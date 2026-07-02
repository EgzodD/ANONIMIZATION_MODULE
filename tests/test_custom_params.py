"""
Тесты кастомного параметра `disable_entities` — выборочное отключение типов
сущностей в запросе. Проверяем, что параметр только СУЖАЕТ анонимизацию
(отключает разрешённые типы), не даёт включить запрещённые и не роняет запрос
на мусорных значениях.
"""

from app.anonymizer import (
    anonymize_text,
    anonymize_json,
    analyze_text,
    resolve_disabled_entities,
    POLICY_ENTITIES,
    EXCLUDED_ENTITIES,
)


class TestResolveDisabledEntities:
    def test_empty_returns_empty(self):
        assert resolve_disabled_entities(None) == frozenset()
        assert resolve_disabled_entities([]) == frozenset()

    def test_valid_type_kept(self):
        assert resolve_disabled_entities(["PHONE_NUMBER"]) == frozenset({"PHONE_NUMBER"})

    def test_case_insensitive_and_trimmed(self):
        assert resolve_disabled_entities([" phone_number "]) == frozenset({"PHONE_NUMBER"})

    def test_unknown_type_ignored(self):
        # мусор не проходит и не ломает — возвращается пустое множество
        assert resolve_disabled_entities(["FOO_BAR"]) == frozenset()

    def test_cannot_enable_forbidden(self):
        # LOCATION/NRP исключены из политики — их нельзя "отключить" (они и так не скрываются),
        # и через параметр они не попадают в результат resolve
        result = resolve_disabled_entities(list(EXCLUDED_ENTITIES))
        assert result == frozenset()
        assert not (result & EXCLUDED_ENTITIES)

    def test_result_is_subset_of_policy(self):
        result = resolve_disabled_entities(["PHONE_NUMBER", "EMAIL_ADDRESS", "FOO"])
        assert result <= POLICY_ENTITIES
        assert "FOO" not in result


class TestAnonymizeTextWithDisable:
    def test_disable_dob_keeps_date_but_hides_phone(self):
        # дата ловится двумя распознавателями (DATE_OF_BIRTH + встроенный DATE_TIME),
        # поэтому чтобы не скрывать её — нужно отключить оба типа
        text = "Дата рождения: 15.03.1990, телефон +79991234567"
        result = anonymize_text(text, disable_entities=["DATE_OF_BIRTH", "DATE_TIME"])
        assert "15.03.1990" in result["anonymized"]      # дата не скрыта
        assert "<PHONE>" in result["anonymized"]          # телефон всё ещё скрыт
        assert "+79991234567" not in result["anonymized"]

    def test_disable_single_of_overlapping_types_still_masks(self):
        # если отключить только DATE_OF_BIRTH, дату всё равно скроет DATE_TIME —
        # это безопасное поведение (перекрывающиеся распознаватели)
        text = "Дата рождения: 15.03.1990, телефон +79991234567"
        result = anonymize_text(text, disable_entities=["DATE_OF_BIRTH"])
        assert "15.03.1990" not in result["anonymized"]

    def test_disable_phone_keeps_phone_but_hides_email(self):
        text = "Телефон +79991234567, почта ivan@mail.ru"
        result = anonymize_text(text, disable_entities=["PHONE_NUMBER"])
        assert "+79991234567" in result["anonymized"]     # телефон не скрыт
        assert "<EMAIL>" in result["anonymized"]           # email скрыт

    def test_disable_is_case_insensitive(self):
        text = "Телефон +79991234567"
        result = anonymize_text(text, disable_entities=["phone_number"])
        assert "+79991234567" in result["anonymized"]

    def test_disabled_type_absent_from_entities_found(self):
        text = "Телефон +79991234567, почта ivan@mail.ru"
        result = anonymize_text(text, disable_entities=["PHONE_NUMBER"])
        types = {e["entity_type"] for e in result["entities_found"]}
        assert "PHONE_NUMBER" not in types
        assert "EMAIL_ADDRESS" in types

    def test_no_disable_equals_full_anonymization(self):
        text = "Дата рождения: 15.03.1990, телефон +79991234567"
        result = anonymize_text(text)
        assert "<DATE_OF_BIRTH>" in result["anonymized"]
        assert "<PHONE>" in result["anonymized"]

    def test_unknown_disable_does_not_leak(self):
        # мусорный тип не должен отключить реальную анонимизацию
        text = "Телефон +79991234567"
        result = anonymize_text(text, disable_entities=["FOO_BAR"])
        assert "<PHONE>" in result["anonymized"]
        assert "+79991234567" not in result["anonymized"]

    def test_cannot_unhide_location(self):
        # попытка "отключить" LOCATION ничего не ломает; LOCATION и так не скрывается
        text = "Иван Петров живёт в Москве"
        result = anonymize_text(text, disable_entities=["LOCATION"])
        assert "Москв" in result["anonymized"]
        assert "<PERSON>" in result["anonymized"]  # PERSON по-прежнему скрыт


class TestAnalyzeTextWithDisable:
    def test_analyze_respects_disable(self):
        text = "Телефон +79991234567, почта ivan@mail.ru"
        results = analyze_text(text, disable_entities=["PHONE_NUMBER"])
        types = {r.entity_type for r in results}
        assert "PHONE_NUMBER" not in types
        assert "EMAIL_ADDRESS" in types


class TestAnonymizeJsonWithDisable:
    def test_json_threads_disable(self):
        data = {"note": "Телефон +79991234567, почта ivan@mail.ru"}
        result, _ = anonymize_json(data, disable_entities=["PHONE_NUMBER"])
        assert "+79991234567" in result["note"]
        assert "<EMAIL>" in result["note"]


class TestApiDisableEntities:
    def test_endpoint_disable_dob(self, client):
        response = client.post(
            "/anonymize/text",
            json={
                "text": "Дата рождения: 15.03.1990, телефон +79991234567",
                "disable_entities": ["DATE_OF_BIRTH", "DATE_TIME"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "15.03.1990" in data["anonymized"]
        assert "<PHONE>" in data["anonymized"]

    def test_endpoint_without_disable_hides_all(self, client):
        response = client.post(
            "/anonymize/text",
            json={"text": "Дата рождения: 15.03.1990, телефон +79991234567"},
        )
        data = response.json()
        assert "<DATE_OF_BIRTH>" in data["anonymized"]
        assert "<PHONE>" in data["anonymized"]

    def test_endpoint_unknown_type_ignored(self, client):
        response = client.post(
            "/anonymize/text",
            json={"text": "Телефон +79991234567", "disable_entities": ["FOO"]},
        )
        assert response.status_code == 200
        assert "<PHONE>" in response.json()["anonymized"]

    def test_openapi_exposes_disable_entities(self, client):
        schema = client.get("/openapi.json").json()
        props = schema["components"]["schemas"]["AnonymizeTextRequest"]["properties"]
        assert "disable_entities" in props
