"""
Тесты API эндпоинтов.
"""



class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("ok", "degraded")  # degraded когда БД недоступна
        assert data["analyzer_ready"] is True
        assert "db_connected" in data

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


class TestSwaggerDocs:
    def test_openapi_schema_available(self, client):
        """Ядровая проверка: OpenAPI отдаётся в standalone-режиме (CHATWOOT_ENABLED=false)
        и описывает ядровые эндпоинты. Chatwoot-эндпоинты — см.
        tests/integrations/chatwoot/test_chatwoot_api.py."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == "Anonymization Service"
        assert "/anonymize/text" in schema["paths"]
        assert "/health" in schema["paths"]

    def test_swagger_ui_available(self, client):
        response = client.get("/docs")
        assert response.status_code == 200
