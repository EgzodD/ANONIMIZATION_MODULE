"""
Тесты API эндпоинтов.
"""

import pytest


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["analyzer_ready"] is True

    def test_health_lists_supported_entities(self, client):
        response = client.get("/health")
        data = response.json()
        assert "PHONE_NUMBER" in data["supported_entities"]
        assert "EMAIL_ADDRESS" in data["supported_entities"]
        assert "LOCATION" not in data["supported_entities"]


class TestAnonymizeTextEndpoint:
    def test_anonymize_text_success(self, client):
        response = client.post(
            "/anonymize/text",
            json={"text": "Меня зовут Иван Петров, телефон +79991234567"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "anonymized" in data
        assert "<PHONE>" in data["anonymized"]

    def test_anonymize_text_empty_body(self, client):
        response = client.post("/anonymize/text", json={"text": ""})
        assert response.status_code == 422

    def test_anonymize_text_no_pii(self, client):
        response = client.post(
            "/anonymize/text",
            json={"text": "Хорошая погода сегодня"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["anonymized"] == "Хорошая погода сегодня"
        assert data["entities_found"] == []

    def test_anonymize_text_preserves_location(self, client):
        response = client.post(
            "/anonymize/text",
            json={"text": "Иван Петров живёт в Москве"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "Москв" in data["anonymized"]

    def test_anonymize_text_returns_mapping(self, client):
        response = client.post(
            "/anonymize/text",
            json={"text": "Телефон: +7 999 123 45 67"},
        )
        data = response.json()
        assert len(data["mapping"]) > 0

    def test_anonymize_text_response_structure(self, client):
        response = client.post(
            "/anonymize/text",
            json={"text": "Иван Петров, ivan@mail.ru, +79991234567"},
        )
        data = response.json()
        assert "original" in data
        assert "anonymized" in data
        assert "entities_found" in data
        assert "mapping" in data
        for entity in data["entities_found"]:
            assert "entity_type" in entity
            assert "start" in entity
            assert "end" in entity
            assert "score" in entity
            assert "value" in entity


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
        payload = {
            "event": "message_created",
            "id": 103,
            "content": "Иван Петров из Москвы",
            "sender": None,
        }
        response = client.post("/webhook", json=payload)
        data = response.json()
        assert "Москв" in data["anonymized_content"]


class TestSwaggerDocs:
    def test_openapi_schema_available(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == "Anonymization Service"
        assert "/anonymize/text" in schema["paths"]
        assert "/anonymize/conversation" in schema["paths"]
        assert "/anonymize/batch" in schema["paths"]
        assert "/health" in schema["paths"]

    def test_swagger_ui_available(self, client):
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_describes_conversation_response(self, client):
        response = client.get("/openapi.json")
        schemas = response.json()["components"]["schemas"]
        assert "ConversationResponse" in schemas
        conv_props = schemas["ConversationResponse"]["properties"]
        assert "messages" in conv_props
        assert "contact" in conv_props
        assert "total_entities_found" in conv_props
