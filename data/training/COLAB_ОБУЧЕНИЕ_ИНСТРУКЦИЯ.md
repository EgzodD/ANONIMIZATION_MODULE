# Обучение модели PERSON в Google Colab — пошагово

Дистилляция в лёгкий `rubert-tiny2` (Track B). Улучшаем распознавание ФИО и убираем
ложные срабатывания на топонимах/улицах/орг-названиях. Всё нужное — в `data/training/`.

---

## Что понадобится
- Аккаунт Google (Colab бесплатный подойдёт).
- ~20–30 минут. GPU ускоряет, но не обязателен (ученик крошечный).
- Ничего скачивать вручную НЕ нужно: ученик `rubert-tiny2` и учитель тянутся автоматически.

## Где что лежит (в репозитории, папка `data/training/`)
| Файл | Что |
|---|---|
| `train/train.conll`, `train/train_negatives.conll` | обучающие метки (ФИО + негативы) |
| `dev/dev.conll`, `dev/dev_negatives.conll` | валидация |
| `test/test.jsonl` | held-out — **в обучении не участвует** |
| `make_silver_corpus.py` | генератор silver-корпуса |
| `silver/corpus.txt` | 8000 предложений для разметки учителем (уже сгенерирован) |
| `train_distill.py` | разметка учителем + обучение ученика |
| `DISTILLATION_RECIPE.md` | теория, выбор учителя, приёмка |

---

## Шаг 0. Открыть Colab и включить GPU
1. https://colab.research.google.com → New notebook.
2. Меню **Runtime → Change runtime type → Hardware accelerator: T4 GPU** → Save.

## Шаг 1. Загрузить код в Colab
**Вариант А (проще) — загрузить папку `data/training` архивом.**
На своём компьютере: заархивируй `data/training` в `training.zip`. В Colab выполни ячейку,
нажми кнопку выбора файла и выбери `training.zip`:
```python
from google.colab import files
up = files.upload()                 # выбери training.zip
!unzip -q training.zip -d .
%cd training                         # если внутри архива папка training
!ls
```

**Вариант Б — клонировать репозиторий** (если есть доступ):
```python
!git clone https://github.com/EgzodD/ANONIMIZATION_MODULE.git
%cd ANONIMIZATION_MODULE/data/training
!ls
```

## Шаг 2. Установить зависимости
```python
!pip install -q "transformers>=4.40" datasets seqeval spacy
!python -m spacy download ru_core_news_lg
```

## Шаг 3. (по желанию) Перегенерить silver-корпус
`silver/corpus.txt` уже лежит в репозитории. Если хочешь больше данных:
```python
!python make_silver_corpus.py 12000     # 12k предложений
```

## Шаг 4. Разметить silver учителем
**Лёгкий путь — spaCy (рекомендую для первого раза, без конфликтов версий):**
```python
from train_distill import label_silver_with_spacy
label_silver_with_spacy()               # -> silver/corpus.conll
```
spaCy хорошо отличает город (LOC) от имени (PER) — именно это лечит FP по топонимам.

**Сильный путь — DeepPavlov (качество выше, но капризнее по версиям).** Делать в
ОТДЕЛЬНОМ notebook/рантайме (DeepPavlov тянет свои версии transformers), затем скачать
`silver/corpus.conll` и продолжить обучение в чистом рантайме:
```python
!pip install -q deeppavlov && python -m deeppavlov install ner_rus_bert
from train_distill import label_silver_with_teacher
label_silver_with_teacher()             # -> silver/corpus.conll
```

## Шаг 5. Обучить ученика
```python
!python train_distill.py
```
- 12 эпох, метрика **F2** (приоритет recall — пропуск ФИО = утечка).
- Ученик остаётся `rubert-tiny2` (лёгкий). Результат → папка `person_ruBERT_distilled/`.
- В логах смотри `eval_recall` (должен расти) и `eval_precision`.

## Шаг 6. Скачать обученную модель
```python
!cd person_ruBERT_distilled && tar -czf ../person_ruBERT_distilled.tar.gz \
    config.json model.safetensors tokenizer.json tokenizer_config.json
from google.colab import files
files.download('person_ruBERT_distilled.tar.gz')
```
Формат архива — как ждёт `scripts/fetch_person_model.sh` (файлы в корне).

## Шаг 7. Прислать модель на приёмку
Пришли `person_ruBERT_distilled.tar.gz` — прогоню приёмку (recall/LeakRate/FP/латентность
на held-out `test.jsonl`) и, если не хуже старой, промоутну в прод (`models/person_ruBERT`,
старую в `_old` для отката). **Веса в git не коммитим.**

---

## Частые проблемы
- **`CUDA out of memory`** → уменьши батч: в `train_distill.py` `per_device_train_batch_size=16`.
- **`No module named datasets/seqeval`** → повтори Шаг 2 (иногда Colab сбрасывает среду).
- **DeepPavlov ломает transformers** → используй spaCy-путь (Шаг 4, лёгкий) или отдельный рантайм.
- **Нет GPU** → всё равно обучится (ученик крошечный), просто дольше; F2 не пострадает.
- **`ru_core_news_lg` не найден** → `!python -m spacy download ru_core_news_lg` и перезапусти ячейку.

## Критерии успеха (перед промоутом, проверяю я)
1. Recall ФИО не ниже старой модели, **LeakRate 0%** на held-out test.
2. FP на негативах (топонимы/улицы/орг) — упал.
3. Латентность на CPU не выросла (ученик тот же `rubert-tiny2`).
