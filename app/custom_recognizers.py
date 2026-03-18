"""
Кастомные распознаватели для русских персональных данных.
Presidio по умолчанию не знает русские паттерны — добавляем их вручную.
"""

from presidio_analyzer import PatternRecognizer, Pattern


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

ru_inn_recognizer = PatternRecognizer(
    supported_entity="INN",
    supported_language="ru",
    name="RuInnRecognizer",
    patterns=[
        Pattern(
            name="inn_12",
            regex=r"\b\d{12}\b",
            score=0.5,
        ),
        Pattern(
            name="inn_10",
            regex=r"\b\d{10}\b",
            score=0.4,
        ),
    ],
    context=["инн", "ИНН", "инн:", "ИНН:", "идентификационный номер"],
)

ru_snils_recognizer = PatternRecognizer(
    supported_entity="SNILS",
    supported_language="ru",
    name="RuSnilsRecognizer",
    patterns=[
        Pattern(
            name="snils_dashes",
            regex=r"\b\d{3}-\d{3}-\d{3}\s?\d{2}\b",
            score=0.85,
        ),
        Pattern(
            name="snils_spaces",
            regex=r"\b\d{3}\s\d{3}\s\d{3}\s?\d{2}\b",
            score=0.8,
        ),
    ],
    context=["снилс", "СНИЛС", "страховое свидетельство"],
)

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
    context=["паспорт", "серия", "номер паспорта", "документ"],
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
    context=["родился", "рождения", "дата рождения", "д.р.", "дата", "родилась"],
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


ALL_RU_RECOGNIZERS = [
    ru_phone_recognizer,
    ru_inn_recognizer,
    ru_snils_recognizer,
    ru_passport_recognizer,
    ru_email_recognizer,
    ru_date_of_birth_recognizer,
    ru_card_number_recognizer,
]
