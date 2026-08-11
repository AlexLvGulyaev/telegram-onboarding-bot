# 📋 Telegram Onboarding Bot · IMPLEMENTATION_PLAN

**Проект:** telegram-onboarding-bot  
**Дата:** 2026-08-11  
**Статус:** Улучшенная универсальная версия реализована и запущена. Ожидается E2E-тестирование в Telegram.

---

## 1. Цель

Упаковать исходный репозиторий урока PEcb07 как портфолио-кейс APL: выполнить домашнее задание, провести baseline-прогон, устранить выявленные дефекты, сделать бота универсальным (заменяемые промпты и темы) и опубликовать с полным комплектом документации.

## 2. Архитектура решения

```text
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│   Telegram  │────▶│  aiogram    │────▶│  TrainingStates │
│   client    │◀────│   handlers  │◀────│   (FSM)         │
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

## 3. Состав компонентов

| Компонент | Назначение | Статус |
|-----------|------------|--------|
| `main.py` | Единственная точка входа: логирование, инициализация БД, запуск polling | ✅ |
| `bot/handlers/onboarding.py` | Обработчики Telegram, FSM-состояния | ✅ |
| `config/settings.py` | Pydantic Settings, переменные окружения, загрузка тем | ✅ |
| `database/` | SQLAlchemy-модели, engine, session factory, repository | ✅ |
| `schemas/` | Pydantic-схемы темы, черновика сессии и результата | ✅ |
| `services/prompt_loader.py` | Загрузка и рендеринг версионированных промптов | ✅ |
| `services/ai_training_service.py` | HTTP-клиент к OpenAI API, сборка сообщений | ✅ |
| `services/training_service.py` | TrainingService: бизнес-логика сессии, guard-logic | ✅ |
| `topics/` | Конфиги тем обучения | ✅ |
| `prompts/` | Версионированные системные промпты и JSON Schema | ✅ |
| `docker-compose.yml` | PostgreSQL + bot, healthcheck, depends_on, volume | ✅ |
| `Dockerfile` | Сборка образа бота | ✅ |

## 4. Модель данных

**Таблица `training_results`:**

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | serial PK | Идентификатор |
| `employee_name` | varchar(255) | Имя сотрудника |
| `telegram_user_id` | bigint | ID пользователя Telegram |
| `telegram_chat_id` | bigint | ID чата |
| `topic` | varchar(255) | Тема обучения |
| `total_questions` | int | Всего вопросов |
| `correct_answers` | int | Правильных ответов |
| `score_percent` | int | Процент |
| `final_summary` | text | Итоговый комментарий LLM |
| `created_at` | timestamp | Время создания |

## 5. Интеграции

### 5.1. OpenAI API (HTTP)

- **Chat Completions** — основной ход диалога: `POST {OPENAI_BASE_URL}/chat/completions`,
  модель из `OPENAI_MODEL`, `temperature=0.2`, `response_format=json_schema`
  (схема из `prompts/<version>/response-schema.json`). Используется в
  `AITrainingService.generate_turn()`.
- **Embeddings** — дедупликация вопросов по смыслу: `POST {OPENAI_BASE_URL}/embeddings`,
  модель `text-embedding-3-small`, косинусная близость, порог `0.72`.

### 5.2. Telegram Bot API

- **Транспорт:** long-polling через aiogram 3.x (`dp.start_polling(bot)`).
  Webhook не используется — публичный хост не требуется.
- **Command surface:** `/start`, `/topic`, `/cancel` (пользователь);
  `/admin`, `/new_topic`, `/list_topics`, `/set_topic`, `/delete_topic` (админ).
- **RBAC:** доступ к админ-командам по `message.from_user.id == ADMIN_USER_ID`.

### 5.3. PostgreSQL

- Async через SQLAlchemy 2.x + asyncpg (`DATABASE_URL`).
- Таблицы: `training_results`, `training_topics`, `bot_settings`.
- Volume `postgres_data` сохраняет данные между пересборками бота.

Полные контракты (endpoints, payload, схема ответа) — в `docs/API_CONTRACT.md`.
Внешние интеграции верифицируются по официальной документации OpenAI и Telegram
Bot API (правило external-integration SOT).

## 6. План реализации

### Этап 1. Анализ и ДЗ (✅ выполнен)

- [x] Разобрать `main.py`, `handlers/onboarding.py`, `config/settings.py` и их связь.
- [x] Разобрать `docker-compose.yml`: healthcheck, depends_on, volumes.
- [x] Проанализировать системный промпт: выделить 5 правил и предложить 3 улучшения.
- [x] Составить схему жизненного цикла сессии.
- [x] Подготовить мини-отчёт про async/await и PostgreSQL vs SQLite.

### Этап 2. Baseline-запуск и тестирование (✅ выполнен)

- [x] Запустить локально через `docker compose up --build`.
- [x] Протестировать бота в Telegram.
- [x] Проверить сохранение результатов в PostgreSQL.
- [x] Зафиксировать логи, findings и результаты в `docs/TESTING.md`.

**Baseline-findings (только из прогона с целевой моделью):**
- F1. Базовая версия успешно сохраняет результат в PostgreSQL.
- F2. Вопросы теста дублируются (вопросы 1 и 4 про одно и то же).
- F3. Последний вопрос может быть не задан явно.
- F4. Две точки входа (`main.py` и `bot/main.py`).

### Этап 3. Архитектурное развитие (✅ выполнен)

- [x] Унифицировать точку входа: оставить только `main.py`, перенести логику из `bot/main.py`.
- [x] Вынести системный промпт в `prompts/v1/system.md`.
- [x] Создать JSON Schema ответа LLM в `prompts/v1/response-schema.json`.
- [x] Создать загрузчик промптов (`services/prompt_loader.py`).
- [x] Создать универсальный конфиг темы в `topics/<id>.json` с полями `id`, `name`, `description`, `material`, `prompts_version`.
- [x] Усилить промпт:
  - чёткий триггер перехода к `testing`;
  - запрет на дублирование вопросов;
  - обязательное явное задание вопроса перед оценкой;
  - корректный подсчёт `questions_answered` / `correct_answers`.
- [x] Добавить guard-logic в `TrainingService` для контроля фаз и уникальности вопросов.
- [x] Добавить Telegram-админку для создания/удаления/переключения тем без ручного JSON.
- [ ] Добавить fallback при недоступности OpenAI API.

### Этап 4. Упаковка документации APL (в работе)

- [x] Дополнить `README.md` разделами про универсальные темы и промпты.
- [x] Обновить `docs/ARCHITECTURE.md` под новую структуру.
- [x] Обновить `docs/DEPLOYMENT_GUIDE.md` с учётом `ACTIVE_TOPIC`.
- [x] Создать `docs/TESTING.md` с результатами baseline E2E.
- [ ] Дополнить `docs/TESTING.md` результатами improved E2E.
- [x] Обновить `README.md` и `docs/ARCHITECTURE.md` с разделом про админку.
- [x] Обновить `docs/DEPLOYMENT_GUIDE.md` с `ADMIN_USER_ID`.
- [x] Создать `docs/PROMPT_ARCHITECTURE.md`.
- [x] Создать `docs/E2E_SCENARIOS.md` с чек-листом скриншотов.
- [x] Создать `docs/BUSINESS_VALUE.md`.
- [x] `docs/SECURITY_NOTES.md` — создан.

### Этап 5. Повторное тестирование улучшенной версии

- [x] Запустить улучшенную версию локально.
- [ ] Пройти E2E-прогон в Telegram для нескольких тем.
- [ ] Проверить сохранение результатов в PostgreSQL.
- [ ] Сравнить baseline vs improved в `docs/TESTING.md`.

### Этап 6. Публикация

- [ ] Пройти Deployment Validation на чистом окружении / VPS.
- [ ] Опубликовать/обновить публичный GitHub-репозиторий.
- [ ] Убедиться, что `.env` и внутренние материалы не попали в публичный репозиторий.

## 7. Критерии готовности

- [x] Проект запускается через `docker compose up --build` без ошибок.
- [x] Бот проходит полный сценарий baseline: `/start` → имя → обучение → тест → результат в БД.
- [x] Улучшенная версия запускается через `docker compose up --build`.
- [ ] Улучшенная версия проходит полный сценарий без дублирования вопросов и с чётким переходом к testing.
- [ ] Документация APL самодостаточна и не ссылается на внутренние материалы лаборатории.
- [ ] (Опционально) Пройдена Deployment Validation на VPS.

## 8. Открытые вопросы

- Подтвердить желаемое имя публичного GitHub-репозитория.
- Решить, нужен ли fallback при недоступности OpenAI API в рамках MVP.
