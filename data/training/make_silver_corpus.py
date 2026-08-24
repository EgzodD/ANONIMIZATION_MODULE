"""
Генератор НЕразмеченного silver-корпуса для дистилляции (Track B).

Задача: дать учителю (сильный ru-NER) разнообразный русский текст «как в чатах
поддержки», который он разметит на PERSON/O. Метки НЕ ставим — их поставит
учитель в Colab (см. DISTILLATION_RECIPE.md). Здесь только РАЗНООБРАЗИЕ:
имена в падежах/форматах/регистре, склейки с соседним словом, топонимы, улицы,
орг-названия, частые слова — то, на чём модель ошибалась в реальном прогоне.

Важно: это НЕ обучающие метки, а вход для учителя. Held-out test не используется.

Запуск:  python3 data/training/make_silver_corpus.py [N]   (по умолчанию 8000)
Выход:   data/training/silver/corpus.txt  (одно предложение на строку)
"""
import os
import random
import sys

from generate_dataset import gen_person
from augment_negatives import (
    NEG_TEMPLATES_NOUN,
    NEG_TEMPLATES_ORG,
    NEG_TEMPLATES_STREET,
    NEG_TEMPLATES_TOPO,
    NOUNS,
    ORGS,
    STREETS,
    TOPONYMS,
)

random.seed(2026)
HERE = os.path.dirname(os.path.abspath(__file__))

# Предложения с ФИО (имя = слот {p}); учитель разметит имя как PERSON.
CHAT_TEMPLATES = [
    "Здравствуйте, меня зовут {p}, нужна помощь с кабинетом.",
    "Добрый день, это {p}, обращаюсь по поводу заказа.",
    "Я {p}, не приходит SMS для входа.",
    "На связи {p}, уточните статус доставки.",
    "Клиент {p} просит перезвонить после обеда.",
    "Передайте менеджеру, что звонил {p}.",
    "{p} оставил обращение вчера вечером.",
    "Оформите возврат на имя {p}.",
    "Спасибо, {p} записала заявку.",
    "По доверенности действует {p}.",
    "Заявку подал {p} из соседнего отдела.",
    "Прошу связаться с {p} по рабочему номеру.",
]

# Слова-филлеры, к которым имя иногда «прилипает» без пробела (реальный кейс).
GLUE_FILLERS = ["спасибо", "здравствуйте", "привет", "ок", "алло", "добрый день,"]


def sent_with_name():
    p, _ = gen_person()
    t = random.choice(CHAT_TEMPLATES).replace("{p}", p)
    # 12% — склейка филлера с именем без пробела (СпасибоИван …)
    if random.random() < 0.12:
        filler = random.choice(GLUE_FILLERS).rstrip(", ")
        cap = p[:1].upper() + p[1:]
        t = f"{filler}{cap} на связи."
    return t


def sent_negative():
    kind = random.random()
    if kind < 0.30:
        return random.choice(NEG_TEMPLATES_TOPO).replace("{topo}", random.choice(TOPONYMS))
    if kind < 0.55:
        return random.choice(NEG_TEMPLATES_STREET).replace("{street}", random.choice(STREETS))
    if kind < 0.78:
        return random.choice(NEG_TEMPLATES_NOUN).replace("{noun}", random.choice(NOUNS))
    return random.choice(NEG_TEMPLATES_ORG).replace("{org}", random.choice(ORGS))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    out_dir = os.path.join(HERE, "silver")
    os.makedirs(out_dir, exist_ok=True)
    lines = []
    for _ in range(n):
        # 55% — с именем, 45% — негативы (топонимы/улицы/слова/орг)
        lines.append(sent_with_name() if random.random() < 0.55 else sent_negative())
    random.shuffle(lines)
    path = os.path.join(out_dir, "corpus.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Silver-корпус: {len(lines)} предложений -> {path}")
    print("Примеры:")
    for s in lines[:6]:
        print("  ", s)


if __name__ == "__main__":
    main()
