# Обучение PERSON-распознавателя (ruBERT) в Google Colab

Инструкция к ноутбуку `colab_train_person_ruBERT.ipynb`.
Цель — получить дообученную модель распознавания **ФИО (PERSON)**, которую модуль
подхватит вместо стоковой Natasha. Это «обученная Natasha» для Тестов 3 и 4.

> Почему только PERSON: телефон/ИНН/СНИЛС/паспорт/дату/карту в модуле ловит regex
> (recall 100% на тесте). Обучаемая модель отвечает за ФИО — там и ожидается прирост
> на реальных чатах (опечатки, строчные буквы, падежи).

---

## Что понадобится

- Google-аккаунт (Colab бесплатный).
- 3 файла из репозитория, папка `data/natasha_training/`:
  `train.conll`, `dev.conll`, `test.conll`.

---

## Шаги

### 1. Открыть ноутбук в Colab
- https://colab.research.google.com → `Файл → Загрузить блокнот` →
  выбрать `colab_train_person_ruBERT.ipynb`.

### 2. Включить GPU
- `Среда выполнения → Сменить среду выполнения → Аппаратный ускоритель: GPU (T4)`.

### 3. Выполнять ячейки сверху вниз
- **0. GPU** — проверка (`nvidia-smi`).
- **1. Установка** — transformers/datasets/seqeval/accelerate.
- **2. Данные** — по кнопке загрузить `train.conll`, `dev.conll`, `test.conll`.
- **3–4. Разбор + токенизация** — оставляем только PERSON, метки `O/B-PERSON/I-PERSON`.
- **5. Обучение** — базовая модель `cointegrated/rubert-tiny2`, 8 эпох
  (на T4 ≈ 10–20 минут). Для лучшего качества в этой ячейке можно поменять
  `MODEL_NAME` на `ai-forever/ruBert-base` (учится дольше, модель тяжелее).
- **6. Оценка на test** — печатает precision/recall/f1 на held-out.
- **7. Проверка** — прогон на живых примерах.
- **8. Сохранение** — скачивается `person_ruBERT.zip`.

> Совет: чтобы не потерять модель при отключении Colab, можно вместо скачивания
> подключить Google Drive (`from google.colab import drive; drive.mount('/content/drive')`)
> и сохранить папку туда.

---

## Как встроить в модуль

1. Распаковать `person_ruBERT.zip` в проект, например `models/person_ruBERT/`
   (внутри должен быть `config.json`).
2. Доустановить в venv модуля:
   ```bash
   ./.venv/bin/pip install "transformers>=4.40" torch
   ```
3. Указать путь к модели через переменную окружения — модуль подхватит её
   автоматически (см. `app/custom_recognizers.py`; если путь не задан, работает
   стоковая Natasha, поведение по умолчанию не меняется):
   ```bash
   export PERSON_MODEL_DIR=/abs/path/to/models/person_ruBERT
   ```
4. (Пере)запустить сервис анонимизации.

---

## Прогнать реальные Тесты 3 и 4

После того как модель подключена (`PERSON_MODEL_DIR` задан):

```bash
# Тест 3 (обученная Natasha, без GramLynx)
PERSON_MODEL_DIR=/abs/.../person_ruBERT \
    python data/natasha_training/eval_2x2.py --cells 3 -K 5

# Тесты 3 и 4 (нужен ещё запущенный GramLynx на :8010)
PERSON_MODEL_DIR=/abs/.../person_ruBERT \
GRAMLYNX_URL=http://127.0.0.1:8010 \
    python data/natasha_training/eval_2x2.py --cells 3,4 -K 5
```

> Harness проверяет **фактическое наличие модели** (`PERSON_MODEL_DIR`), а не просто
> флаг. Без реальной модели Тесты 3/4 останутся `blocked` — фейковых цифр не будет.

---

## Что дальше (2×2 замыкается)

- **Δ_train** = (Тест 3 − Тест 1) и (Тест 4 − Тест 2) — прирост от дообучения.
- **Interaction** = (Тест 4 − Тест 3) − (Тест 2 − Тест 1) — есть ли синергия
  GramLynx × обучение.
- Результаты пишутся в `eval_2x2_results.json`; отчёт на рабочем столе можно
  дополнить как и для Теста 2.
