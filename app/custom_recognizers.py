"""
Кастомные распознаватели для русских персональных данных.
Presidio по умолчанию не знает русские паттерны — добавляем их вручную.
"""

import logging

from presidio_analyzer import Pattern, PatternRecognizer

logger = logging.getLogger(__name__)

ru_phone_recognizer = PatternRecognizer(
    supported_entity="PHONE_NUMBER",
    supported_language="ru",
    name="RuPhoneRecognizer",
    patterns=[
        Pattern(
            name="ru_phone_plus7",
            regex=r"\+7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}",
            score=0.9,
        ),
        Pattern(
            name="ru_phone_8",
            regex=r"8[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}",
            score=0.85,
        ),
    ],
)


def _validate_inn(inn_str: str) -> bool:
    digits = [int(c) for c in inn_str if c.isdigit()]
    if len(digits) == 10:
        weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        control = sum(w * d for w, d in zip(weights, digits)) % 11 % 10
        return control == digits[9]
    if len(digits) == 12:
        w1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        w2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        c1 = sum(w * d for w, d in zip(w1, digits)) % 11 % 10
        c2 = sum(w * d for w, d in zip(w2, digits)) % 11 % 10
        return c1 == digits[10] and c2 == digits[11]
    return False


class RuInnRecognizer(PatternRecognizer):
    def __init__(self):
        super().__init__(
            supported_entity="INN",
            supported_language="ru",
            name="RuInnRecognizer",
            patterns=[
                Pattern(name="inn_12", regex=r"\b\d{12}\b", score=0.5),
                Pattern(name="inn_10", regex=r"\b\d{10}\b", score=0.4),
            ],
            context=[
                "инн", "ИНН", "инн:", "ИНН:",
                "идентификационный номер", "налоговый номер",
                "ИНН физ", "ИНН юр",
            ],
        )

    def validate_result(self, pattern_text: str):
        return _validate_inn(pattern_text)


ru_inn_recognizer = RuInnRecognizer()


def _validate_snils(snils_str: str) -> bool:
    digits = [int(c) for c in snils_str if c.isdigit()]
    if len(digits) != 11:
        return False
    weights = [9, 8, 7, 6, 5, 4, 3, 2, 1]
    total = sum(w * d for w, d in zip(weights, digits[:9]))
    if total < 100:
        control = total
    elif total in (100, 101):
        control = 0
    else:
        control = total % 101
        if control in (100, 101):
            control = 0
    return control == digits[9] * 10 + digits[10]


class RuSnilsRecognizer(PatternRecognizer):
    def __init__(self):
        super().__init__(
            supported_entity="SNILS",
            supported_language="ru",
            name="RuSnilsRecognizer",
            patterns=[
                Pattern(name="snils_dashes", regex=r"\b\d{3}-\d{3}-\d{3}\s?\d{2}\b", score=0.85),
                Pattern(name="snils_spaces", regex=r"\b\d{3}\s\d{3}\s\d{3}\s?\d{2}\b", score=0.8),
            ],
            context=["снилс", "СНИЛС", "страховое свидетельство"],
        )

    def validate_result(self, pattern_text: str):
        return _validate_snils(pattern_text)


ru_snils_recognizer = RuSnilsRecognizer()

ru_passport_recognizer = PatternRecognizer(
    supported_entity="PASSPORT",
    supported_language="ru",
    name="RuPassportRecognizer",
    patterns=[
        Pattern(
            name="passport_series_number",
            regex=r"\b\d{2}\s?\d{2}\s?\d{6}\b",
            score=0.4,
        ),
        Pattern(
            name="passport_series_word_number",
            regex=r"\b\d{4}\s*(?:номер|н[оo]мер|№)\s*\d{6}\b",
            score=0.7,
        ),
    ],
    context=[
        "паспорт", "паспорта", "серия", "номер паспорта", "документ",
        "загранпаспорт", "паспортные данные", "серию", "удостоверение",
    ],
)

ru_email_recognizer = PatternRecognizer(
    supported_entity="EMAIL_ADDRESS",
    supported_language="ru",
    name="RuEmailRecognizer",
    patterns=[
        Pattern(
            name="email",
            regex=r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
            score=0.9,
        ),
    ],
)

ru_date_of_birth_recognizer = PatternRecognizer(
    supported_entity="DATE_OF_BIRTH",
    supported_language="ru",
    name="RuDateOfBirthRecognizer",
    patterns=[
        Pattern(
            name="date_dot",
            regex=r"\b\d{2}\.\d{2}\.\d{4}\b",
            score=0.4,
        ),
        Pattern(
            name="date_slash",
            regex=r"\b\d{2}/\d{2}/\d{4}\b",
            score=0.4,
        ),
    ],
    # ВАЖНО: Presidio (LemmaContextAwareEnhancer) сравнивает этот список с
    # ЛЕММАМИ слов текста. «родилась» в тексте видится как «родиться»,
    # «рождения» — как «рождение». Поэтому здесь обязаны быть начальные формы,
    # иначе буст не срабатывает и дату перебивает spaCy DATE_TIME → <PII>
    # (замер: 19 из 28 дат рождения уходили в <PII> ровно из-за этого).
    context=[
        "родиться", "рождение",  # леммы — их видит enhancer
        "д.р", "г.р",  # spaCy токенизирует «д.р.» как «д.р» (без хвостовой точки)
        "родился", "родилась", "родились", "рождения",
        "рожденный", "рожденная", "рождён",
        "дата рождения", "д.р.", "др", "ДР:", "год рождения",
        "дата рожд", "г.р.", "гр", "дата",
    ],
)

ru_card_number_recognizer = PatternRecognizer(
    supported_entity="CREDIT_CARD",
    supported_language="ru",
    name="RuCardNumberRecognizer",
    patterns=[
        Pattern(
            name="card_16",
            regex=r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b",
            score=0.7,
        ),
    ],
    context=["карта", "карты", "номер карты", "банковская"],
)


# Распознаватель PERSON — только наш дообученный ruBERT (models/person_ruBERT).
#
# Запасного распознавателя здесь намеренно НЕТ. Раньше стоял фолбэк на стоковую
# Natasha: если модели не было, он подхватывался молча, сервис выглядел исправным
# (health отвечал ok), но давал утечки ФИО — 0.94% (3 из 318) на тестовом наборе.
# Отсутствие модели должно быть громким, а не тихим, поэтому:
#   - модель есть  -> работает ruBERT;
#   - модели нет   -> PERSON не ищется вообще, а app/main.py отказывается стартовать
#                     (кроме явного ALLOW_NO_PERSON_MODEL=true для тестов/CI).
from app.person_transformer_recognizer import (  # noqa: E402 — намеренно рядом с логикой выбора
    PERSON_MODEL_DIR,
    PersonTransformerRecognizer,
    person_model_available,
)

ALL_RU_RECOGNIZERS = [
    ru_phone_recognizer,
    ru_inn_recognizer,
    ru_snils_recognizer,
    ru_passport_recognizer,
    ru_email_recognizer,
    ru_date_of_birth_recognizer,
    ru_card_number_recognizer,
]

if person_model_available():
    _person_recognizer = PersonTransformerRecognizer()
    ALL_RU_RECOGNIZERS.append(_person_recognizer)
else:
    _person_recognizer = None
    logger.warning(
        "Модель PERSON не найдена (PERSON_MODEL_DIR=%r) — ФИО распознаваться НЕ будут. "
        "Это допустимо только для тестов и CI.",
        PERSON_MODEL_DIR,
    )
