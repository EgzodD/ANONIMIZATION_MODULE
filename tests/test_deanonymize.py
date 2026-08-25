"""
Деобезличивание: восстановление исходных значений по mapping.

Ключевой сценарий продукта — обратимость: анонимизировать → отдать <PERSON>/<PHONE>
внешней LLM → восстановить ответ по mapping. Проверяем полный round-trip и
восстановление в тексте другой структуры (ответ LLM), в т.ч. с повторами
(<PHONE>, <PHONE_2>).
"""
import pytest

from app.anonymizer import anonymize_text, deanonymize_text

pytestmark = pytest.mark.unit


def test_deanonymize_empty_and_no_mapping():
    assert deanonymize_text("", {}) == {"deanonymized": "", "replaced": 0}
    assert deanonymize_text("нет плейсхолдеров", {}) == {
        "deanonymized": "нет плейсхолдеров", "replaced": 0}


def test_deanonymize_llm_response():
    """Ответ LLM другой структуры восстанавливается по mapping."""
    mapping = {"<PERSON>": "Иван Петров", "<PHONE>": "+7 999 123 45 67"}
    out = deanonymize_text("Перезвоните <PERSON> по номеру <PHONE>.", mapping)
    assert out["deanonymized"] == "Перезвоните Иван Петров по номеру +7 999 123 45 67."
    assert out["replaced"] == 2


def test_deanonymize_duplicate_placeholders():
    """Нумерованные повторы (<PHONE>, <PHONE_2>) не путаются между собой."""
    mapping = {"<PHONE>": "+7 111", "<PHONE_2>": "+7 222"}
    out = deanonymize_text("Основной <PHONE>, запасной <PHONE_2>.", mapping)
    assert out["deanonymized"] == "Основной +7 111, запасной +7 222."
    assert out["replaced"] == 2


@pytest.mark.requires_model
def test_round_trip_restores_original():
    """anonymize → deanonymize возвращает ИСХОДНЫЙ текст ключ-в-ключ."""
    text = ("Здравствуйте, меня зовут Иван Петров, телефон +7 999 123 45 67, "
            "запасной 8 926 000 11 22, почта ivan@mail.ru.")
    res = anonymize_text(text)
    assert res["anonymized"] != text            # что-то замаскировано
    back = deanonymize_text(res["anonymized"], res["mapping"])
    assert back["deanonymized"] == text          # полное восстановление
