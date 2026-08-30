# 🚀 Telegram Onboarding Bot · DEPLOYMENT_GUIDE

**Проект:** telegram-onboarding-bot
**Дата:** 2026-08-11
**Статус:** Source of Truth процесса развёртывания.

---

## 🎯 1. Назначение

Единый Source of Truth для воспроизведения работоспособного экземпляра Telegram Onboarding Bot в чистом окружении. Если после выполнения руководства система не работает — руководство устарело.

Руководство рассчитано на технически подготовленного пользователя, знакомого с Docker и Linux. Управление темами через бота (команды администратора) описано в [`docs/OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md) и здесь не повторяется.

> ⚠️ Все токены, ключи и ID в этом документе — плейсхолдеры. Никогда не используйте значения из примеров в production.

---

## 📚 2. Связанные документы

- [🏠 `README.md`](../README.md) — главная страница проекта и быстрый старт.
- [🏗️ `docs/ARCHITECTURE.md`](ARCHITECTURE.md) — архитектура системы.
- [📖 `docs/USER_GUIDE.md`](USER_GUIDE.md) — как пройти обучение сотруднику.
- [🎛️ `docs/OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md) — как управлять темами оператору.
- [🧪 `docs/TESTING.md`](TESTING.md) — результаты E2E-прогонов.
- [🔐 `docs/SECURITY_NOTES.md`](SECURITY_NOTES.md) — безопасность, RBAC, секреты.

---

## 🛠️ 3. Варианты развёртывания

| Вариант | Когда использовать | Требования |
|---------|--------------------|------------|
| **Локальный запуск** | Разработка, ручное тестирование | Docker, Docker Compose v2 |
| **Production на VPS** | Публичный бот для сотрудников | VPS, Docker, SSH |

Compose поднимает три сервиса: `db` (PostgreSQL 16, результаты и темы), `redis` (FSM-сессии), `bot` (long polling Telegram).

---

## 📋 4. Требования

- Установленный Docker и Docker Compose (плагин `docker compose`, не `docker-compose` v1).
- Telegram-бот и его токен (`BOT_TOKEN`) — от [@BotFather](https://t.me/botfather).
- Ключ OpenAI API (`OPENAI_API_KEY`).
- Telegram user ID администратора (`ADMIN_USER_ID`) — для управления темами.

---

## 🔧 5. Переменные окружения

Создайте `.env` из `.env.example`:

```bash
cp .env.example .env
```

```env
BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/onboarding
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5.4-mini-2026-03-17
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MAX_RETRIES=3
OPENAI_RETRY_BACKOFF=1.5

ADMIN_USER_ID=your_telegram_user_id

ACTIVE_TOPIC=onboarding
PROMPTS_DIR=prompts

REDIS_URL=redis://redis:6379/0

QUIZ_QUESTION_COUNT=5
LOG_LEVEL=INFO
```

### Как получить переменные

- `BOT_TOKEN` — от [@BotFather](https://t.me/botfather).
- `DATABASE_URL` — для docker compose используется сервис `db` (оставьте как в примере). При внешней БД укажите её URL.
- `OPENAI_API_KEY` — из личного кабинета OpenAI.
- `OPENAI_MODEL` — модель OpenAI. Убедитесь, что она доступна в вашем аккаунте.
- `OPENAI_MAX_RETRIES` — число попыток при временных сбоях OpenAI API (429 / 5xx / сеть), по умолчанию 3. Клиентские ошибки (400/401/403) не повторяются.
- `OPENAI_RETRY_BACKOFF` — база экспоненциальной задержки между попытками в секундах (по умолчанию 1.5: ~1.5s, 2.25s, 3.4s… + джиттер). Заголовок `Retry-After` от API приоритетнее.
- `REDIS_URL` — адрес Redis для FSM-сессий (сервис `redis` из docker compose). Активные сессии обучения переживают рестарт контейнера бота. Пустое значение (`REDIS_URL=`) — сессии в памяти (MemoryStorage): dev-режим, прогресс теряется при рестарте; завершённые результаты в PostgreSQL в обоих режимах.
- `ADMIN_USER_ID` — ваш числовой Telegram user ID. Узнать: отправьте любое сообщение боту [@userinfobot](https://t.me/userinfobot) или выполните `curl -s "https://api.telegram.org/bot<BOT_TOKEN>/getUpdates" | jq '.result[-1].message.from.id'`.
- `ACTIVE_TOPIC` — id темы, которая станет активной при первом старте (пока в БД нет активной темы). Тема с этим id **должна уже быть в БД** — загрузите её через `/import_topic` (из `topics/*.json`) или `/new_topic` после первого запуска. Применяется **только при первом старте**; на работающей системе активная тема меняется через `/set_topic` (см. [`docs/OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md)). Если указанная тема отсутствует в БД — `main.py` сбросит её и запишет предупреждение в лог, бот стартует без активной темы.
- `PROMPTS_DIR` — каталог версионированных промптов (по умолчанию `prompts`).
- `QUIZ_QUESTION_COUNT` — число вопросов теста (1–20, по умолчанию 5).
- `LOG_LEVEL` — `DEBUG` / `INFO` / `WARNING` / `ERROR` (по умолчанию `INFO`).

> ⚠️ `.env` содержит секреты и **не коммитируется** (уже в `.gitignore`). Не публикуйте `BOT_TOKEN` и `OPENAI_API_KEY`.

---

## ▶️ 6. Локальный запуск

```bash
# клонировать репозиторий
git clone <repo-url>
cd telegram-onboarding-bot

# подготовить .env
cp .env.example .env
# заполнить .env (см. раздел 5)

# собрать и запустить
docker compose up --build
```

Проверка:

```bash
docker compose ps        # сервисы db, redis и bot со статусом Up / healthy
docker compose logs bot | tail   # ожидаемая строка: Start polling for bot @<your_bot>
```

Если вместо неё ошибка импорта или traceback — см. раздел «Устранение неполадок».

---

## 🗄️ 7. Проверка базы данных

### Вариант 1: psql из контейнера

```bash
docker compose exec db psql -U postgres -d onboarding -c "SELECT * FROM training_results;"
```

### Вариант 2: DBeaver (только через SSH-туннель)

Порт `5434` проброшен в `docker-compose.yml` как `127.0.0.1:5434:5432` — он доступен
только на самом хосте и **не открыт в интернет**. Поэтому с рабочего компьютера
подключайтесь через SSH-туннель:

```bash
ssh -L 5434:127.0.0.1:5434 YOUR_VPS_IP
```

В DBeaver: Host `localhost`, Port `5434`, Database `onboarding`, User `postgres`.
Пароль — значение `POSTGRES_PASSWORD` из `.env` сервера (не дефолт из этого
гайда, если на вашем инстансе он был заменён).

---

## 🚀 8. Развёртывание на VPS

### 8.1. Подключиться к серверу

```bash
ssh root@YOUR_VPS_IP
```

### 8.2. Установить Docker и плагин Compose

```bash
apt update
apt install -y docker.io docker-compose-plugin
```

### 8.3. Клонировать репозиторий

```bash
cd /opt
git clone <repo-url>
cd telegram-onboarding-bot
```

### 8.4. Создать .env и заполнить секреты

```bash
cp .env.example .env
nano .env
# заполнить BOT_TOKEN, OPENAI_API_KEY, ADMIN_USER_ID
# Ctrl+O, Enter, Ctrl+X
```

### 8.5. Собрать и запустить

```bash
docker compose up --build -d
```

### 8.6. Проверить статус

```bash
docker compose ps
docker compose logs bot | tail
```

Ожидаемая строка в логах: `Start polling for bot @<your_bot>`.

---

## 🧪 9. Проверка запуска (smoke test)

1. `docker compose ps` — `db`, `redis` и `bot` со статусом `Up` / `healthy`.
2. `docker compose logs bot | tail` — есть `Start polling for bot @…` и `FSM storage: Redis`.
3. В Telegram (от имени администратора) `/import_topic` — загрузить темы-заготовки из `topics/*.json` в БД. Ответ: «Импортировано/обновлено тем: N (...)».
4. `/list_topics` — темы в списке, у активной пометка ✅.
5. `/set_topic onboarding` — назначить активную тему.
6. `/start` — бот отвечает, называет тему, просит имя сотрудника.
7. `/edit_topic <id>`: на шаге «Материал» отправьте `/skip`, на шаге «Версия промптов» — `/skip`; бот подтвердит, что тема обновлена без изменений (проверка команды редактирования).
8. Пройдите обучение и тест до итогового балла.
9. Проверьте сохранение в БД:
   ```bash
   docker compose exec db psql -U postgres -d onboarding -c "SELECT count(*) FROM training_results;"
   ```
   — счётчик увеличился.

> ℹ️ На свежем развёртывании БД пуста. Бот стартует без тем и не падает — `/start` подскажет `/import_topic` или `/new_topic`. Управление темами — в [`docs/OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md).

Полный воспроизводимый прогон в чистом окружении — см. [`docs/DEPLOYMENT_VALIDATION_REPORT.md`](DEPLOYMENT_VALIDATION_REPORT.md).

---

## 📂 10. Темы обучения (поставка и активация)

Это раздел про развёртывание тем, а не управление ими через бота (управление — в [`docs/OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md)).

**Единый источник истины для тем — PostgreSQL** (`training_topics`). Каталог `topics/` содержит темы-заготовки, поставляемые с репозиторием; это **импортные шаблоны**, а не runtime-источник. Бот не читает их автоматически при старте.

**Загрузка тем-заготовок** выполняется командой администратора `/import_topic` (после первого запуска):

- `/import_topic` — загрузить **все** файлы `topics/*.json` в БД;
- `/import_topic <id>` — загрузить один `topics/<id>.json`.

Импорт идёт через `create_or_update` — **перезаписывает** все поля темы, включая `prompts_version`. Поэтому `/import_topic <id>` — это и способ обновить существующую тему после правки её файла, и способ перевести тему на новую версию промпта. Для тем, созданных через `/new_topic` (без файла-заготовки), правка — командой `/edit_topic <id>` (администратор редактирует name/description/material/prompts_version по шагам, `/skip` — оставить поле).

**Добавить свою тему-заготовку** (для поставки с репозиторием):

1. Создайте файл `topics/<id>.json`:

   ```json
   {
     "id": "my-topic",
     "name": "Моя тема",
     "description": "Краткое описание (≥ 10 символов)",
     "material": "Материал для обучения и теста...",
     "prompts_version": "v1"
   }
   ```

2. Загрузите тему в БД командой администратора:

   ```
   /import_topic my-topic
   ```

3. Активируйте тему:
   - **при первом старте** — задайте `ACTIVE_TOPIC=my-topic` в `.env` (тема должна быть уже в БД после `/import_topic`; применяется, только пока в БД нет активной темы);
   - **на работающей системе** — команда `/set_topic my-topic` администратором (см. [`docs/OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md)).

> ℹ️ `.env ACTIVE_TOPIC` **не** меняет тему на работающей системе, где в БД уже есть активная тема (`bot_settings`): при рестарте `main.py` берёт активную тему из БД. Для смены используйте `/set_topic`.

> ℹ️ Бот стартует и при пустой БД, и без каталога `topics/`. `/start` без активной темы не падает — отвечает подсказкой `/import_topic` или `/new_topic`.

---

## 🔄 11. Обновление

```bash
cd /opt/telegram-onboarding-bot
git pull
docker compose up -d --build
```

Данные PostgreSQL сохраняются в volume `postgres_data` и не теряются при пересборке.

---

## ↩️ 12. Откат

Если обновление привело к неработоспособности:

```bash
git log --oneline -5
git checkout <предыдущий_рабочий_коммит>
docker compose up -d --build
```

---

## 🛑 13. Остановка

```bash
docker compose down
```

Удалить данные PostgreSQL:

```bash
docker compose down -v
```

---

## 🚨 14. Устранение неполадок

| Симптом | Причина | Решение |
|---------|---------|---------|
| `bot` рестартует, в логах traceback / `ImportError` | Образ собран из старого кода | `docker compose build` (или `--build`), затем `docker compose up -d` |
| Порт `5432` занят на хосте | На хосте уже работает PostgreSQL | В `docker-compose.yml` проброс `5434:5432` уже используется; при конфликте смените порт |
| `password authentication failed for user "postgres"` | Пароль БД не синхронизирован | Проверить, что `DATABASE_URL` в `.env` совпадает с `POSTGRES_PASSWORD` в `docker-compose.yml` |
| Бот не отвечает в Telegram | Неверный `BOT_TOKEN` или бот уже запущен elsewhere (конфликт polling) | Проверить токен через Telegram API; остановить другие экземпляры бота |
| `OpenAI API недоступен после N попыток` в ответе пользователю | OpenAI API недоступен дольше серии retry | Проверить ключ (`docker compose logs bot`), лимиты аккаунта; сессия сохранена — повторите сообщение позже |
| Бот пишет «FSM storage: in-memory» | Пустой `REDIS_URL` в `.env` (dev-режим) | Задать `REDIS_URL=redis://redis:6379/0` и пересоздать bot (`docker compose up -d`) |
| Ошибки 429 / 5xx от OpenAI | Превышен rate limit или неверный `OPENAI_API_KEY` | Проверить ключ и лимиты аккаунта; модель должна существовать в аккаунте. Транзиентные сбои теперь ретраятся автоматически |
| `getaddrinfo EAI_AGAIN db` | `bot` и `db` в разных сетях | Запускать оба через один `docker compose` (общая сеть создаётся автоматически) |
| `$` в пароле БД не работает | Docker Compose интерполирует `$` | Экранировать как `$$` в `.env` |
| `/start` отвечает «Тем обучения пока нет» | БД пуста, темы не загружены | Администратор: `/import_topic` (загрузить из `topics/*.json`) или `/new_topic` (создать вручную), затем `/set_topic <id>` |
| `/start` отвечает «Нет активной темы обучения» | Темы в БД есть, но активная не выбрана | Выполните `/set_topic <id>` администратором (см. [`docs/OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md)) |
| В логах `Active topic ... not found in database, resetting` | `ACTIVE_TOPIC` в `.env` или активная тема в БД ссылается на удалённую тему | `main.py` сбросил активную тему; назначьте новую через `/set_topic <id>` |

---

## ℹ️ 15. Особенности версии

- Системные промпты вынесены в `prompts/` и версионированы (`prompts_version` в конфиге темы).
- Единственный источник тем — PostgreSQL (`training_topics`); темы-заготовки из `topics/` загружаются командой `/import_topic` (не автоматически при старте).
- Бот стартует при пустой БД и без `topics/`; `/start` без активной темы отвечает подсказкой, не падает.
- Временные сбои OpenAI API (429 / 5xx / сеть) повторяются с экспоненциальной задержкой (`OPENAI_MAX_RETRIES`/`OPENAI_RETRY_BACKOFF`); после исчерпания попыток диалог сохраняется, пользователь получает сообщение о сбое.
- FSM-сессии обучения хранятся в Redis (сервис `redis`, volume `redis_data`) и переживают рестарт бота; пустой `REDIS_URL` — MemoryStorage (dev-режим).
- `/topic <id>` доступен только администратору (смена глобальной темы); `/topic` без аргумента — read-only список для всех.
- Активная тема хранится в БД (`bot_settings`), а не в `.env`; `.env ACTIVE_TOPIC` — только начальное значение при первом старте (тема должна быть в БД).
- Сессии обучения — в Redis (`REDIS_URL`); активная сессия переживает рестарт бота. Завершённые результаты — в PostgreSQL.
- Данные PostgreSQL сохраняются благодаря volume `postgres_data`.

---

## 🔐 16. Безопасность

- `.env` не коммитировать в репозиторий (уже в `.gitignore`).
- API-ключи хранить только на сервере.
- Доступ к управлению темами (`/new_topic`, `/edit_topic`, `/set_topic`, `/delete_topic`, `/topic <id>`, `/import_topic`) — только для `ADMIN_USER_ID` (RBAC).
- Подробнее — [`docs/SECURITY_NOTES.md`](SECURITY_NOTES.md).

---

## 📚 Связанные документы

- [🏠 `README.md`](../README.md) — главная страница проекта.
- [🏗️ `docs/ARCHITECTURE.md`](ARCHITECTURE.md) — архитектура системы.
- [📖 `docs/USER_GUIDE.md`](USER_GUIDE.md) — как пройти обучение сотруднику.
- [🎛️ `docs/OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md) — как управлять темами оператору.
- [🧪 `docs/TESTING.md`](TESTING.md) — результаты E2E-прогонов.
- [🔐 `docs/SECURITY_NOTES.md`](SECURITY_NOTES.md) — безопасность, RBAC, секреты.