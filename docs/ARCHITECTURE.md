# 🏗️ Telegram Onboarding Bot · ARCHITECTURE

**Проект:** telegram-onboarding-bot  
**Дата:** 2026-08-11  
**Статус:** Актуальная архитектура после рефакторинга в универсального обучающего бота.

---

## 1. Общая архитектура

```text
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│   Telegram  │────▶│  aiogram    │────▶│  TrainingStates │
│   client    │◀────│  handlers   │◀────│  (FSM)          │
└─────────────┘     └─────────────┘     └─────────────────┘
                          │
                          ▼
                   ┌─────────────────────┐
                   │  TrainingService    │
                   │  AITrainingService  │
                   │  PromptLoader       │
                   └─────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
   │  OpenAI API │  │   topics/   │  │  PostgreSQL │
   └─────────────┘  │  prompts/   │  └─────────────┘
                    └─────────────┘
```

## 2. Компоненты

### 2.1. Точка входа

`main.py` (корень проекта) — единственная точка входа. Загружает настройки, инициализирует бота, БД и сервисы, запускает polling.

### 2.2. Telegram-уровень

- `bot/handlers/onboarding.py` — роутер обучения и FSM-состояния `TrainingStates`;
- `bot/handlers/admin.py` — роутер администратора для управления темами;
- `bot/keyboards/common.py` — reply-клавиатуры «Отмена» и удаление клавиатуры;
- `bot/middlewares/logging.py` — middleware логирования входящих сообщений.

### 2.3. Конфигурация

`config/settings.py` — `Pydantic Settings` с переменными окружения:
- `BOT_TOKEN` — токен Telegram-бота;
- `DATABASE_URL` — подключение к PostgreSQL;
- `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL` — LLM;
- `ACTIVE_TOPIC` — идентификатор темы из `topics/`;
- `PROMPTS_DIR`, `TOPICS_DIR` — пути к конфигам;
- `ADMIN_USER_ID` — Telegram user ID администратора, которому доступно управление темами;
- legacy-переменные `TRAINING_TOPIC`, `TRAINING_MATERIAL` — fallback, если `ACTIVE_TOPIC` не задан;
- `QUIZ_QUESTION_COUNT` — количество вопросов теста;
- `LOG_LEVEL` — уровень логирования.

### 2.4. Универсальные темы и промпты

- `topics/<id>.json` — конфигурация темы: `id`, `name`, `description`, `material`, `prompts_version`.
- `prompts/<version>/system.md` — системный промпт с плейсхолдерами.
- `prompts/<version>/response-schema.json` — JSON Schema ответа LLM.
- `services/prompt_loader.py` — загружает и рендерит промпты под конкретную тему.

### 2.5. База данных

- `database/db.py` — создание async engine, session factory, инициализация таблиц;
- `database/models.py` — SQLAlchemy-модель `TrainingResult`;
- `database/repository.py` — `TrainingResultRepository` для создания и чтения записей.

### 2.6. Схемы

`schemas/training.py` — Pydantic-модели:
- `TrainingTopicConfig` — конфигурация темы;
- `TrainingResultCreate` / `TrainingResultRead` — запись результата;
- `TrainingSessionDraft` — состояние активной сессии (включая историю заданных вопросов);
- `TrainingAssistantTurn` — ответ LLM.

### 2.7. Сервисы

- `services/prompt_loader.py` — загрузка версионированных промптов и схем;
- `services/ai_training_service.py` — HTTP-клиент к OpenAI API, сборка сообщений с рендерингом промпта;
- `services/training_service.py` — бизнес-логика сессии: валидация имени, строгий контроль фаз, уникальность вопросов, подсчёт баллов, сохранение результата.

## 3. Инфраструктура

`docker-compose.yml` поднимает два сервиса:

- `db` — PostgreSQL 16 с healthcheck, volume `postgres_data`;
- `bot` — сборка образа из `Dockerfile`, depends_on `db` с условием `service_healthy`.

Это разделение позволяет:
- хранить данные независимо от жизненного цикла контейнера бота;
- масштабировать или обновлять бота без потери БД;
- подключаться к PostgreSQL удалённо (например, через DBeaver).

## 4. Жизненный цикл сессии

```text
/start
  │
  ▼
collecting_name ──(имя)──▶ learning
                              │
                              │(сотрудник готов / материал разобран)
                              ▼
                          testing
                              │
                              │(questions_answered == total_questions)
                              ▼
                          completed
                              │
                              ▼
                    сохранение в training_results
```

## 5. Улучшения бизнес-логики

### 5.1. Строгий контроль фаз

`TrainingService.apply_ai_turn` не позволяет:
- вернуться из `testing` в `learning`;
- завершить сессию (`completed`), пока не проверены все вопросы.

### 5.2. Уникальность вопросов

В `TrainingSessionDraft` хранится список `asked_questions`. Если LLM предлагает вопрос, уже присутствующий в истории, он сбрасывается, и модель должна сгенерировать другой.

### 5.3. Корректность оценки

Оценка ответа (`latest_answer_evaluated`) учитывается только в фазе `testing` и только при наличии текущего вопроса. Это предотвращает ложное завершение теста на произвольном сообщении пользователя.

## 6. JSON Schema ответа LLM

```json
{
  "reply": "string",
  "phase": "learning | testing | completed",
  "latest_answer_evaluated": true | false,
  "answer_is_correct": true | false | null,
  "answer_feedback": "string | null",
  "next_question": "string | null",
  "final_summary": "string | null"
}
```

## 7. Открытые вопросы архитектурного развития

- Рассмотреть абстракцию LLM-провайдера для возможности замены OpenAI.
- Добавить персистентное хранилище FSM-состояния (Redis / PostgreSQL) для отказоустойчивости.
- Подготовить механизм версионирования тем через Git-репозиторий или внешнее хранилище.
