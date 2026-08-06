"""
Тесты модуля анонимизации — проверка распознавания русских ПДн.

Категория: модульные (unit) — каждый тип ПДн проверяется изолированно.
Запуск только этой категории: pytest -m unit (или через scripts/test_menu.py).
"""

import csv
import os

import pytest

from app.anonymizer import analyze_text, anonymize_text

pytestmark = pytest.mark.unit


class TestPersonRecognition:
    def test_recognizes_full_name(self):
        result = anonymize_text("Обращение от Ивана Петрова по вопросу кредита")
        assert "<PERSON>" in result["anonymized"]

    def test_recognizes_full_name_with_patronymic(self):
        result = anonymize_text("Клиент: Наталья Владимировна Кузнецова")
        assert "<PERSON>" in result["anonymized"]
        assert "Наталья" not in result["anonymized"]


class TestPhoneRecognition:
    def test_recognizes_plus7_phone(self):
        result = anonymize_text("Телефон: +7 999 123 45 67")
        assert "<PHONE>" in result["anonymized"]
        assert "999" not in result["anonymized"]

    def test_recognizes_8_phone(self):
        result = anonymize_text("Звоните 8 (495) 555-12-34")
        assert "<PHONE>" in result["anonymized"]

    def test_recognizes_compact_phone(self):
        result = anonymize_text("Номер: +79161234567")
        assert "<PHONE>" in result["anonymized"]


class TestEmailRecognition:
    def test_recognizes_email(self):
        result = anonymize_text("Почта: ivan.petrov@yandex.ru")
        assert "<EMAIL>" in result["anonymized"]
        assert "ivan.petrov" not in result["anonymized"]


class TestInnRecognition:
    def test_recognizes_inn_12_with_context(self):
        # 772012345670 — валидный ИНН (12 цифр, проходит алгоритм ФНС)
        result = anonymize_text("ИНН: 772012345670")
        assert "<INN>" in result["anonymized"]

    def test_recognizes_inn_10_with_context(self):
        # 7701234560 — валидный ИНН (10 цифр, проходит алгоритм ФНС)
        result = anonymize_text("ИНН клиента 7701234560")
        assert "<INN>" in result["anonymized"]


class TestSnilsRecognition:
    def test_recognizes_snils_dashes(self):
        # 123-456-789 64 — валидный СНИЛС (проходит алгоритм ПФР)
        result = anonymize_text("СНИЛС 123-456-789 64")
        assert "<SNILS>" in result["anonymized"]

    def test_recognizes_snils_spaces(self):
        # 123 456 789 64 — валидный СНИЛС (пробельный формат)
        result = anonymize_text("страховое свидетельство 123 456 789 64")
        assert "<SNILS>" in result["anonymized"]


class TestPassportRecognition:
    def test_recognizes_passport_with_context(self):
        result = anonymize_text("Паспорт серия 4515 номер 123456")
        entities = [e["entity_type"] for e in result["entities_found"]]
        assert "PASSPORT" in entities


class TestDateOfBirthRecognition:
    def test_recognizes_dob_dot_format(self):
        result = anonymize_text("Дата рождения: 15.03.1990")
        assert "<DATE_OF_BIRTH>" in result["anonymized"]

    def test_recognizes_dob_slash_format(self):
        result = anonymize_text("Родился 25/12/1985")
        # Может детектиться как DATE_OF_BIRTH или DATE_TIME — оба варианта корректны
        assert "25/12/1985" not in result["anonymized"]


class TestCreditCardRecognition:
    def test_recognizes_card_spaces(self):
        result = anonymize_text("Номер карты 4276 1234 5678 9012")
        assert "<CREDIT_CARD>" in result["anonymized"]

    def test_recognizes_card_dashes(self):
        result = anonymize_text("Карта: 4276-5500-1234-7890")
        assert "<CREDIT_CARD>" in result["anonymized"]


class TestLocationNotHidden:
    def test_location_preserved(self):
        result = anonymize_text("Я живу в Москве на улице Ленина")
        assert "Москв" in result["anonymized"]

    def test_city_preserved(self):
        # Ранее xfail: модель метила 'Санкт-Петербург' как ФИО. Исправлено
        # дообучением с негативами-топонимами (27.07) — теперь топоним остаётся.
        result = anonymize_text("Офис расположен в Санкт-Петербурге")
        assert "Санкт-Петербург" in result["anonymized"]


class TestEdgeCases:
    def test_empty_string(self):
        result = anonymize_text("")
        assert result["anonymized"] == ""
        assert result["entities_found"] == []

    def test_whitespace_only(self):
        result = anonymize_text("   ")
        assert result["entities_found"] == []

    def test_no_pii(self):
        result = anonymize_text("Сегодня хорошая погода в парке")
        assert result["anonymized"] == "Сегодня хорошая погода в парке"

    def test_multiple_entities(self):
        text = "Иван Петров, +79991234567, ivan@mail.ru"
        result = anonymize_text(text)
        assert "<PHONE>" in result["anonymized"]
        assert "<EMAIL>" in result["anonymized"]

    def test_mapping_returned(self):
        result = anonymize_text("Телефон: +7 999 123 45 67")
        assert len(result["mapping"]) > 0


class TestAnonymizeJson:
    def test_anonymizes_flat_dict(self):
        from app.anonymizer import anonymize_json
        data = {"name": "Иван Петров", "city": "Москва"}
        result, entities = anonymize_json(data)
        assert "<PERSON>" in result["name"]
        assert "Москв" in result["city"]  # LOCATION не скрывается

    def test_anonymizes_nested_dict(self):
        from app.anonymizer import anonymize_json
        data = {"info": {"phone": "Телефон: +79991234567", "note": "обычный текст"}}
        result, entities = anonymize_json(data)
        assert "<PHONE>" in result["info"]["phone"]
        assert result["info"]["note"] == "обычный текст"

    def test_anonymizes_list(self):
        from app.anonymizer import anonymize_json
        data = ["Иван Петров", "обычный текст"]
        result, entities = anonymize_json(data)
        assert "<PERSON>" in result[0]

    def test_handles_none(self):
        from app.anonymizer import anonymize_json
        result, entities = anonymize_json(None)
        assert result is None

    def test_handles_numbers(self):
        from app.anonymizer import anonymize_json
        data = {"count": 42, "active": True}
        result, entities = anonymize_json(data)
        assert result["count"] == 42
        assert result["active"] is True


class TestDatasetCoverage:
    """Проверяем покрытие на CSV-датасете."""

    @pytest.fixture
    def dataset(self):
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "ru_training_data.csv"
        )
        rows = []
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        return rows

    def test_dataset_recall(self, dataset):
        """Recall >= 0.5 на датасете — хотя бы половина сущностей распознана."""
        total = 0
        found = 0

        seen_texts = {}
        for row in dataset:
            text = row["text"]
            expected_type = row["entity_type"]
            if text not in seen_texts:
                seen_texts[text] = analyze_text(text)

            results = seen_texts[text]
            detected_types = {r.entity_type for r in results}
            total += 1
            if expected_type in detected_types:
                found += 1

        recall = found / total if total > 0 else 0
        assert recall >= 0.95, f"Recall={recall:.2f} < 0.95 (found {found}/{total})"
