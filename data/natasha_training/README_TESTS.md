# Инструкция по запуску тестов модуля анонимизации (план 2×2)

Harness: `data/natasha_training/eval_2x2.py`
Датасет: `data/natasha_training/test/test.jsonl` (150 примеров, held-out от train).

## Что это

Прогоняет модуль анонимизации по факторному плану 2×2 и считает метрики
(strict/relaxed, Micro/Macro, Precision/Recall/F2, LeakRate, время).

| Тест | prep (GramLynx) | Natasha | Что нужно для запуска |
|---|---|---|---|
| 1 | выкл | не обучена | ничего — работает сразу |
| 2 | вкл | не обучена | запущенный GramLynx (`GRAMLYNX_URL`) |
| 3 | выкл | обучена | дообученная Natasha (`NATASHA_TRAINED=1`) |
| 4 | вкл | обучена | оба |

Все команды — из **корня проекта** (`ANONIMIZATION_MODULE`).

---

## Тест 1 — базовый (работает прямо сейчас)

```bash
python3 data/natasha_training/eval_2x2.py --cells 1 -K 5 --warmup 1
```

- `--cells` — какие тесты гонять (`1`, `1,2`, `1,2,3,4` …).
- `-K` — сколько повторов для замера времени (по умолчанию 5).
- `--warmup` — сколько первых прогонов выбросить (по умолчанию 1).
- `--no-time` — не мерить время (быстрее, только качество).

Результат печатается в консоль и пишется в
`data/natasha_training/eval_2x2_results.json`.

---

## Тест 2 — с предобработкой GramLynx

**1. Поднять GramLynx** (в отдельном терминале; веса уже скачаны в `tests/GramLynx/models/`):

```bash
cd tests/GramLynx
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Дождаться готовности (первый прогрев моделей):

```bash
curl http://127.0.0.1:8010/health     # нужно {"status":"ok","ready":true}
```

**2. Запустить Тест 2**, указав адрес GramLynx:

```bash
GRAMLYNX_URL=http://127.0.0.1:8010 python3 data/natasha_training/eval_2x2.py --cells 2 -K 5
```

> Порт 8010 выбран, чтобы не конфликтовать с модулем анонимизации на 8000.
> В режиме предобработки основная метрика — **LeakRate** (по значению),
> т.к. GramLynx меняет текст и сдвигает координаты — span-level становится
> некорректным (harness это учитывает автоматически).

---

## Тесты 3 и 4 — с дообученной Natasha

⚠️ **Пока заблокированы:** дообученной модели Natasha в проекте нет
(распознаватель грузит стоковый `NewsNERTagger`). Сначала нужно обучить
slovnet-NER на `train/train.jsonl` и научить `NatashaPersonRecognizer`
грузить обученную модель.

После того как модель появится:

```bash
# Тест 3 (только дообучение)
NATASHA_TRAINED=1 python3 data/natasha_training/eval_2x2.py --cells 3

# Тест 4 (оба фактора)
NATASHA_TRAINED=1 GRAMLYNX_URL=http://127.0.0.1:8010 \
    python3 data/natasha_training/eval_2x2.py --cells 4
```

---

## Все 4 сразу (когда всё готово)

```bash
NATASHA_TRAINED=1 GRAMLYNX_URL=http://127.0.0.1:8010 \
    python3 data/natasha_training/eval_2x2.py --cells 1,2,3,4 -K 5 --warmup 1
```

Недоступные ячейки не падают, а помечаются как заблокированные в выводе и в JSON.

---

## Как читать результат

- **Recall / LeakRate** — главные: пропуск ПДн = утечка. Recall высокий, LeakRate низкий = хорошо.
- **Precision** — чистота: низкий precision = скрыли лишнее (over-masking), это не утечка.
- **strict vs relaxed** — разрыв показывает ошибки границ (напр. у имён Natasha).
- **Micro / Macro** — общий итог vs среднее по типам (Macro не даёт «утопить» редкие типы).
- **Время** — медиана мс/текст по K повторам.

## Изолированная оценка только Natasha (PERSON)

Отдельный скрипт с разбором по падежам/регистру/формату ФИО и графиками:

```bash
python3 data/natasha_training/eval_natasha_isolated.py
# графики → Рабочий стол/report_anonymization/Графики метрик/
```
