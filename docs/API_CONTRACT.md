# 🔌 Telegram Onboarding Bot · API_CONTRACT

**Проект:** telegram-onboarding-bot
**Дата:** 2026-08-11
**Статус:** Контракты внешних интеграций и внутреннего LLM-хода.

> 📌 **SOT:** Внешние контракты верифицированы по официальной документации
> OpenAI и Telegram Bot API (см. раздел «Источники»). Внутренний JSON-контракт
> хода описан по фактической реализации в `prompts/v1/response-schema.json` и
> `services/ai_training_service.py`. Если документация противоречит SOT —
> исправляется документация.

---

## 🎯 1. Назначение

Бот **не предоставляет HTTP-API** наружу. Этот документ фиксирует три контракта,
которые нужны интегратору, чтобы адаптировать бота под новую тему или заменить
LLM-провайдера:

1. **OpenAI API** — Chat Completions (основной ход) + Embeddings (дедупликация вопросов).
2. **Telegram Bot API** — command surface, long-polling, RBAC.
3. **Внутренний JSON-контракт LLM-хода** — структура ответа модели, по которой
   бот ведёт FSM-сессию.

---

## 🤖 2. OpenAI API

### 2.1. Chat Completions (основной ход)

Используется в `AITrainingService.generate_turn()`.

| Параметр | Значение |
|----------|----------|
| Метод | `POST` |
| URL | `{OPENAI_BASE_URL}/chat/completions` |
| Base URL (default) | `https://api.openai.com/v1` |
| Авторизация | `Authorization: Bearer {OPENAI_API_KEY}` |
| Content-Type | `application/json` |
| Timeout | 120 s (connect 30 s) |

**Тело запроса:**

```json
{
  "model": "<OPENAI_MODEL>",
  "temperature": 0.2,
  "messages": [
    {"role": "system", "content": "<рендер system.md>"},
    {"role": "user",   "content": "<_build_prompt(): состояние + JSON-контракт>"}
  ],
  "response_format": {
    "type": "json_schema",
    "json_schema": "<содержимое prompts/<version>/response-schema.json>"
  }
}
```

- `model` — из `OPENAI_MODEL` (по умолчанию `gpt-5.4-mini-2026-03-17`).
- `temperature` — 0.2, фиксирована в коде для предсказуемости диалога.
- `response_format` — strict JSON Schema, загружается из
  `prompts/{prompts_version}/response-schema.json` через `PromptLoader`.
- `system`-сообщение — рендер `prompts/<version>/system.md` с подстановкой
  `{{topic}}`, `{{material}}`, `{{total_questions}}` (см. `PROMPT_ARCHITECTURE.md`).
- `user`-сообщение — технический слой: сериализованное состояние сессии +
  правила заполнения JSON-полей + переходы фаз + дедуп по `asked_questions`.

**Ответ (используемые поля):**

```json
{
  "choices": [{"message": {"content": "<JSON-строка, см. раздел 4>"}}],
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
}
```

`choices[0].message.content` парсится как JSON и валидируется в
`TrainingAssistantTurn` (Pydantic). `usage` сохраняется в ход для учёта токенов
и в `training_results.total_tokens_spent`.

### 2.2. Embeddings (дедупликация вопросов)

Используется в `AITrainingService.is_semantic_duplicate()` / `get_embeddings()`.

| Параметр | Значение |
|----------|----------|
| Метод | `POST` |
| URL | `{OPENAI_BASE_URL}/embeddings` |
| Авторизация | `Authorization: Bearer {OPENAI_API_KEY}` |
| Тело | `{"model": "text-embedding-3-small", "input": ["<question>", ...]}` |

Косинусная близость между эмбеддингом нового вопроса и эмбеддингами уже
заданных вопросов. Порог `_DUPLICATE_EMBEDDING_THRESHOLD = 0.72` (короткие
русские вопросы кластеруются ниже типичного диапазона 0.80–0.85). Повтор по
смыслу блокируется в `TrainingService`, и модель должна предложить другой факт.

### 2.3. Источники (SOT)

- OpenAI API Reference — Chat Completions, JSON Schema response_format, Embeddings.
- Перед публикацией / заменой провайдера — верифицировать endpoints и payload
  по актуальной официальной документации провайдера.

---

## 📨 3. Telegram Bot API

### 3.1. Транспорт

Long-polling через aiogram 3.x (`dp.start_polling(bot)` в `main.py`).
Webhook **не используется**, публичный хост не нужен — это упрощает развёртывание.

| Параметр | Значение |
|----------|----------|
| Библиотека | aiogram 3.x |
| Токен | `BOT_TOKEN` |
| Режим | long-polling |
| Свойства | `DefaultBotProperties()` (default parse mode) |

### 3.2. Command surface

Команды пользователя (`bot/handlers/onboarding.py`):

| Команда | Назначение |
|---------|------------|
| `/start` | Начать новую сессию обучения: показать тему, запросить имя |
| `/topic` | Список тем или смена темы (`/topic <id>`) |
| `/cancel` | Отменить текущую сессию |

Команды администратора (`bot/handlers/admin.py`, ограничены `ADMIN_USER_ID`):

| Команда | Назначение |
|---------|------------|
| `/admin` | Показать меню администратора |
| `/new_topic` | Создать тему по шагам в диалоге |
| `/list_topics` | Список тем с отметкой активной |
| `/set_topic <id>` | Сделать тему активной по умолчанию |
| `/delete_topic <id>` | Удалить тему |

### 3.3. RBAC

Доступ к админ-командам — проверка `_is_admin()`:
`message.from_user.id == settings.admin_user_id`. Если `ADMIN_USER_ID` не задан
или не совпадает — бот отказывает в доступе. Не-администратор не может управлять
темами.

### 3.4. Источники (SOT)

- Telegram Bot API — официальная документация: методы `sendMessage`,
  `getUpdates` (под капотом aiogram long-polling), разметка сообщений.
- Поведение команд описано по фактической реализации в обработчиках, а не по
  предположениям о «типовом Telegram-боте».

---

## 🗂️ 4. Внутренний JSON-контракт LLM-хода

Каноническая схема — `prompts/<version>/response-schema.json` (strict,
`additionalProperties: false`). Загружается через `PromptLoader` и уходит в API
через `response_format`. Здесь — семантика полей (когда чем заполнять).

| Поле | Тип | Когда заполняется |
|------|-----|-------------------|
| `reply` | string | Текст, который видит сотрудник. При вопросе теста — сам вопрос здесь. |
| `phase` | enum `learning \| testing \| completed` | Текущая фаза FSM. |
| `latest_answer_evaluated` | boolean | `true` только если в этом ходу оценён ответ на вопрос теста. |
| `answer_is_correct` | boolean \| null | Только вместе с `latest_answer_evaluated=true`. |
| `answer_feedback` | string \| null | Короткая обратная связь; только вместе с `latest_answer_evaluated=true`. |
| `next_question` | string \| null | Техническая копия вопроса из `reply`. Всегда, когда `phase=testing` и задаётся вопрос; иначе `null`. |
| `final_summary` | string \| null | Только при `phase=completed`: сильные стороны + что повторить. |

**Правила перехода (см. также `PROMPT_ARCHITECTURE.md`):**

- `learning → testing`: по сигналу готовности сотрудника
  («готов», «давай», «тест», «экзамен», «переходим»).
- `testing → completed`: когда `questions_answered == total_questions`.
- `completed` разрешён только когда `questions_answered == total_questions`.
- `next_question` не должен повторять по смыслу вопросы из `asked_questions`.

> ⚠️ **Guard-слой в коде:** `TrainingService.apply_ai_turn()` валидирует ответ
> модели и не позволяет нарушить жизненный цикл сессии, даже если модель
> ошиблась (возврат из testing в learning, досрочный completed, пропуск вопроса).
> Технические правила заполнения JSON живут в `_build_prompt()` /
> `request_question()` в `services/ai_training_service.py`, а поведенческие — в
> `prompts/v1/system.md` (см. `PROMPT_ARCHITECTURE.md`, раздел о двухслойной
> архитектуре).

---

## 🔐 5. Переменные окружения контрактов

| Переменная | Контракт | Обязательна |
|------------|---------|-------------|
| `OPENAI_API_KEY` | OpenAI | ✅ |
| `OPENAI_MODEL` | OpenAI (Chat Completions) | ✅ |
| `OPENAI_BASE_URL` | OpenAI | default `https://api.openai.com/v1` |
| `BOT_TOKEN` | Telegram | ✅ |
| `ADMIN_USER_ID` | Telegram RBAC | для админ-команд |
| `ACTIVE_TOPIC` | Выбор темы | ✅ (или legacy `TRAINING_TOPIC`/`TRAINING_MATERIAL`) |

Полный список — в `docs/DEPLOYMENT_GUIDE.md`.

---

## 📚 6. Связанные документы

- [🏠 `README.md`](../README.md) — главная страница.
- [🏗️ `ARCHITECTURE.md`](ARCHITECTURE.md) — компоненты и потоки данных.
- [📝 `PROMPT_ARCHITECTURE.md`](PROMPT_ARCHITECTURE.md) — двухслойная архитектура промпта и схема ответа.
- [🚀 `DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) — переменные окружения и запуск.
- [📖 `USER_GUIDE.md`](USER_GUIDE.md) — сценарии пользователя и оператора.