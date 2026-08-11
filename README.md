# 🏠 Telegram Onboarding Bot

AI-driven Telegram-бот для поэтапного обучения сотрудников новому материалу и автоматического тестирования.

## Назначение

Бот заменяет живого наставника на первичном этапе онбординга:

- объясняет материал простыми сообщениями;
- отвечает на вопросы сотрудника строго по заданной теме;
- сам решает, когда можно переходить к тесту;
- задаёт вопросы по одному и оценивает ответы по материалу;
- сохраняет результат теста в PostgreSQL.

Ключевое отличие этой версии — **универсальный шаблон обучения**: темы и системные промпты вынесены в отдельные файлы, поэтому бота можно адаптировать под любую тематику без изменения кода.

## Стек

- Python 3.11
- aiogram 3.x
- SQLAlchemy 2.x + asyncpg
- PostgreSQL 16
- OpenAI API (JSON Schema ответа)
- Docker Compose

## Быстрый старт

```bash
cp .env.example .env
# заполните BOT_TOKEN, OPENAI_API_KEY
# выберите тему в ACTIVE_TOPIC или оставьте legacy-настройки TRAINING_TOPIC/TRAINING_MATERIAL
docker compose up --build
```

## Структура проекта

```
.
├── bot/                  # Telegram-обработчики и middleware
├── config/               # Настройки и переменные окружения
├── database/             # Модели, миграции и репозиторий результатов
├── prompts/              # Версионированные системные промпты
├── schemas/              # Pydantic-схемы
├── services/             # AI-training service, prompt loader и training service
├── topics/               # Конфиги тем обучения (JSON)
├── main.py               # Единственная точка входа
├── docker-compose.yml    # Инфраструктура: bot + db
├── Dockerfile
└── requirements.txt
```

## Жизненный цикл сессии

1. `/start` — бот запрашивает имя сотрудника и показывает текущую тему.
2. Сбор имени — фиксация `employee_name`.
3. Обучение — AI-наставник последовательно подаёт материал.
4. Тестирование — `QUIZ_QUESTION_COUNT` вопросов, по одному за раз, с обратной связью.
5. Завершение — итоговый балл и `final_summary` сохраняются в таблицу `training_results`.

## Команды

| Команда | Назначение |
|---------|------------|
| `/start` | Начать новую сессию обучения |
| `/topic` | Список тем или смена темы (`/topic <id>`) |
| `/cancel` | Отменить текущую сессию |

### Команды администратора

| Команда | Назначение |
|---------|------------|
| `/admin` | Показать меню администратора |
| `/new_topic` | Создать новую тему обучения по шагам |
| `/list_topics` | Список доступных тем |
| `/set_topic <id>` | Сделать тему активной по умолчанию |
| `/delete_topic <id>` | Удалить тему |

Доступ к админ-командам ограничен `ADMIN_USER_ID`.

## Универсальная тематизация

Темы обучения описываются в `topics/<id>.json`:

```json
{
  "id": "onboarding",
  "name": "Корпоративный онбординг",
  "description": "...",
  "material": "...",
  "prompts_version": "v1"
}
```

Системные промпты хранятся в `prompts/<version>/system.md` и могут содержать плейсхолдеры `{{topic}}`, `{{material}}`, `{{total_questions}}`. Чтобы адаптировать бота под новую тему, достаточно добавить JSON-файл темы и выбрать её через `ACTIVE_TOPIC`.

## Документация

| Документ | Назначение |
|----------|------------|
| [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) | 📊 Паспорт состояния проекта |
| [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) | 📋 Технический план реализации |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 🏗️ Архитектура и компоненты |
| [`docs/PROMPT_ARCHITECTURE.md`](docs/PROMPT_ARCHITECTURE.md) | 📝 Двухслойная архитектура промпта |
| [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) | 🔌 Контракты OpenAI / Telegram / LLM-хода |
| [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) | 📖 Руководство сотрудника и оператора |
| [`docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md) | 🚀 Руководство по развёртыванию (Source of Truth) |
| [`docs/DEPLOYMENT_VALIDATION_REPORT.md`](docs/DEPLOYMENT_VALIDATION_REPORT.md) | ✅ Отчёт воспроизводимости с нуля |
| [`docs/E2E_SCENARIOS.md`](docs/E2E_SCENARIOS.md) | 🎬 Сквозные сценарии |
| [`docs/BUSINESS_VALUE.md`](docs/BUSINESS_VALUE.md) | 💼 Бизнес-ценность |
| [`docs/TESTING.md`](docs/TESTING.md) | 🧪 Результаты тестирования и дефекты |
| [`docs/MEDIA_INDEX.md`](docs/MEDIA_INDEX.md) | 🖼️ Каталог медиаматериалов |

## Статус

MVP с универсальной архитектурой тем и промптов. E2E-дефекты устранены и
подтверждены прогонами (см. `docs/TESTING.md`). До публикации на GitHub
требуется прохождение Deployment Validation в чистом окружении
(см. `docs/DEPLOYMENT_VALIDATION_REPORT.md`).
