"""
Вспомогательные функции анонимизации Chatwoot-сущностей (contact/messages/
conversation). Перенесены из app/main.py без изменения логики — только
перенос кода в рамках выноса интеграции с Chatwoot за флаг CHATWOOT_ENABLED.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.anonymizer import anonymize_json, anonymize_text
from app.integrations.chatwoot.database import Contact, Conversation
from app.integrations.chatwoot.schemas import (
    ContactAnonymized,
    ConversationResponse,
    MessageAnonymized,
)


def _anonymize_contact(
    db: Session, contact_id: int | None, disable_entities=None
) -> ContactAnonymized | None:
    if not contact_id:
        return None

    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        return None

    all_entities = []

    name_anon = None
    if contact.name:
        res = anonymize_text(contact.name, disable_entities=disable_entities)
        name_anon = res["anonymized"]
        all_entities.extend(res["entities_found"])

    email_anon = None
    if contact.email:
        res = anonymize_text(contact.email, disable_entities=disable_entities)
        email_anon = res["anonymized"]
        all_entities.extend(res["entities_found"])

    phone_anon = None
    if contact.phone:
        res = anonymize_text(contact.phone, disable_entities=disable_entities)
        phone_anon = res["anonymized"]
        all_entities.extend(res["entities_found"])

    additional_anon = None
    if contact.additional_attributes:
        additional_anon, all_entities = anonymize_json(
            contact.additional_attributes, all_entities, disable_entities=disable_entities
        )

    custom_anon = None
    if contact.custom_attributes:
        custom_anon, all_entities = anonymize_json(
            contact.custom_attributes, all_entities, disable_entities=disable_entities
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


def _anonymize_messages(messages: list, disable_entities=None) -> list[MessageAnonymized]:
    """Анонимизирует список сообщений. Принимает уже загруженные ORM-объекты."""
    results = []
    for msg in sorted(messages, key=lambda m: m.created_at or datetime.min):
        all_entities = []

        content_anon = None
        if msg.content:
            res = anonymize_text(msg.content, disable_entities=disable_entities)
            content_anon = res["anonymized"]
            all_entities.extend(res["entities_found"])

        content_attrs_anon = None
        if msg.content_attributes:
            content_attrs_anon, all_entities = anonymize_json(
                msg.content_attributes, all_entities, disable_entities=disable_entities
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


def _anonymize_conversation(
    conv: Conversation, db: Session, disable_entities=None
) -> ConversationResponse:
    all_entities = []

    identifier_anon = None
    if conv.identifier:
        res = anonymize_text(conv.identifier, disable_entities=disable_entities)
        identifier_anon = res["anonymized"]
        all_entities.extend(res["entities_found"])

    additional_anon = None
    if conv.additional_attributes:
        additional_anon, all_entities = anonymize_json(
            conv.additional_attributes, all_entities, disable_entities=disable_entities
        )

    custom_anon = None
    if conv.custom_attributes:
        custom_anon, all_entities = anonymize_json(
            conv.custom_attributes, all_entities, disable_entities=disable_entities
        )

    contact_result = _anonymize_contact(db, conv.contact_id, disable_entities=disable_entities)
    if contact_result:
        all_entities.extend(contact_result.entities_found)

    # Используем уже загруженные через selectinload сообщения
    messages_result = _anonymize_messages(conv.messages, disable_entities=disable_entities)
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
