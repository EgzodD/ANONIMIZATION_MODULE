from pydantic import BaseModel, Field
from datetime import datetime


# --- Request ---

# Общее описание кастомного параметра для всех запросов анонимизации.
_DISABLE_ENTITIES_DESC = (
    "Необязательный список типов сущностей, которые НЕ нужно скрывать в этом запросе "
    "(например [\"DATE_OF_BIRTH\"]). Параметр может только СУЖАТЬ анонимизацию: "
    "перечисленные типы будут пропущены. Включить типы вне политики сервиса "
    "(в т.ч. LOCATION/NRP) через него нельзя. Неизвестные названия игнорируются "
    "(данные останутся скрытыми). Каждое применение логируется."
)


class AnonymizeTextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=50_000, description="Текст для анонимизации")
    disable_entities: list[str] | None = Field(default=None, description=_DISABLE_ENTITIES_DESC)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "text": "Меня зовут Иван Петров, мой телефон +7 999 123 45 67, email ivan@mail.ru",
                    "disable_entities": ["DATE_OF_BIRTH"],
                }
            ]
        }
    }


class AnonymizeConversationRequest(BaseModel):
    conversation_id: int = Field(..., description="ID записи в таблице conversations")
    disable_entities: list[str] | None = Field(default=None, description=_DISABLE_ENTITIES_DESC)


class AnonymizeBatchRequest(BaseModel):
    conversation_ids: list[int] = Field(..., min_length=1, max_length=100, description="Список ID записей")
    disable_entities: list[str] | None = Field(default=None, description=_DISABLE_ENTITIES_DESC)


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
    content_attributes_anonymized: dict | list | None
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
    additional_attributes_anonymized: dict | list | None
    custom_attributes_anonymized: dict | list | None
    entities_found: list[EntityFound]


class ConversationResponse(BaseModel):
    id: int
    uuid: str
    display_id: int
    identifier: str | None
    identifier_anonymized: str | None
    additional_attributes_anonymized: dict | list | None
    custom_attributes_anonymized: dict | list | None
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
    db_connected: bool
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
