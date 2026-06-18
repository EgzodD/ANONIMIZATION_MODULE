"""
Микросервис анонимизации персональных данных.
Использует Microsoft Presidio с кастомными распознавателями для русского языка.
Работает с БД Chatwoot: conversations -> messages -> contacts.
"""

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

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
import logging

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
        "**Не скрывается:** LOCATION (локация/адрес)"
    ),
    version="1.0.0",
)


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


def _anonymize_messages(db: Session, conversation_id: int) -> list[MessageAnonymized]:
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .all()
    )

    results = []
    for msg in messages:
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

    # Conversation fields
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

    # Contact
    contact_result = _anonymize_contact(db, conv.contact_id)
    if contact_result:
        all_entities.extend(contact_result.entities_found)

    # Messages
    messages_result = _anonymize_messages(db, conv.id)
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


@app.post("/anonymize/text", response_model=AnonymizeTextResponse, tags=["Anonymization"])
def anonymize_free_text(request: AnonymizeTextRequest):
    """Анонимизация произвольного текста. Принимает текст, возвращает анонимизированный + маппинг."""
    result = anonymize_text(request.text)
    return AnonymizeTextResponse(**result)


@app.post("/anonymize/conversation", response_model=ConversationResponse, tags=["Anonymization"])
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
    conv = db.query(Conversation).filter(Conversation.id == request.conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return _anonymize_conversation(conv, db)


@app.post("/anonymize/batch", response_model=BatchResponse, tags=["Anonymization"])
def anonymize_batch(
    request: AnonymizeBatchRequest,
    db: Session = Depends(get_db),
):
    """Пакетная анонимизация нескольких conversations с подтягиванием messages и contacts."""
    conversations = (
        db.query(Conversation)
        .filter(Conversation.id.in_(request.conversation_ids))
        .all()
    )

    results = [_anonymize_conversation(conv, db) for conv in conversations]

    return BatchResponse(
        total=len(request.conversation_ids),
        processed=len(results),
        results=results,
    )


@app.post("/webhook", response_model=WebhookResponse, tags=["Webhook"])
def chatwoot_webhook(payload: WebhookPayload):
    """
    Принимает webhook от Chatwoot.
    Регистрируется в Chatwoot: Settings -> Integrations -> Webhooks.
    Подписка на событие: message_created.

    Chatwoot отправляет сюда JSON с данными сообщения.
    Сервис анонимизирует content и данные sender, возвращает результат.
    """
    event = payload.event or "unknown"
    all_entities = []

    # Анонимизация content сообщения
    content_anon = None
    if payload.content:
        res = anonymize_text(payload.content)
        content_anon = res["anonymized"]
        all_entities.extend(res["entities_found"])

    # Анонимизация данных отправителя (имя, email, телефон)
    sender_anon = None
    if payload.sender:
        sender_anon, all_entities = anonymize_json(payload.sender, all_entities)

    # ID из payload
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
