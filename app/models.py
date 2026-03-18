from pydantic import BaseModel, Field
from datetime import datetime


# --- Request ---

class AnonymizeTextRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Текст для анонимизации")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"text": "Меня зовут Иван Петров, мой телефон +7 999 123 45 67, email ivan@mail.ru"}
            ]
        }
    }


class AnonymizeConversationRequest(BaseModel):
    conversation_id: int = Field(..., description="ID записи в таблице conversations")


class AnonymizeBatchRequest(BaseModel):
    conversation_ids: list[int] = Field(..., min_length=1, description="Список ID записей")


# --- Response ---

class EntityFound(BaseModel):
    entity_type: str
    start: int
    end: int
    score: float
    value: str


class AnonymizeTextResponse(BaseModel):
    original: str
    anonymized: str
    entities_found: list[EntityFound]
    mapping: dict[str, str]


class MessageAnonymized(BaseModel):
    message_id: int
    message_type: int | None
    sender_type: str | None
    original_content: str | None
    anonymized_content: str | None
    content_attributes_anonymized: dict | None
    entities_found: list[EntityFound]
    created_at: datetime | None


class ContactAnonymized(BaseModel):
    contact_id: int
    original_name: str | None
    anonymized_name: str | None
    original_email: str | None
    anonymized_email: str | None
    original_phone: str | None
    anonymized_phone: str | None
    additional_attributes_anonymized: dict | None
    custom_attributes_anonymized: dict | None
    entities_found: list[EntityFound]


class ConversationResponse(BaseModel):
    id: int
    uuid: str
    display_id: int
    identifier: str | None
    identifier_anonymized: str | None
    additional_attributes_anonymized: dict | None
    custom_attributes_anonymized: dict | None
    contact: ContactAnonymized | None
    messages: list[MessageAnonymized]
    total_entities_found: int
    created_at: datetime | None


class BatchResponse(BaseModel):
    total: int
    processed: int
    results: list[ConversationResponse]


class HealthResponse(BaseModel):
    status: str
    analyzer_ready: bool
    supported_entities: list[str]


# --- Webhook ---

class WebhookPayload(BaseModel):
    """Payload от Chatwoot webhook (событие message_created и др.)."""
    event: str | None = None
    id: int | None = None
    content: str | None = None
    content_type: str | None = None
    message_type: str | None = None
    conversation: dict | None = None
    sender: dict | None = None
    account: dict | None = None
    inbox: dict | None = None

    model_config = {"extra": "allow"}


class WebhookResponse(BaseModel):
    event: str
    message_id: int | None
    conversation_id: int | None
    original_content: str | None
    anonymized_content: str | None
    sender_anonymized: dict | None
    entities_found: list[EntityFound]
    total_entities: int
