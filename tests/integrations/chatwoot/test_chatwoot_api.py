"""
Тесты Chatwoot-специфичных эндпоинтов: /webhook, /anonymize/conversation,
/anonymize/batch. Перенесены из tests/test_api.py при разделении ядра и
опциональной интеграции с Chatwoot (CHATWOOT_ENABLED).

Работают через фикстуру `client` из локального conftest.py, которая форсирует
CHATWOOT_ENABLED=true. Реальный Postgres не поднимается: DATABASE_URL указывает
на заведомо недоступный адрес. Поэтому:
- /webhook (не обращается к БД) тестируется полноценно, как раньше;
- /anonymize/conversation и /anonymize/batch (обращаются к БД) тестируются
  только на регистрацию роута (не 404) и предсказуемую ошибку при
  недоступной БД — end-to-end тесты с реальными данными Chatwoot вне охвата
  этого файла.
"""

import pytest

pytestmark = pytest.mark.integration


class TestWebhookEndpoint:
    def test_webhook_message_created(self, client):
        payload = {
            "event": "message_created",
            "id": 100,
            "content": "Здравствуйте, меня зовут Иван Петров, тел +79991234567",
            "message_type": "incoming",
            "conversation": {"id": 1, "status": "open"},
            "sender": {
                "id": 10,
                "name": "Иван Петров",
                "email": "ivan@mail.ru",
                "phone_number": "+79991234567",
                "type": "contact",
            },
            "account": {"id": 1},
        }
        response = client.post("/webhook", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["event"] == "message_created"
        assert data["message_id"] == 100
        assert data["conversation_id"] == 1
        assert "<PHONE>" in data["anonymized_content"]
        assert data["total_entities"] > 0

    def test_webhook_anonymizes_sender(self, client):
        payload = {
            "event": "message_created",
            "id": 101,
            "content": "Привет",
            "sender": {
                "name": "Мария Сидорова",
                "email": "maria@yandex.ru",
            },
        }
        response = client.post("/webhook", json=payload)
        data = response.json()
        assert "<EMAIL>" in data["sender_anonymized"]["email"]

    def test_webhook_empty_content(self, client):
        payload = {
            "event": "conversation_created",
            "id": 102,
            "content": None,
            "sender": None,
        }
        response = client.post("/webhook", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["anonymized_content"] is None
        assert data["total_entities"] == 0

    def test_webhook_preserves_location_in_content(self, client):
        # Ранее xfail: PERSON поглощал соседний топоним ('Иван Петров из Москвы'
        # -> единый <PERSON>). Исправлено дообучением с негативами (ФИО рядом с
        # городом) — теперь город остаётся в тексте.
        payload = {
            "event": "message_created",
            "id": 103,
            "content": "Иван Петров из Москвы",
            "sender": None,
        }
        response = client.post("/webhook", json=payload)
        data = response.json()
        assert "Москв" in data["anonymized_content"]


class TestConversationEndpoint:
    """Без реального Postgres — только регистрация роута и поведение при недоступной БД."""

    def test_conversation_route_registered(self, client):
        response = client.post("/anonymize/conversation", json={"conversation_id": 1})
        assert response.status_code != 404

    def test_conversation_handles_db_unavailable(self, client):
        response = client.post("/anonymize/conversation", json={"conversation_id": 1})
        assert response.status_code >= 500


class TestBatchEndpoint:
    """Без реального Postgres — только регистрация роута и поведение при недоступной БД."""

    def test_batch_route_registered(self, client):
        response = client.post("/anonymize/batch", json={"conversation_ids": [1, 2]})
        assert response.status_code != 404

    def test_batch_handles_db_unavailable(self, client):
        response = client.post("/anonymize/batch", json={"conversation_ids": [1, 2]})
        assert response.status_code >= 500


class TestSwaggerDocsChatwoot:
    def test_openapi_lists_chatwoot_routes(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "/anonymize/conversation" in schema["paths"]
        assert "/anonymize/batch" in schema["paths"]
        assert "/webhook" in schema["paths"]

    def test_openapi_describes_conversation_response(self, client):
        response = client.get("/openapi.json")
        schemas = response.json()["components"]["schemas"]
        assert "ConversationResponse" in schemas
        conv_props = schemas["ConversationResponse"]["properties"]
        assert "messages" in conv_props
        assert "contact" in conv_props
        assert "total_entities_found" in conv_props
