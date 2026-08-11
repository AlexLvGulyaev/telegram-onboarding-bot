# 🚀 Telegram Onboarding Bot · DEPLOYMENT_GUIDE

**Проект:** telegram-onboarding-bot
**Дата:** 2026-08-11
**Статус:** Source of Truth процесса развёртывания.

> 📌 **SOT:** Этот документ — единственный источник истины для воспроизведения
> проекта. Любое изменение, затрагивающее развёртывание, требует актуализации
> здесь. Готовность к публикации подтверждается прохождением Deployment
> Validation в чистом окружении — см. `DEPLOYMENT_VALIDATION_REPORT.md`.

---

## Требования

- Установленный Docker.
- Установленный Docker Compose (плагин `docker compose`, не `docker-compose` v1).
- Telegram-бот и его токен (`BOT_TOKEN`).
- Ключ OpenAI API (`OPENAI_API_KEY`).

## Локальный запуск

1. Скопируйте `.env.example` в `.env`:

```bash
cp .env.example .env
```

2. Заполните `.env`:

```env
BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/onboarding
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5.4-mini-2026-03-17
OPENAI_BASE_URL=https://api.openai.com/v1

# Admin access
ADMIN_USER_ID=your_telegram_user_id

# Выберите тему из topics/ или используйте legacy-переменные
ACTIVE_TOPIC=onboarding
PROMPTS_DIR=prompts
TOPICS_DIR=topics

QUIZ_QUESTION_COUNT=5
LOG_LEVEL=INFO
```

> ⚠️ **Внимание:** `.env` содержит секреты и **не коммитируется** в репозиторий
> (уже в `.gitignore`). Не публикуйте `BOT_TOKEN` и `OPENAI_API_KEY`. В
> документации используются placeholder-значения `your_...`.

3. Запустите проект:

```bash
docker compose up --build
```

4. Убедитесь, что контейнеры подняты (smoke-test):

```bash
docker compose ps
```

Ожидаемый результат: сервисы `db` и `bot` со статусом `Up` / `healthy`.

5. Проверьте, что бот запустился:

```bash
docker compose logs bot | tail
```

Ожидаемая строка: `Start polling for bot @<your_bot>`. Если вместо неё ошибка
иморта или traceback — см. раздел «Типовые проблемы».

## Проверка базы данных

### Вариант 1: psql из контейнера

```bash
docker compose exec db psql -U postgres -d onboarding -c "SELECT * FROM training_results;"
```

### Вариант 2: DBeaver

- Host: `localhost`
- Port: `5434` (или тот порт, что проброшен в `docker-compose.yml`, если `5432` занят)
- Database: `onboarding`
- User: `postgres`
- Password: `postgres`

## Проверка бота

1. Откройте Telegram, найдите своего бота.
2. Отправьте `/start`.
3. Введите имя сотрудника.
4. Пройдите обучение и тестирование.
5. Убедитесь, что результат сохранился в PostgreSQL.
6. Для смены темы отправьте `/topic` и выберите другую тему.

## Управление темами через Telegram-админку

Администратор (пользователь с `ADMIN_USER_ID`) может управлять темами прямо в боте:

| Команда | Назначение |
|---------|------------|
| `/admin` | Показать меню администратора |
| `/new_topic` | Создать тему по шагам в диалоге |
| `/list_topics` | Список тем с отметкой активной |
| `/set_topic <id>` | Сделать тему активной по умолчанию |
| `/delete_topic <id>` | Удалить тему |

Добавленная тема сохраняется как `topics/<id>.json` и сразу доступна для обучения.

## Добавление новой темы вручную

1. Создайте файл `topics/<id>.json`:

```json
{
  "id": "my-topic",
  "name": "Моя тема",
  "description": "Краткое описание",
  "material": "Материал для обучения...",
  "prompts_version": "v1"
}
```

2. Установите `ACTIVE_TOPIC=my-topic` в `.env`.
3. Пересоздайте контейнер бота:

```bash
docker compose up -d --force-recreate bot
```

## Остановка

```bash
docker compose down
```

Чтобы удалить данные PostgreSQL:

```bash
docker compose down -v
```

## Перенос на VPS

1. Подключитесь к серверу по SSH.
2. Установите Docker и плагин Docker Compose (v2):

```bash
apt update
apt install -y docker.io docker-compose-plugin
```

3. Клонируйте репозиторий:

```bash
git clone <repo-url>
cd telegram-onboarding-bot
```

4. Создайте `.env` из `.env.example` и заполните секреты (см. выше).
5. Запустите:

```bash
docker compose up --build -d
```

## Типовые проблемы

| Симптом | Причина | Решение |
|---------|---------|---------|
| `bot` рестартует, в логах traceback / `ImportError` | Образ собран из старого кода | `docker compose build` (или `--build`), затем `docker compose up -d` |
| Порт `5432` занят локально | На хосте уже работает PostgreSQL | В `docker-compose.yml` пробросить другой порт (например `5434:5432`) |
| `password authentication failed for user "postgres"` | Пароль БД не синхронизирован | Проверить `DATABASE_URL` в `.env` совпадает с `POSTGRES_PASSWORD` в `docker-compose.yml` |
| Бот не отвечает в Telegram | Неверный `BOT_TOKEN` или бот уже запущен elsewhere (конфликт polling) | Проверить токен через Telegram API; остановить другие экземпляры бота |
| Ошибки 429 / 5xx от OpenAI | Превышен rate limit или неверный `OPENAI_API_KEY` | Проверить ключ и лимиты аккаунта; модель должна существовать в аккаунте |
| Ошибка `getaddrinfo EAI_AGAIN db` | `bot` и `db` в разных сетях | Запускать оба через один `docker compose` (общая сеть создаётся автоматически) |
| Символ `$` в пароле БД не работает | Docker Compose интерполирует `$` | Экранировать как `$$` в `.env` |

## Проверка запуска (минимальный smoke-test)

1. `docker compose ps` — `db` и `bot` `Up`/`healthy`.
2. `docker compose logs bot | tail` — есть `Start polling for bot @…`.
3. В Telegram `/start` — бот отвечает, называет тему, просит имя.
4. После тестовой сессии:
   `docker compose exec db psql -U postgres -d onboarding -c "SELECT count(*) FROM training_results;"`
   — счётчик увеличился.

Полный воспроизводимый прогон (включая чистое окружение) — см.
`DEPLOYMENT_VALIDATION_REPORT.md`.

## Особенности версии

- Системные промпты вынесены в `prompts/` и версионированы.
- Темы обучения вынесены в `topics/`.
- Сессии хранятся в памяти (`MemoryStorage`).
- PostgreSQL-данные сохраняются благодаря volume `postgres_data`.
