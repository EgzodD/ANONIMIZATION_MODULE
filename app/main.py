"""
Микросервис анонимизации персональных данных.
Использует Microsoft Presidio с кастомными распознавателями для русского языка.
Работает с БД Chatwoot: conversations -> messages -> contacts.
"""

import hmac
import hashlib
import logging
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import get_db, Conversation, Message, Contact
from app.anonymizer import anonymize_text, anonymize_json, analyzer_engine, EXCLUDED_ENTITIES
from app.models import (
    AnonymizeTextRequest,
    AnonymizeConversationRequest,
    AnonymizeBatchRequest,
    AnonymizeTextResponse,
    ConversationResponse,
    MessageAnonymized,
    ContactAnonymized,
    BatchResponse,
    HealthResponse,
    WebhookPayload,
    WebhookResponse,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Anonymization Service",
    description=(
        "Микросервис анонимизации персональных данных в русскоязычных текстах.\n\n"
        "Использует Microsoft Presidio + кастомные распознаватели для русского языка.\n\n"
        "Работает с БД Chatwoot. При анонимизации conversation подтягиваются:\n"
        "- **messages** — поле `content` (текст сообщения) + `content_attributes` (jsonb)\n"
        "- **contacts** — поля `name`, `email`, `phone`, `additional_attributes`, `custom_attributes`\n"
        "- **conversations** — поля `identifier`, `additional_attributes`, `custom_attributes`\n\n"
        "**Поддерживаемые типы ПДн:**\n"
        "- PERSON — ФИО\n"
        "- PHONE_NUMBER — номера телефонов (+7, 8)\n"
        "- EMAIL_ADDRESS — email-адреса\n"
        "- INN — ИНН (10/12 цифр)\n"
        "- SNILS — СНИЛС\n"
        "- PASSPORT — серия и номер паспорта\n"
        "- DATE_OF_BIRTH — дата рождения\n"
        "- CREDIT_CARD — номера карт\n\n"
        "**Не скрывается:** LOCATION (локация/адрес)\n\n"
        "**Аутентификация:** X-API-Key header (если задан API_KEY в env)"
    ),
    version="2.0.0",
)

# ─── API-ключ аутентификация ───────────────────────────────────────────────
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: str | None = Depends(_api_key_header)):
    """Проверяет X-API-Key. Если API_KEY не задан в env — аутентификация отключена."""
    if settings.api_key and api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")


# ─── Вспомогательные функции анонимизации ─────────────────────────────────

def _anonymize_contact(db: Session, contact_id: int | None) -> ContactAnonymized | None:
    if not contact_id:
        return None

    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        return None

    all_entities = []

    name_anon = None
    if contact.name:
        res = anonymize_text(contact.name)
        name_anon = res["anonymized"]
        all_entities.extend(res["entities_found"])

    email_anon = None
    if contact.email:
        res = anonymize_text(contact.email)
        email_anon = res["anonymized"]
        all_entities.extend(res["entities_found"])

    phone_anon = None
    if contact.phone:
        res = anonymize_text(contact.phone)
        phone_anon = res["anonymized"]
        all_entities.extend(res["entities_found"])

    additional_anon = None
    if contact.additional_attributes:
        additional_anon, all_entities = anonymize_json(
            contact.additional_attributes, all_entities
        )

    custom_anon = None
    if contact.custom_attributes:
        custom_anon, all_entities = anonymize_json(
            contact.custom_attributes, all_entities
        )

    return ContactAnonymized(
        contact_id=contact.id,
        original_name=contact.name,
        anonymized_name=name_anon,
        original_email=contact.email,
        anonymized_email=email_anon,
        original_phone=contact.phone,
        anonymized_phone=phone_anon,
        additional_attributes_anonymized=additional_anon,
        custom_attributes_anonymized=custom_anon,
        entities_found=all_entities,
    )


def _anonymize_messages(messages: list) -> list[MessageAnonymized]:
    """Анонимизирует список сообщений. Принимает уже загруженные ORM-объекты."""
    results = []
    for msg in sorted(messages, key=lambda m: m.created_at or datetime.min):
        all_entities = []

        content_anon = None
        if msg.content:
            res = anonymize_text(msg.content)
            content_anon = res["anonymized"]
            all_entities.extend(res["entities_found"])

        content_attrs_anon = None
        if msg.content_attributes:
            content_attrs_anon, all_entities = anonymize_json(
                msg.content_attributes, all_entities
            )

        results.append(
            MessageAnonymized(
                message_id=msg.id,
                message_type=msg.message_type,
                sender_type=msg.sender_type,
                original_content=msg.content,
                anonymized_content=content_anon,
                content_attributes_anonymized=content_attrs_anon,
                entities_found=all_entities,
                created_at=msg.created_at,
            )
        )

    return results


def _anonymize_conversation(conv: Conversation, db: Session) -> ConversationResponse:
    all_entities = []

    identifier_anon = None
    if conv.identifier:
        res = anonymize_text(conv.identifier)
        identifier_anon = res["anonymized"]
        all_entities.extend(res["entities_found"])

    additional_anon = None
    if conv.additional_attributes:
        additional_anon, all_entities = anonymize_json(
            conv.additional_attributes, all_entities
        )

    custom_anon = None
    if conv.custom_attributes:
        custom_anon, all_entities = anonymize_json(
            conv.custom_attributes, all_entities
        )

    contact_result = _anonymize_contact(db, conv.contact_id)
    if contact_result:
        all_entities.extend(contact_result.entities_found)

    # Используем уже загруженные через selectinload сообщения
    messages_result = _anonymize_messages(conv.messages)
    for msg in messages_result:
        all_entities.extend(msg.entities_found)

    return ConversationResponse(
        id=conv.id,
        uuid=conv.uuid,
        display_id=conv.display_id,
        identifier=conv.identifier,
        identifier_anonymized=identifier_anon,
        additional_attributes_anonymized=additional_anon,
        custom_attributes_anonymized=custom_anon,
        contact=contact_result,
        messages=messages_result,
        total_entities_found=len(all_entities),
        created_at=conv.created_at,
    )


# ─── Эндпоинты ────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check(db: Session = Depends(get_db)):
    """Проверка состояния сервиса, подключения к БД и списка поддерживаемых типов сущностей."""
    db_ok = False
    try:
        db.execute(sql_text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    supported = analyzer_engine.get_supported_entities(language="ru")
    filtered = [e for e in supported if e not in EXCLUDED_ENTITIES]
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        analyzer_ready=True,
        db_connected=db_ok,
        supported_entities=sorted(filtered),
    )


@app.post(
    "/anonymize/text",
    response_model=AnonymizeTextResponse,
    tags=["Anonymization"],
    dependencies=[Depends(require_api_key)],
)
def anonymize_free_text(request: AnonymizeTextRequest):
    """Анонимизация произвольного текста. Принимает текст, возвращает анонимизированный + маппинг."""
    result = anonymize_text(request.text)
    return AnonymizeTextResponse(**result)


@app.post(
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

    return _anonymize_conversation(conv, db)


@app.post(
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

    results = [_anonymize_conversation(conv, db) for conv in conversations]

    return BatchResponse(
        total=len(request.conversation_ids),
        processed=len(results),
        results=results,
    )


@app.post("/webhook", response_model=WebhookResponse, tags=["Webhook"])
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
