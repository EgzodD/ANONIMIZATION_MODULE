"""
Примеры-образцы по осям методики тестирования.

Здесь собраны показательные тесты, закрывающие оси, которых не хватало
в остальном наборе. Каждый класс подписан, к какой оси/методике относится, —
файл заодно служит наглядной документацией «как это выглядит в коде».

Все тесты здесь НЕ зависят от дообученной PERSON-модели (используют regex-типы:
телефон, email, ИНН), поэтому проходят и в CI без модели.
"""

import pytest

from app.anonymizer import anonymize_text
from app.config import settings


class TestApiRequiresKey:
    """
    Ось 4 (цель): тестирование БЕЗОПАСНОСТИ.
    Ось 1 (доступ): чёрный ящик — проверяем через HTTP, не заглядывая в код.
    Ось 3 (уровень): интеграционное/API.

    Смысл простыми словами: если в настройках задан API-ключ, то эндпоинт,
    отдающий mapping (ключ де-анонимизации), обязан отказывать без ключа (403)
    и пускать с правильным ключом (200). Так проверяем, что защита реально
    включается.
    """

    def test_rejects_without_key(self, client, monkeypatch):
        monkeypatch.setattr(settings, "api_key", "test-secret-123")
        resp = client.post("/anonymize/text", json={"text": "Иван Петров"})
        assert resp.status_code == 403

    def test_accepts_with_key(self, client, monkeypatch):
        monkeypatch.setattr(settings, "api_key", "test-secret-123")
        resp = client.post(
            "/anonymize/text",
            json={"text": "Телефон +79991234567"},
            headers={"X-API-Key": "test-secret-123"},
        )
        assert resp.status_code == 200


class TestFullPipelineReversible:
    """
    Ось 3 (уровень): СИСТЕМНОЕ — прогоняем всю цепочку целиком.
    Ось 2 (техника): сценарий использования — реальный путь «обезличили,
      потом по mapping восстановили оригинал».

    Смысл простыми словами: mapping — это ключ, которым обезличенный текст
    возвращается в исходный. Проверяем весь круг: в тексте с несколькими ПДн
    все значения скрыты, а затем по mapping текст точно восстанавливается.
    """

    def test_all_pii_masked_then_restored(self):
        # Берём типы, которые НЕ конкурируют за один и тот же плейсхолдер.
        # (Число-ИНН, например, ловится ещё и телефоном/паспортом — тогда
        # mapping по плейсхолдеру схлопывается; это отдельная известная
        # особенность, здесь мы демонстрируем чистый круг обратимости.)
        original = "Телефон +79991234567, почта test@mail.ru"
        res = anonymize_text(original)

        # 1) все значения ПДн скрыты, плейсхолдеры на месте
        assert "+79991234567" not in res["anonymized"]
        assert "test@mail.ru" not in res["anonymized"]
        assert "<PHONE>" in res["anonymized"]
        assert "<EMAIL>" in res["anonymized"]

        # 2) обратный ход: по mapping восстанавливаем оригинал
        restored = res["anonymized"]
        for placeholder, value in res["mapping"].items():
            restored = restored.replace(placeholder, value)
        assert restored == original


class TestEmptyAndNoPii:
    """
    Ось 2 (техника): эквивалентное разделение — берём по одному представителю
      из классов входа «пусто», «только пробелы», «текст без ПДн».
    Ось 4 (цель): часть регрессии — крайние входы не должны ломать модуль.

    Смысл простыми словами: не нужно гонять тысячи пустых строк — достаточно
    по одному примеру на каждый класс поведения.
    """

    @pytest.mark.parametrize("text", ["", "   ", "Сегодня хорошая погода"])
    def test_no_entities_no_change(self, text):
        res = anonymize_text(text)
        assert res["anonymized"] == text
        assert res["entities_found"] == []
        assert res["mapping"] == {}
