"""
Кастомные распознаватели для русских персональных данных.
Presidio по умолчанию не знает русские паттерны — добавляем их вручную.
"""

import logging
import re

from presidio_analyzer import (
    EntityRecognizer,
    Pattern,
    PatternRecognizer,
    RecognizerResult,
)

logger = logging.getLogger(__name__)


class KeywordAnchoredRecognizer(EntityRecognizer):
    """Ищет номер (ИНН/СНИЛС/паспорт), стоящий РЯДОМ с ключевым словом.

    Маскирует только сам номер (группа 1, если она есть — иначе всё совпадение);
    ключевое слово («ИНН», «СНИЛС», «паспорт») остаётся в тексте. Контрольная
    сумма НЕ требуется: если рядом написано «ИНН», число почти наверняка ИНН, и
    пропустить его (утечка ПДн) хуже, чем один раз перемаскировать. Благодаря
    этому ловятся «грязные» форматы (пробелы, №, дефисы, точки, тире) и тестовые
    (невалидные по контрольной сумме) номера, которые чистый regex+checksum
    пропускал.

    allowed_digit_counts — сколько цифр допустимо в номере (например {10, 12}
    для ИНН, {11} для СНИЛС). Совпадения с другим числом цифр отбрасываются, что
    отсекает мусор при жадном захвате разделителей.
    """

    def __init__(self, entity, patterns, allowed_digit_counts=None,
                 score=0.9, name=None):
        self._rx = [re.compile(p, re.IGNORECASE) for p in patterns]
        self._allowed = set(allowed_digit_counts or ())
        self._score = score
        self._entity = entity
        super().__init__(
            supported_entities=[entity],
            supported_language="ru",
            name=name or f"{entity}AnchoredRecognizer",
        )

    def load(self) -> None:  # нечего загружать
        pass

    def analyze(self, text, entities, nlp_artifacts=None):
        if self._entity not in entities:
            return []
        out = []
        for rx in self._rx:
            for m in rx.finditer(text):
                grp = 1 if rx.groups else 0
                start, end = m.span(grp)
                if self._allowed:
                    digits = sum(c.isdigit() for c in text[start:end])
                    if digits not in self._allowed:
                        continue
                out.append(
                    RecognizerResult(
                        entity_type=self._entity,
                        start=start,
                        end=end,
                        score=self._score,
                    )
                )
        return out


# Разделители, встречающиеся ВНУТРИ номера ПДн: пробел, точка, дефис, тире,
# среднее тире, слэш. НЕ включаем буквы/запятые/№ (кроме отдельных мест) —
# это границы номера.
_SEP = r"[\s.\-–—/]"

# Промежуток между ключевым словом и номером: допускает склейку без пробела
# («ИНН7712…»), обычные разделители и до 2 живых слов (родит. падеж:
# «ИНН гражданина …», «СНИЛС сотрудника: …»). НЕ используем \b после ключа —
# в Python re граница буква→цифра не срабатывает, и склейка утекала.
# Слова-связки НЕ пересекают конец предложения (.!?): иначе «нет ИНН. Мой заказ
# 555…» маскировал бы номер заказа из СЛЕДУЮЩЕГО предложения как ИНН.
_GAP = r"(?:[^\w.!?\n]+\w+){0,2}?[\s:№.\-–—]{0,6}"

ru_phone_recognizer = PatternRecognizer(
    supported_entity="PHONE_NUMBER",
    supported_language="ru",
    name="RuPhoneRecognizer",
    patterns=[
        # (?<!\d) — не начинать матч С СЕРЕДИНЫ длинного числа (иначе «8» внутри
        # ИНН/паспорта давало частичную маску «7<PHONE>» и утечку первой цифры)
        Pattern(
            name="ru_phone_plus7",
            regex=r"(?<!\d)\+7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)",
            score=0.9,
        ),
        Pattern(
            name="ru_phone_8",
            regex=r"(?<!\d)8[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)",
            score=0.85,
        ),
        # Российский мобильный: 7/8 + код оператора 9XX + 7 цифр, любые
        # разделители. Требование «2-я цифра = 9» отсекает случайные 11-значные
        # ID (номер заказа 78123456789 — не мобильный), но ловит «79161234567»,
        # «7-916-123 45 67», «89268804109».
        Pattern(
            name="ru_phone_mobile9",
            regex=r"(?<!\d)[78][\s\-]?9(?:[\s\-]?\d){9}(?!\d)",
            score=0.6,
        ),
        # голый мобильный без кода страны: 9XXXXXXXXX (10 цифр, начинается на 9).
        # Заменяет снятый встроенный presidio PhoneRecognizer для этого формата,
        # но НЕ ловит номера заказа/трека/договора (они не начинаются на 9).
        Pattern(name="ru_phone_bare_mobile", regex=r"(?<!\d)9\d{9}(?!\d)", score=0.5),
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
        # «серия … номер …» — есть слово «номер»/№, поэтому не голое число
        Pattern(
            name="passport_series_word_number",
            regex=r"\b\d{4}\s*(?:номер|н[оo]мер|№)\s*\d{6}\b",
            score=0.7,
        ),
    ],
    # Голый context-free паттерн «\d{2} \d{2} \d{6}» (score 0.4) УБРАН: он метил
    # любое 10-значное число как паспорт (номер заказа/трека/договора → <PASSPORT>,
    # ~перемаскирование). Паспорт рядом с ключевым словом покрывает якорный
    # ru_passport_anchored; отдельно стоящий 10-значный без контекста — не паспорт.
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

# Обфусцированный e-mail: «ivan собака mail точка ru», «user(at)dom[dot]com».
# Люди так диктуют почту, чтобы обойти маскирование. Ловим «@»-часть (собака/at)
# + «.»-часть (точка/dot) в любом написании; маскируем всё выражение.
_AT = r"(?:@|\(\s*at\s*\)|\[\s*at\s*\]|\bat\b|собак[аеу]|\(\s*собак[аеу]\s*\))"
_DOT = r"(?:\.|\(\s*dot\s*\)|\[\s*dot\s*\]|\bdot\b|точк[аеу]|\(\s*точк[аеу]\s*\)|\[\s*точк[аеу]\s*\])"
# Локальная часть может быть продиктована как 1-3 слова через пробел
# («ivan petrov собака …»), иначе первое слово утекало.
_LOCAL = r"[\w.+\-]+(?:\s+[\w.+\-]+){0,2}"
ru_obfuscated_email_recognizer = PatternRecognizer(
    supported_entity="EMAIL_ADDRESS",
    supported_language="ru",
    name="RuObfuscatedEmailRecognizer",
    patterns=[
        Pattern(
            name="email_obfuscated",
            regex=rf"{_LOCAL}\s*{_AT}\s*[\w\-]+\s*{_DOT}\s*[A-Za-z]{{2,6}}",
            score=0.85,
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
            regex=r"\b\d{4}[\s\-.]?\d{4}[\s\-.]?\d{4}[\s\-.]?\d{4}\b",
            score=0.7,
        ),
        # 16 цифр с произвольными разделителями, в т.ч. 8 пар и точки:
        # «52 19 44 70 10 83 65 24», «5469_2103_4812_6137», «5469.2103.4812.6137»
        Pattern(
            name="card_16_loose",
            regex=r"\b\d{2}(?:[\s\-_.]?\d{2}){7}\b",
            score=0.55,
        ),
    ],
    context=["карта", "карты", "номер карты", "банковская", "мир", "виза"],
)

# Карты нестандартной длины (Maestro 13, Amex 15, UnionPay 17-19) рядом с
# ключевым словом карты — обычные 16-значные паттерны их не ловят.
ru_card_anchored = KeywordAnchoredRecognizer(
    entity="CREDIT_CARD",
    patterns=[
        rf"(?:карт[а-яё]*|maestro|amex|american\s+express|mastercard|виз[аы]|visa|"
        rf"unionpay){_GAP}(\d[\d\s\-.]{{10,25}}\d)",
    ],
    allowed_digit_counts={12, 13, 14, 15, 16, 17, 18, 19},
    score=0.8,
    name="RuCardAnchoredRecognizer",
)


# Распознаватель PERSON — только наш дообученный ruBERT (models/person_ruBERT).
#
# Отдельного фолбэка на Natasha здесь намеренно НЕТ (раньше он подхватывался
# молча и давал утечки ФИО — 0.94%). Отсутствие ruBERT должно быть громким:
#   - модель есть  -> работает ruBERT (авторитетный источник PERSON);
#   - модели нет   -> app/main.py отказывается стартовать (кроме
#                     ALLOW_NO_PERSON_MODEL=true для тестов/CI).
# ВАЖНО: presidio по умолчанию регистрирует встроенный SpacyRecognizer из
# ru_core_news_lg, и он ТОЖЕ метит PERSON (score 0.85). Это дополнительный
# (не заменяющий) фолбэк: ruBERT-спаны имеют пол score 0.9 и всегда перебивают
# spaCy на пересечении (см. person_transformer_recognizer._clean_person_span и
# пол score), а spaCy лишь добавляет непокрытые ruBERT имена. С ALLOW_NO_PERSON_MODEL
# spaCy остаётся единственным (слабым) источником PERSON — для теста это приемлемо.
from app.person_transformer_recognizer import (  # noqa: E402 — намеренно рядом с логикой выбора
    PERSON_MODEL_DIR,
    PersonTransformerRecognizer,
    person_model_available,
)

# --- Якорные распознаватели: номер РЯДОМ с ключевым словом ---------------------
# Закрывают утечки «грязных» форматов, которые чистый regex+checksum пропускал:
#   ИНН 77-0123-456789 / 77 05 31 24 68 90 / 50.1234.567890 / №771298765432
#   СНИЛС 112-233-445-95 / 14567890123 / 143—721—908 36 / № 165-904-321 88
#   Паспорт: серия 40 12, номер 583 214 / 45-21 №883 104 / 46 07 № 381924
# Номер маскируется целиком, ключевое слово остаётся. Контрольная сумма не нужна.

# число из 10/12 цифр с любыми внутренними разделителями (жадно, конец — цифра)
_INN_NUM = r"\d[\d\s.\-–—]{6,40}\d"
ru_inn_anchored = KeywordAnchoredRecognizer(
    entity="INN",
    patterns=[
        rf"ИНН{_GAP}({_INN_NUM})",
        rf"идентификационн\w*\s+номер\w*{_GAP}({_INN_NUM})",
    ],
    allowed_digit_counts={10, 12},
    score=0.9,
    name="RuInnAnchoredRecognizer",
)

_SNILS_NUM = r"\d[\d\s.\-–—]{6,30}\d"
ru_snils_anchored = KeywordAnchoredRecognizer(
    entity="SNILS",
    patterns=[
        rf"СНИЛС{_GAP}({_SNILS_NUM})",
        rf"страхов\w*\s+свидетельств\w*{_GAP}({_SNILS_NUM})",
    ],
    allowed_digit_counts={11},
    score=0.9,
    name="RuSnilsAnchoredRecognizer",
)

# Паспорт: серия (4 цифры) + номер (6 цифр) в любых форматах.
_PASS_NUM = r"(?:\d{2}[\s\-/]?\d{2}[\s\-/№.]{0,4}\d{3}[\s\-/]?\d{3}|\d{10})"
ru_passport_anchored = KeywordAnchoredRecognizer(
    entity="PASSPORT",
    patterns=[
        # «паспорт [РФ] [серия] <номер>» + склейка + до 2 слов между
        rf"паспорт[а-яё]*(?:\s*рф)?{_GAP}(?:сери[яию]\W{{0,4}})?№?\s*({_PASS_NUM})",
        # «серия 40 12, номер 583 214» / «серия № 4513, номер № 908172» — маска целиком
        r"(сери[яию]\W{0,4}№?\s*\d{2}\s?\d{2}\W{0,14}(?:номер|№)\W{0,4}№?\s*\d{3}\s?\d{3})",
        # обратный порядок: «номер 583214, серия 4012»
        r"((?:номер|№)\W{0,4}№?\s*\d{3}\s?\d{3}\W{0,14}сери[яию]\W{0,4}№?\s*\d{2}\s?\d{2})",
    ],
    allowed_digit_counts={10},
    score=0.85,
    name="RuPassportAnchoredRecognizer",
)

# Дата рождения по якорю: «дата рождения … 17021992» (в т.ч. без разделителей),
# допускаем до 3 слов между ключом и числом («записана как»).
ru_dob_anchored = KeywordAnchoredRecognizer(
    entity="DATE_OF_BIRTH",
    patterns=[
        r"дата\s+рожд\w*(?:\W+\w+){0,3}?\W{0,5}"
        r"(\d{2}[.\-/]?\d{2}[.\-/]?\d{4}|\d{8})",
    ],
    allowed_digit_counts={8},
    score=0.7,
    name="RuDobAnchoredRecognizer",
)

ALL_RU_RECOGNIZERS = [
    ru_phone_recognizer,
    ru_inn_recognizer,
    ru_inn_anchored,
    ru_snils_recognizer,
    ru_snils_anchored,
    ru_passport_recognizer,
    ru_passport_anchored,
    ru_email_recognizer,
    ru_obfuscated_email_recognizer,
    ru_date_of_birth_recognizer,
    ru_dob_anchored,
    ru_card_number_recognizer,
    ru_card_anchored,
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
