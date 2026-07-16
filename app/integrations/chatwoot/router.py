"""
Роуты интеграции с Chatwoot: /anonymize/conversation, /anonymize/batch, /webhook.
Подключаются в app/main.py только если settings.chatwoot_enabled == True.
"""

import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, selectinload

from app.anonymizer import anonymize_json, anonymize_text
from app.auth import require_api_key
from app.config import settings
from app.integrations.chatwoot.database import Conversation, get_db
from app.integrations.chatwoot.schemas import (
    AnonymizeBatchRequest,
    AnonymizeConversationRequest,
    BatchResponse,
    ConversationResponse,
    WebhookPayload,
    WebhookResponse,
)
from app.integrations.chatwoot.service import _anonymize_conversation

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/anonymize/conversation",
    response_model=ConversationResponse,
    tags=["Anonymization"],
    dependencies=[Depends(require_api_key)],
)
def anonymize_conversation(
    request: AnonymizeConversationRequest,
    db: Session = Depends(get_db),
):
    """
    Полная анонимизация conversation с подтягиванием связанных данных:
    - messages.content + messages.content_attributes
    - contacts.name, email, phone, additional_attributes, custom_attributes
    - conversations.identifier, additional_attributes, custom_attributes
    """
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == request.conversation_id)
        .options(selectinload(Conversation.messages))
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return _anonymize_conversation(conv, db, disable_entities=request.disable_entities)


@router.post(
    "/anonymize/batch",
    response_model=BatchResponse,
    tags=["Anonymization"],
    dependencies=[Depends(require_api_key)],
)
def anonymize_batch(
    request: AnonymizeBatchRequest,
    db: Session = Depends(get_db),
):
    """Пакетная анонимизация нескольких conversations. Сообщения загружаются одним запросом (selectinload)."""
    conversations = (
        db.query(Conversation)
        .filter(Conversation.id.in_(request.conversation_ids))
        .options(selectinload(Conversation.messages))
        .all()
    )

    results = [
        _anonymize_conversation(conv, db, disable_entities=request.disable_entities)
        for conv in conversations
    ]

    return BatchResponse(
        total=len(request.conversation_ids),
        processed=len(results),
        results=results,
    )


@router.post("/webhook", response_model=WebhookResponse, tags=["Webhook"])
async def chatwoot_webhook(http_request: Request, payload: WebhookPayload):
    """
    Принимает webhook от Chatwoot.
    Если CHATWOOT_WEBHOOK_SECRET задан — проверяет HMAC-SHA256 подпись (X-Chatwoot-Signature).
    Регистрируется в Chatwoot: Settings -> Integrations -> Webhooks.
    """
    if settings.chatwoot_webhook_secret:
        sig = http_request.headers.get("X-Chatwoot-Signature", "")
        body = await http_request.body()
        expected = hmac.new(
            settings.chatwoot_webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise HTTPException(status_code=403, detail="Invalid webhook signature")

    event = payload.event or "unknown"
    all_entities = []

    content_anon = None
    if payload.content:
        res = anonymize_text(payload.content)
        content_anon = res["anonymized"]
        all_entities.extend(res["entities_found"])

    sender_anon = None
    if payload.sender:
        sender_anon, all_entities = anonymize_json(payload.sender, all_entities)

    message_id = payload.id
    conversation_id = None
    if payload.conversation and isinstance(payload.conversation, dict):
        conversation_id = payload.conversation.get("id")

    logger.info(
        "Webhook [%s]: message_id=%s, conversation_id=%s, entities=%d",
        event, message_id, conversation_id, len(all_entities),
    )

    return WebhookResponse(
        event=event,
        message_id=message_id,
        conversation_id=conversation_id,
        original_content=payload.content,
        anonymized_content=content_anon,
        sender_anonymized=sender_anon,
        entities_found=all_entities,
        total_entities=len(all_entities),
    )
