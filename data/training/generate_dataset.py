"""
Генератор размеченного датасета для дообучения Natasha NER.

Создаёт синтетические тексты в стиле чатов поддержки с автоматической разметкой
всех типов ПДн. Имена склоняются по падежам (pymorphy3), ИНН/СНИЛС проходят
контрольную сумму ФНС/ПФР. Разметка строится автоматически по позициям вставки —
ручная разметка не требуется.

Выход:
  train/  (70%)  — обучающая выборка
  dev/    (15%)  — валидация во время обучения
  test/   (15%)  — финальная оценка

Форматы:
  *.conll  — токены с BIO-тегами (token \t TAG)
  *.jsonl  — спаны {"text": ..., "spans": [{"start","stop","type"}]}
"""

import json
import os
import random

import pymorphy3
from razdel import tokenize

random.seed(42)
morph = pymorphy3.MorphAnalyzer()

HERE = os.path.dirname(os.path.abspath(__file__))

# ════════════════════════════════════════════════════════════════════
#  БАЗЫ ИМЁН
# ════════════════════════════════════════════════════════════════════
MALE_NAMES = [
    "Иван", "Дмитрий", "Сергей", "Александр", "Андрей", "Алексей", "Михаил",
    "Николай", "Павел", "Виктор", "Григорий", "Юрий", "Артём", "Олег",
    "Роман", "Владимир", "Денис", "Максим", "Егор", "Кирилл",
]
FEMALE_NAMES = [
    "Наталья", "Ольга", "Елена", "Мария", "Светлана", "Ирина", "Татьяна",
    "Анна", "Екатерина", "Юлия", "Алёна", "Дарья", "Виктория", "Людмила",
    "Галина", "Оксана", "Полина", "Марина", "Вера", "Надежда",
]
MALE_PATR = [
    "Иванович", "Дмитриевич", "Сергеевич", "Александрович", "Андреевич",
    "Алексеевич", "Михайлович", "Николаевич", "Павлович", "Викторович",
    "Анатольевич", "Игоревич", "Борисович", "Петрович", "Васильевич",
]
FEMALE_PATR = [
    "Ивановна", "Дмитриевна", "Сергеевна", "Александровна", "Андреевна",
    "Алексеевна", "Михайловна", "Николаевна", "Павловна", "Викторовна",
    "Анатольевна", "Игоревна", "Борисовна", "Петровна", "Васильевна",
]
# Фамилии в базовой (мужской) форме; женская образуется добавлением "а"
SURNAMES_M = [
    "Петров", "Смирнов", "Кузнецов", "Попов", "Васильев", "Соколов",
    "Михайлов", "Новиков", "Фёдоров", "Морозов", "Волков", "Алексеев",
    "Лебедев", "Семёнов", "Егоров", "Павлов", "Козлов", "Степанов",
    "Орлов", "Макаров", "Никитин", "Захаров", "Зайцев", "Соловьёв",
]

CASES = ["nomn", "gent", "datv", "accs", "ablt", "loct"]


def _inflect(word, case, gender):
    """Склоняет слово (имя/фамилия/отчество) в нужный падеж с учётом пола."""
    for pp in morph.parse(word):
        grams = pp.tag.grammemes
        if {"Surn", "Name", "Patr"} & grams or pp.tag.POS == "NOUN":
            inf = pp.inflect({case, gender})
            if inf:
                return inf.word.capitalize()
    inf = morph.parse(word)[0].inflect({case})
    return inf.word.capitalize() if inf else word


# ════════════════════════════════════════════════════════════════════
#  ГЕНЕРАТОРЫ ПДн → возвращают (строка, тип_сущности)
# ════════════════════════════════════════════════════════════════════
def gen_person():
    """Случайное ФИО в случайном падеже и формате. Может быть в нижнем регистре."""
    male = random.random() < 0.5
    gender = "masc" if male else "femn"
    first = random.choice(MALE_NAMES if male else FEMALE_NAMES)
    patr = random.choice(MALE_PATR if male else FEMALE_PATR)
    surn_base = random.choice(SURNAMES_M)
    surn = surn_base if male else surn_base + "а"

    case = random.choice(CASES)
    f = _inflect(first, case, gender)
    p = _inflect(patr, case, gender)
    s = _inflect(surn, case, gender)

    fmt = random.choice([
        "ФИО",   # Иван Петрович Смирнов
        "ФамИО", # Смирнов Иван Петрович
        "ИФ",    # Иван Смирнов
        "ФИ",    # Смирнов Иван
        "ИО",    # Иван Петрович
        "ИниФ",  # И.П. Смирнов
    ])
    if fmt == "ФИО":
        text = f"{f} {p} {s}"
    elif fmt == "ФамИО":
        text = f"{s} {f} {p}"
    elif fmt == "ИФ":
        text = f"{f} {s}"
    elif fmt == "ФИ":
        text = f"{s} {f}"
    elif fmt == "ИО":
        text = f"{f} {p}"
    else:  # ИниФ
        text = f"{f[0]}.{p[0]}. {s}"

    # 20% — нижний регистр (имитация неаккуратного ввода)
    if random.random() < 0.20:
        text = text.lower()
    return text, "PERSON"


def gen_phone():
    a = random.choice(["915", "916", "903", "905", "925", "999", "495", "812", "800"])
    b = random.randint(100, 999)
    c = random.randint(10, 99)
    d = random.randint(10, 99)
    fmt = random.choice([
        f"+7 {a} {b} {c} {d}",
        f"+7({a}){b}-{c}-{d}",
        f"8 ({a}) {b}-{c}-{d}",
        f"+7{a}{b}{c}{d}",
        f"8-{a}-{b}-{c}-{d}",
    ])
    return fmt, "PHONE_NUMBER"


def gen_email():
    user = random.choice([
        "ivan.petrov", "natasha.k", "s.ivanova", "a.belov", "client123",
        "p.orlov", "m.makarova", "user.test", "d.smirnov", "o.fedorova",
    ])
    dom = random.choice(["yandex.ru", "gmail.com", "mail.ru", "inbox.ru",
                          "company.ru", "test.org", "bk.ru", "list.ru"])
    return f"{user}@{dom}", "EMAIL_ADDRESS"


def gen_inn():
    """Генерирует ИНН (10 или 12 цифр), проходящий контрольную сумму ФНС."""
    if random.random() < 0.5:
        base = [random.randint(0, 9) for _ in range(9)]
        w = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        c = sum(x * y for x, y in zip(w, base)) % 11 % 10
        return "".join(map(str, base + [c])), "INN"
    base = [random.randint(0, 9) for _ in range(10)]
    w1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    w2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    c1 = sum(x * y for x, y in zip(w1, base)) % 11 % 10
    c2 = sum(x * y for x, y in zip(w2, base + [c1])) % 11 % 10
    return "".join(map(str, base + [c1, c2])), "INN"


def gen_snils():
    """Генерирует СНИЛС, проходящий контрольную сумму ПФР."""
    base = [random.randint(0, 9) for _ in range(9)]
    w = [9, 8, 7, 6, 5, 4, 3, 2, 1]
    total = sum(x * y for x, y in zip(w, base))
    if total < 100:
        ctl = total
    elif total in (100, 101):
        ctl = 0
    else:
        ctl = total % 101
        if ctl in (100, 101):
            ctl = 0
    s = "".join(map(str, base))
    sep = random.choice(["-", " "])
    return f"{s[:3]}{sep}{s[3:6]}{sep}{s[6:9]} {ctl:02d}", "SNILS"


def gen_passport():
    series = f"{random.randint(10,99)} {random.randint(10,99)}"
    number = f"{random.randint(100000, 999999)}"
    return f"{series} {number}", "PASSPORT"


def gen_dob():
    d = random.randint(1, 28)
    m = random.randint(1, 12)
    y = random.randint(1955, 2005)
    sep = random.choice([".", "/"])
    return f"{d:02d}{sep}{m:02d}{sep}{y}", "DATE_OF_BIRTH"


def gen_card():
    parts = [random.choice(["4276", "5469", "2202", "4081", "5536"])]
    parts += [f"{random.randint(0,9999):04d}" for _ in range(3)]
    sep = random.choice([" ", "-"])
    return sep.join(parts), "CREDIT_CARD"


# ════════════════════════════════════════════════════════════════════
#  ШАБЛОНЫ ПРЕДЛОЖЕНИЙ
#  {person}, {phone}, ... — слоты, заменяются на сгенерированные ПДн.
#  Текст вокруг слотов имитирует реальные чаты поддержки.
# ════════════════════════════════════════════════════════════════════
TEMPLATES = [
    "Здравствуйте, меня зовут {person}, прошу помочь с заявкой.",
    "Клиент {person} обратился по вопросу кредита.",
    "Обращение от {person}, телефон для связи {phone}.",
    "Прошу записать: {person}, {phone}, {email}.",
    "Добрый день, это {person}. Мой ИНН {inn}.",
    "Уважаемый {person}! Ваш ИНН {inn} подтверждён.",
    "Я {person}, мой СНИЛС {snils}, родилась {dob}.",
    "Клиент: {person}, ИНН {inn}, СНИЛС {snils}.",
    "Свяжитесь с {person} по телефону {phone}.",
    "Перевод на карту {card} получателю {person}.",
    "Запись на приём: {person}, дата рождения {dob}.",
    "Контакт: {person}, {phone}, {email}.",
    "{person} обратился с паспортом {passport} и картой {card}.",
    "Отправьте документы на почту {email}, получатель {person}.",
    "Заявка №{rand}: {person}, паспорт {passport}.",
    "Звонил {person}, оставил номер {phone}.",
    "Регистрация: {person}, д.р. {dob}, почта {email}.",
    "Менеджер {person} перезвонит на {phone}.",
    "Данные клиента {person}: ИНН {inn}, паспорт {passport}.",
    "Оформляю на {person}, карта оплаты {card}.",
    "По вопросу {person} — СНИЛС {snils}, телефон {phone}.",
    "Заказ принят. Клиент {person}, email {email}.",
    "Прошу проверить ИНН {inn} клиента {person}.",
    "Договор на имя {person}, дата рождения {dob}.",
    "Жалоба от {person}, контактный {phone}, почта {email}.",
    # Шаблоны без ПДн — чтобы модель не находила лишнего
    "Спасибо за обращение, ваш вопрос обрабатывается.",
    "Здравствуйте, чем могу помочь?",
    "Заявка зарегистрирована, ожидайте ответа в течение дня.",
    "Уточните, пожалуйста, детали вашего запроса.",
    "Документы приняты, проверка займёт два рабочих дня.",
]

SLOT_GENERATORS = {
    "person": gen_person,
    "phone": gen_phone,
    "email": gen_email,
    "inn": gen_inn,
    "snils": gen_snils,
    "passport": gen_passport,
    "dob": gen_dob,
    "card": gen_card,
}

import re
SLOT_RE = re.compile(r"\{(\w+)\}")


def build_example(template):
    """Подставляет ПДн в шаблон, возвращает (текст, список спанов)."""
    text = ""
    spans = []
    pos = 0
    for m in SLOT_RE.finditer(template):
        # текст до слота
        text += template[pos:m.start()]
        slot = m.group(1)
        if slot == "rand":
            text += str(random.randint(1000, 9999))
        elif slot in SLOT_GENERATORS:
            value, etype = SLOT_GENERATORS[slot]()
            start = len(text)
            text += value
            stop = len(text)
            spans.append({"start": start, "stop": stop, "type": etype})
        else:
            text += m.group(0)
        pos = m.end()
    text += template[pos:]
    return text, spans


# ════════════════════════════════════════════════════════════════════
#  BIO-РАЗМЕТКА (CoNLL)
# ════════════════════════════════════════════════════════════════════
def to_bio(text, spans):
    """Токенизирует текст (razdel) и присваивает BIO-теги по спанам."""
    rows = []
    for tok in tokenize(text):
        tag = "O"
        for sp in spans:
            if tok.start >= sp["start"] and tok.stop <= sp["stop"]:
                prefix = "B" if tok.start == sp["start"] else "I"
                tag = f"{prefix}-{sp['type']}"
                break
        rows.append((tok.text, tag))
    return rows


# ════════════════════════════════════════════════════════════════════
#  ГЕНЕРАЦИЯ И ЗАПИСЬ
# ════════════════════════════════════════════════════════════════════
def generate(n_total=1000):
    examples = []
    for _ in range(n_total):
        tmpl = random.choice(TEMPLATES)
        text, spans = build_example(tmpl)
        examples.append({"text": text, "spans": spans})
    random.shuffle(examples)
    return examples


def write_split(examples, folder, name):
    os.makedirs(folder, exist_ok=True)
    # JSONL (спаны)
    with open(os.path.join(folder, f"{name}.jsonl"), "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    # CoNLL (BIO)
    with open(os.path.join(folder, f"{name}.conll"), "w", encoding="utf-8") as f:
        for ex in examples:
            for token, tag in to_bio(ex["text"], ex["spans"]):
                f.write(f"{token}\t{tag}\n")
            f.write("\n")


def main():
    n_total = 1000
    examples = generate(n_total)

    n_train = int(n_total * 0.70)
    n_dev = int(n_total * 0.15)
    train = examples[:n_train]
    dev = examples[n_train:n_train + n_dev]
    test = examples[n_train + n_dev:]

    write_split(train, os.path.join(HERE, "train"), "train")
    write_split(dev, os.path.join(HERE, "dev"), "dev")
    write_split(test, os.path.join(HERE, "test"), "test")

    # Статистика
    from collections import Counter
    counts = Counter()
    for ex in examples:
        for sp in ex["spans"]:
            counts[sp["type"]] += 1

    print(f"Сгенерировано примеров: {n_total}")
    print(f"  train: {len(train)}")
    print(f"  dev:   {len(dev)}")
    print(f"  test:  {len(test)}")
    print("\nСущностей по типам (всего):")
    for t, c in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {t:<16} {c}")
    print(f"\nВсего сущностей: {sum(counts.values())}")


if __name__ == "__main__":
    main()
