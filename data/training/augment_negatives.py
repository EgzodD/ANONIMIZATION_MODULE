"""
Аугментация обучающих данных негативами против ложных срабатываний PERSON.

Зачем: замер на негативах (tests/test_false_positives.py) и 2 xfail-теста
показали — модель метит как ФИО (а) топонимы, особенно многословные
(«Санкт-Петербург», «Нижний Новгород»), и (б) частые слова с заглавной
(«Штрихкод», «Инвентарный», «Талон»). Лечится дообучением с негативными
примерами, где эти слова размечены как `O`.

Что делает: генерирует негативы трёх видов и пишет их в ОТДЕЛЬНЫЕ файлы
(train_negatives.*, dev_negatives.*), НЕ трогая train/dev/test — так тест-сет
остаётся held-out и disjoint, а исходные данные не переписываются (обратимо).
Ноутбук дообучения читает train.conll + train_negatives.conll (см. cell «Разбор
CoNLL»).

  1) чистые топонимы            → все токены O
  2) частые слова с заглавной   → все токены O
  3) человек рядом с городом    → span только на ФИО, город = O
     (учит модель не «съедать» соседний топоним в PERSON — второй xfail)

Запуск:  python3 data/training/augment_negatives.py
"""
import json
import os
import random

from generate_dataset import gen_person, to_bio  # тот же генератор ФИО и BIO

random.seed(2026)
HERE = os.path.dirname(os.path.abspath(__file__))

# Топонимы: упор на многословные/дефисные — их модель путает с ФИО чаще всего.
TOPONYMS = [
    "Санкт-Петербург", "Нижний Новгород", "Ростов-на-Дону", "Великий Новгород",
    "Набережные Челны", "Ханты-Мансийск", "Йошкар-Ола", "Улан-Удэ",
    "Москва", "Екатеринбург", "Новосибирск", "Краснодар", "Казань", "Самара",
    "Челябинск", "Владивосток", "Красноярск", "Пермь", "Воронеж", "Волгоград",
    "Уфа", "Калининград", "Тюмень", "Иркутск", "Ярославль", "Омск", "Сочи",
    "Тольятти", "Барнаул", "Ставрополь", "Севастополь", "Магнитогорск",
]

# Частые существительные с заглавной (как в начале предложения) — драйверы FP.
NOUNS = [
    "Штрихкод", "Артикул", "Талон", "Квитанция", "Накладная", "Реквизиты",
    "Договор", "Заказ", "Позиция", "Гарантия", "Счёт", "Тариф", "Бонус",
    "Купон", "Промокод", "Каталог", "Ассортимент", "Реестр", "Ведомость",
    "Заявка", "Обращение", "Инвентарь", "Уведомление", "Сертификат",
]

# Шаблоны-негативы (spans пусты — скрывать нечего). {topo}/{noun} = слоты.
NEG_TEMPLATES_TOPO = [
    "Наш филиал в городе {topo} работает по будням.",
    "Доставка в город {topo} занимает два рабочих дня.",
    "Отделение в городе {topo} временно закрыто на учёт.",
    "Есть ли товар в наличии в городе {topo}?",
    "Пункт выдачи в городе {topo} переехал на новый адрес.",
    "Склад в городе {topo} отгружает заказы ежедневно.",
]
NEG_TEMPLATES_NOUN = [
    "{noun} оформлен, ожидайте уведомление.",
    "{noun} обработан в течение рабочего дня.",
    "Проверьте, пожалуйста, {noun} по вашей заявке.",
    "{noun} готов к выдаче на пункте самовывоза.",
    "{noun} принят в работу, статус обновится позже.",
]
# Шаблоны с ФИО рядом с городом — span только на человеке.
PERSON_TOPO_TEMPLATES = [
    "Клиент {person}, город {topo}, оформил заявку.",
    "Заявка от {person} из города {topo}.",
    "{person} уточняет наличие в городе {topo}.",
    "Менеджер {person} работает в городе {topo}.",
]


def build_person_topo(template):
    """Собирает текст с ФИО и городом; span проставляет только на ФИО."""
    person_text, _ = gen_person()
    topo = random.choice(TOPONYMS)
    text = ""
    spans = []
    pos = 0
    import re
    for m in re.finditer(r"\{(\w+)\}", template):
        text += template[pos:m.start()]
        slot = m.group(1)
        if slot == "person":
            start = len(text)
            text += person_text
            spans.append({"start": start, "stop": len(text), "type": "PERSON"})
        elif slot == "topo":
            text += topo
        pos = m.end()
    text += template[pos:]
    return {"text": text, "spans": spans}


def generate(n_topo=70, n_noun=70, n_person_topo=60):
    ex = []
    for _ in range(n_topo):
        t = random.choice(NEG_TEMPLATES_TOPO).replace("{topo}", random.choice(TOPONYMS))
        ex.append({"text": t, "spans": []})
    for _ in range(n_noun):
        t = random.choice(NEG_TEMPLATES_NOUN).replace("{noun}", random.choice(NOUNS))
        ex.append({"text": t, "spans": []})
    for _ in range(n_person_topo):
        ex.append(build_person_topo(random.choice(PERSON_TOPO_TEMPLATES)))
    random.shuffle(ex)
    return ex


def write(examples, folder, name):
    with open(os.path.join(folder, f"{name}.jsonl"), "w", encoding="utf-8") as f:
        for e in examples:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(os.path.join(folder, f"{name}.conll"), "w", encoding="utf-8") as f:
        for e in examples:
            for token, tag in to_bio(e["text"], e["spans"]):
                f.write(f"{token}\t{tag}\n")
            f.write("\n")


def main():
    ex = generate()
    random.shuffle(ex)
    n_dev = int(len(ex) * 0.15)
    dev, train = ex[:n_dev], ex[n_dev:]
    write(train, os.path.join(HERE, "train"), "train_negatives")
    write(dev, os.path.join(HERE, "dev"), "dev_negatives")
    n_person = sum(1 for e in ex if e["spans"])
    print(f"Негативов сгенерировано: {len(ex)}  (train {len(train)} / dev {len(dev)})")
    print(f"  чистых негативов (spans=[]): {len(ex) - n_person}")
    print(f"  с ФИО рядом с городом:       {n_person}")
    print("Файлы: train/train_negatives.{jsonl,conll}, dev/dev_negatives.{jsonl,conll}")


if __name__ == "__main__":
    main()
