# 📦 Telegram Onboarding Bot · Examples

**Проект:** telegram-onboarding-bot
**Дата:** 2026-08-11
**Статус:** as-built

---

## 🎯 1. Назначение

Каталог содержит примеры JSON-ответов LLM по внутреннему контракту хода
(см. [🔌 `docs/API_CONTRACT.md`](../API_CONTRACT.md), раздел 4). Примеры
приведены по фазам жизненного цикла сессии: `learning`, `testing`,
`completed`. Данные основаны на реальном E2E-прогоне по теме
«Кибербезопасность для сотрудников» (см. [🧪 `docs/TESTING.md`](../TESTING.md)).

---

## 📂 2. Файлы

| Файл | Фаза | Что показывает |
|------|------|----------------|
| `training_turn_learning.json` | `learning` | Бот объясняет материал и спрашивает готовность |
| `training_turn_testing.json` | `testing` | Бот оценивает ответ + задаёт следующий вопрос |
| `training_turn_completed.json` | `completed` | Бот завершает тест и даёт итоговую сводку |

> 📌 Все три ответа соответствуют strict JSON Schema
> `prompts/v1/response-schema.json` (`additionalProperties: false`).
> Валидируются Pydantic-моделью `TrainingAssistantTurn` в коде.

---

## 📚 3. Связанные документы

- [🏠 `README.md`](../../README.md) — главная страница проекта.
- [🔌 `docs/API_CONTRACT.md`](../API_CONTRACT.md) — контракты OpenAI / Telegram / LLM-хода.
- [📝 `docs/PROMPT_ARCHITECTURE.md`](../PROMPT_ARCHITECTURE.md) — двухслойная архитектура промпта и схема ответа.
- [🧪 `docs/TESTING.md`](../TESTING.md) — результаты E2E-прогонов.