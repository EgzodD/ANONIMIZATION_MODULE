#!/usr/bin/env python3
"""
Меню прогона тестов: выбрать, что именно проверить.

Зачем: тестов много и они про разное — распознавание ПДн, безопасность,
скорость, приватность. Гонять всё ради одной проверки долго, а помнить наизусть
команды pytest с маркерами неудобно. Здесь всё собрано в одном месте.

Использование:
    ./scripts/test_menu.py              — интерактивное меню
    ./scripts/test_menu.py speed        — сразу нужная категория, без меню
    ./scripts/test_menu.py --list       — список категорий

Категории — это маркеры pytest (см. pyproject.toml). Один тест может попадать
сразу в несколько: например проверка API-ключа это и security, и integration.
"""

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _python() -> str:
    """Python из venv проекта, если он есть."""
    venv = os.path.join(ROOT, ".venv", "bin", "python")
    return venv if os.path.isfile(venv) else sys.executable


# ключ -> (заголовок, пояснение, аргументы pytest, нужна ли модель)
CATEGORIES = {
    "all": (
        "Всё",
        "полный прогон всех тестов",
        ["-m", "not requires_model"],
        False,
    ),
    "security": (
        "Безопасность",
        "аутентификация по API-ключу, границы политики сущностей",
        ["-m", "security"],
        False,
    ),
    "privacy": (
        "Приватность",
        "гейт LeakRate: ноль утечек ПДн на held-out наборе",
        ["-m", "privacy"],
        True,
    ),
    "speed": (
        "Скорость",
        "латентность и пропускная способность обработки",
        ["-m", "speed", "-s"],
        False,
    ),
    "unit": (
        "Модульные",
        "распознавание каждого типа ПДн по отдельности",
        ["-m", "unit"],
        False,
    ),
    "integration": (
        "Интеграционные",
        "HTTP API и адаптер Chatwoot",
        ["-m", "integration"],
        False,
    ),
    "e2e": (
        "Сквозные",
        "вся цепочка целиком + обратимость по mapping",
        ["-m", "e2e"],
        False,
    ),
    "custom_params": (
        "Кастомный параметр",
        "disable_entities — выборочное отключение типов в запросе",
        ["-m", "custom_params"],
        False,
    ),
    "ci": (
        "Как в CI",
        "ровно то, что гоняет CI: без модели, с покрытием",
        ["-m", "not requires_model", "--cov=app", "--cov-report=term-missing"],
        False,
    ),
    # args=None — не pytest, а показ примеров (scripts/demo_examples.py)
    "demo": (
        "Демо",
        "вход → выход на примерах тест-сета: посмотреть работу глазами",
        None,
        False,
    ),
}

ORDER = ["all", "security", "privacy", "speed", "unit", "integration",
         "e2e", "custom_params", "ci", "demo"]


def model_available() -> bool:
    sys.path.insert(0, ROOT)
    try:
        from app.person_transformer_recognizer import person_model_available

        return person_model_available()
    except Exception:
        return False


def count(args: list) -> str:
    """Сколько тестов в категории (для показа в меню).

    pytest пишет итог по-разному: без фильтра «77 tests collected», а с фильтром
    по маркеру «8/77 tests collected (69 deselected)» — берём первое число.
    """
    if args is None:  # демо — не pytest, счётчик тестов неприменим
        return "—"
    # для подсчёта нужны только -m <marker>; флаги прогона (-s, --cov...) мешают
    collect_args = []
    skip_next = False
    for i, a in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if a == "-m":
            collect_args += ["-m", args[i + 1]]
            skip_next = True
    try:
        out = subprocess.run(
            [_python(), "-m", "pytest", *collect_args, "--collect-only", "-q"],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
            env={**os.environ, "ALLOW_NO_PERSON_MODEL": "true"},
        ).stdout.strip().splitlines()
        for line in reversed(out):
            m = re.match(r"(\d+)(?:/\d+)?\s+tests?\s+collected", line.strip())
            if m:
                return m.group(1)
    except Exception:
        pass
    return "?"


def _verdict(title: str, hint: str, out: str, returncode: int) -> None:
    """Итоговый блок по-русски: что проверялось и чем закончилось.

    Разбирает финальную строку pytest («20 passed, 57 deselected, ...»)
    и переводит её в понятный вердикт, чтобы не вычитывать простыню логов.
    """
    counts = {k: int(n) for n, k in re.findall(
        r"(\d+) (passed|failed|error(?:s)?|skipped|xfailed|xpassed|deselected)", out)}
    failed = counts.get("failed", 0) + counts.get("error", 0) + counts.get("errors", 0)
    passed = counts.get("passed", 0)

    print("\n" + "═" * 62)
    print(f"  ИТОГ — {title}")
    print("─" * 62)
    print(f"  Проверялось: {hint}")
    if counts.get("deselected"):
        print(f"  Выполнено тестов: {passed + failed}   "
              f"({counts['deselected']} вне категории — отфильтрованы, это норма)")
    if failed:
        print(f"  ✘ ПРОВАЛОВ: {failed} — ищите строки FAILED выше.")
        print("    Если это приватность (LeakRate) — не «чинить тест», а разбираться,")
        print("    почему потекли ПДн: провал гейта = утечка = инцидент.")
    elif returncode == 0:
        print(f"  ✔ Все тесты прошли: {passed} passed")
    else:
        print(f"  ⚠ pytest завершился с кодом {returncode} — смотрите вывод выше")
    if counts.get("xfailed"):
        print(f"  xfailed {counts['xfailed']} — известный ожидаемый провал (ML-долг:"
              f" PERSON путает топонимы с ФИО); это НЕ ошибка прогона")
    if counts.get("xpassed"):
        print(f"  xpassed {counts['xpassed']} — ожидали провал, но тест прошёл:"
              f" пометку xfail пора снимать осознанно")
    if counts.get("skipped"):
        print(f"  skipped {counts['skipped']} — пропущены (обычно нет модели или"
              f" тест-сета); проверьте, что пропуск ожидаемый")
    print("═" * 62 + "\n")


def run(key: str) -> int:
    title, hint, args, needs_model = CATEGORIES[key]
    has_model = model_available()

    if args is None:  # демо — не pytest, просто показ примеров
        print(f"\n▶ {title}\n", flush=True)
        return subprocess.run(
            [_python(), os.path.join(ROOT, "scripts", "demo_examples.py")], cwd=ROOT
        ).returncode

    if needs_model and not has_model:
        print(f"\n  ⊘ «{title}» пропущено: нужна дообученная модель PERSON.")
        print("    Гейт приватности имеет смысл только на продакшн-модели — без неё")
        print("    ФИО не распознаются вообще, и тест упал бы не по делу.")
        print("    Задайте PERSON_MODEL_DIR или загрузите модель:")
        print("      PERSON_MODEL_URL=<url> ./scripts/fetch_person_model.sh\n")
        return 0

    print(f"\n▶ {title}\n")
    env = {**os.environ}
    env.setdefault("ALLOW_NO_PERSON_MODEL", "true")
    proc = subprocess.run(
        [_python(), "-m", "pytest", *args], cwd=ROOT, env=env,
        capture_output=True, text=True,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    _verdict(title, hint, proc.stdout, proc.returncode)
    return proc.returncode


def menu() -> int:
    has_model = model_available()
    while True:
        print("\n" + "═" * 62)
        print("  ЧТО ПРОТЕСТИРОВАТЬ")
        print("═" * 62)
        print(f"  модель PERSON: {'загружена' if has_model else 'НЕ загружена — ФИО не ищутся'}")
        print("─" * 62)
        for i, key in enumerate(ORDER, 1):
            title, hint, args, needs_model = CATEGORIES[key]
            mark = "  [нужна модель]" if needs_model and not has_model else ""
            print(f"  {i}  {title:<20} — {hint}{mark}")
        print("  q  выход")
        print("─" * 62)

        choice = input("  выбор: ").strip().lower()
        if choice in ("q", "quit", "exit", ""):
            return 0
        if not choice.isdigit() or not (1 <= int(choice) <= len(ORDER)):
            print("  нет такого пункта")
            continue
        run(ORDER[int(choice) - 1])


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Меню прогона тестов модуля обезличивания",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("category", nargs="?", choices=list(CATEGORIES),
                    help="запустить категорию сразу, без меню")
    ap.add_argument("--list", action="store_true", help="показать категории и выйти")
    args = ap.parse_args()

    if args.list:
        has_model = model_available()
        print("\n  Категории (маркеры pytest):\n")
        for key in ORDER:
            title, hint, a, needs_model = CATEGORIES[key]
            mark = " [нужна модель]" if needs_model and not has_model else ""
            print(f"  {key:<14} {count(a):>3} тестов  {title} — {hint}{mark}")
        print()
        return 0

    if args.category:
        return run(args.category)
    return menu()


if __name__ == "__main__":
    sys.exit(main())
