# Track B — дистилляция модели PERSON: «тяжело учим → легко крутим»

**Цель:** снизить ложные срабатывания PERSON (топонимы «Королёв», улицы «Тестовая»,
слова «Банковская», орг-названия «Ромашка») и поднять recall ФИО — **не увеличивая
модель**. Инференс должен остаться лёгким.

**Что дистиллируем и что НЕТ:**
- Модель отвечает ТОЛЬКО за `PERSON` (ФИО). ИНН/СНИЛС/паспорт/телефон/карта/e-mail/ДР
  распознаются regex-ами в `app/custom_recognizers.py` — их дистилляция НЕ касается.
- **Ученик (student) = `cointegrated/rubert-tiny2`** (~29M параметров, MIT) — остаётся
  как есть, его и грузит прод. Легче некуда.
- «Большие вычисления» уходят в УЧИТЕЛЯ и в объём данных, а не в размер ученика.

---

## 1. Учитель (teacher) — только пермиссивная лицензия (модуль на продажу)

Учитель используется лишь для РАЗМЕТКИ данных при обучении и в прод НЕ попадает, но
для чистоты прав берём permissive:

| Кандидат | Лицензия | Комментарий |
|---|---|---|
| **DeepPavlov `ner_rus_bert`** | Apache-2.0 | сильный русский NER, рекомендую как учителя |
| `ru_core_news_lg` (spaCy) | MIT | уже в проекте, послабее, но 0 зависимостей |
| Natasha / Slovnet | MIT | быстрый, среднее качество |

Избегать: модели с GPL/AGPL/некоммерческими лицензиями (см. [[commercial-license-constraint]]).

---

## 2. Подход — response-based дистилляция (silver-labels)

Классический logit-KD требует одинаковых токенизаторов у учителя и ученика — у нас они
разные (BERT-teacher vs rubert-tiny2). Поэтому используем **пословную мягкую разметку**,
она tokenizer-agnostic и не связывает лицензию учителя с весами ученика (используются
только ПРЕДСКАЗАНИЯ, не веса):

```
1. Собираем большой НЕразмеченный корпус русского текста «как в чатах поддержки»
   (наши шаблоны + разнообразие: падежи, диктовка, склейки, топонимы, орг-названия).
2. Учитель размечает его на уровне СЛОВ: p(PERSON) для каждого слова  → «silver».
3. Ученик (rubert-tiny2) учится на:
     - GOLD: наш train.conll + train_negatives.conll  (жёсткие метки, вес 1.0)
     - SILVER: корпус, размеченный учителем           (мягкие метки, вес 0.3–0.5)
4. Валидация — на dev; финальный замер — на held-out test (не трогаем!).
```

Это гибрид дистилляции и self-training. Если позже возьмём учителя той же архитектуры —
можно перейти на настоящий logit-KD (KL-дивергенция по логитам), код в §5.

---

## 3. Данные (готовы в репозитории)

| Файл | Что | Кол-во |
|---|---|---|
| `train/train.conll` | gold-позитивы (ФИО в падежах) | 700 |
| `train/train_negatives.conll` | gold-негативы (топонимы/улицы/слова/орг + ФИО-рядом-с-городом) | 298 |
| `dev/dev*.conll` | валидация | 150 + 52 |
| `test/test.jsonl` | held-out, **не использовать в обучении** | 150 |

Негативы расширены под реальные FP (`augment_negatives.py`: +улицы, +орг-названия,
+слова «Банковская/Спам/Латинская», +города Королёв/Ясиноватая). Перегенерация:
```bash
python3 data/training/augment_negatives.py   # disjoint с test проверяется
```

Для silver-корпуса — нагенерировать 5–10k предложений теми же шаблонами + вариативность
(без ручной разметки, метки поставит учитель).

---

## 4. Обучение ученика (Colab, GPU) — набросок

```python
# --- учитель размечает silver-корпус (пример на DeepPavlov) ---
# pip install deeppavlov; python -m deeppavlov install ner_rus_bert
from deeppavlov import build_model
teacher = build_model("ner_rus_bert", download=True)

def silver_label(sentences):        # -> список [(word, 'PERSON'|'O'), ...]
    out = []
    for toks, tags in zip(*teacher(sentences)):
        out.append([(w, "PERSON" if t.endswith("PER") else "O") for w, t in zip(toks, tags)])
    return out

# --- ученик: token-classification на rubert-tiny2 ---
from transformers import (AutoTokenizer, AutoModelForTokenClassification,
                          TrainingArguments, Trainer)
STUDENT = "cointegrated/rubert-tiny2"
tok = AutoTokenizer.from_pretrained(STUDENT)
model = AutoModelForTokenClassification.from_pretrained(
    STUDENT, num_labels=3, id2label={0:"O",1:"B-PERSON",2:"I-PERSON"})

# gold (вес 1.0) + silver (вес 0.3) — объединяем с полем sample_weight,
# в кастомном Trainer домножаем per-token loss на вес источника.
args = TrainingArguments(
    output_dir="person_ruBERT_distilled",
    num_train_epochs=12,            # «тяжело учим» — больше эпох
    per_device_train_batch_size=32,
    learning_rate=5e-5,
    eval_strategy="epoch",
    metric_for_best_model="f2",     # приоритет recall (пропуск ФИО = утечка)
    load_best_model_at_end=True,
)
# Trainer с взвешенным loss (gold>silver) — см. существующий colab-ноутбук как основу.
```

Итог: `person_ruBERT_distilled/` (config.json + model.safetensors + tokenizer*) —
тот же лёгкий формат, что грузит прод.

---

## 5. Опционально — настоящий logit-KD (если учитель = та же архитектура)

Если взять учителем более крупный rubert (та же токенизация), loss ученика:
`L = α·CE(hard) + (1−α)·T²·KL(softmax(student/T), softmax(teacher/T))`, T≈2, α≈0.5.
Это даёт больше сигнала, чем silver-метки, но требует совпадения токенизаторов.

---

## 6. Приёмка (обязательно перед промоутом)

Прогнать НОВУЮ модель тем же способом, что и раньше, и сравнить со старой:
1. **Recall ФИО и LeakRate** на held-out `test.jsonl` — recall не ниже, LeakRate 0%.
2. **FP-негативы** — `tests/test_false_positives.py` + новые топонимы/улицы/орг:
   FP должно упасть (сейчас 5/20).
3. **Скорость** — латентность на CPU не выросла (ученик тот же rubert-tiny2).
4. Промоут: положить в `models/person_ruBERT`, старую — в `models/person_ruBERT_old`
   (бэкап для отката). Веса НЕ коммитить (`.gitignore`), передавать как
   `person_ruBERT.zip` (см. `scripts/fetch_person_model.sh`).

Только при выполнении 1–3 менять прод-модель.
