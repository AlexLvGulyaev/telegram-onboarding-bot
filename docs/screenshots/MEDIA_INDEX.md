# 🖼️ Telegram Onboarding Bot · MEDIA_INDEX

**Проект:** telegram-onboarding-bot
**Дата:** 2026-08-11
**Статус:** Каталог публичных медиаматериалов портфолио. Скриншоты добавляются
по мере съёмки.

> 📌 **SOT:** Архитектурные схемы реализуются в Mermaid внутри Markdown (см.
> `ARCHITECTURE.md`, `PROMPT_ARCHITECTURE.md`) — это не изображения и здесь не
> каталогируются. Здесь — только растровые медиа (скриншоты Telegram-диалогов,
> результаты в БД).

> ⚠️ **Публичный ресурс:** эти скриншоты — материал Customer Facing слоя
> (демонстрация продукта заказчику). Они публикуются в репозитории. Анонимизация
> персональных данных — обязательна перед коммитом (см. `SECURITY_NOTES.md`,
> правило безопасности APL).

---

## 🎯 1. Назначение

MEDIA_INDEX — единый каталог медиаматериалов проекта. Каждое изображение
должно объяснять конкретный тезис документа. Скриншоты не вставляются «потому
что есть».

---

## 📐 2. Схема нейминга

Формат: `TOB_{CATEGORY}_{DESCRIPTION}.{ext}`

Префикс `TOB` — Telegram Onboarding Bot.

| Категория | Назначение | Пример |
|-----------|------------|--------|
| `ui` | Диалог в Telegram (ход обучения/теста) | `TOB_ui_learning_block.png` |
| `admin` | Управление темами в боте | `TOB_admin_new_topic.png` |
| `result` | Результат в PostgreSQL / итог теста | `TOB_result_db_rows.png` |
| `demo` | Демонстрационные GIF/видео | `TOB_demo_walkthrough.gif` |

> ❌ Архитектурные схемы (`arch`) — в Mermaid внутри Markdown, не PNG.
> См. `ARCHITECTURE.md` §1, §4.

---

## 🗂️ 3. Размещение

```text
docs/
└── screenshots/
    ├── MEDIA_INDEX.md        # Этот каталог
    ├── TOB_ui_*.png          # Диалоги: обучение, тест, итог
    ├── TOB_admin_*.png       # Админка: темы
    ├── TOB_result_*.png     # Результаты в БД
    └── TOB_demo_*.gif        # Демонстрация (опц.)
```

Каталог `docs/screenshots/` — публичный, входит в репозиторий и публикуется на
GitHub. Внутренние свидетельства тестирования (если нужны) держатся отдельно, в
`attachments/` (gitignored).

---

## 📋 4. Каталог изображений

| ID | Файл | Категория | Тезис | Используется в |
|----|------|-----------|-------|----------------|
| 1 | `TOB_ui_happy_path.png` | `ui` | Полный сквозной диалог: `/start` → имя → блок обучения → «Готов» → переход к тесту → вопросы + feedback → итог X/5 + `final_summary` | `README.md`, `SYSTEM_DEMO.md`, `E2E_SCENARIOS.md`, `BUSINESS_VALUE.md` |
| 2 | `TOB_result_db_rows.png` | `result` | Результат теста сохраняется в PostgreSQL: таблица `training_results` (колонки `employee_name`, `topic`, `total_questions`, `correct_answers`, `score_percent`, `created_at`) | `SYSTEM_DEMO.md`, `TESTING.md`, `ARCHITECTURE.md`, `OPERATOR_GUIDE.md` |
| 3 | `TOB_ui_cancel.png` | `ui` | `/cancel` прерывает сессию: подтверждение сброса + повторное сообщение без `/start` не возобновляет старую сессию | `README.md`, `SYSTEM_DEMO.md`, `E2E_SCENARIOS.md`, `USER_GUIDE.md` |
| 4 | `TOB_ui_topic_switch.png` | `ui` | Смена темы пользователем: `/topic` (список доступных тем) → `/topic <id>` (подтверждение переключения) → `/start` уже по новой теме | `README.md`, `SYSTEM_DEMO.md`, `E2E_SCENARIOS.md`, `USER_GUIDE.md`, `OPERATOR_GUIDE.md` |
| 5 | `TOB_ui_invalid_input.png` | `ui` | Валидация ввода: слишком короткое имя (1 символ) → ошибка + фото/стикер вместо текста → «пришлите текст» | `SYSTEM_DEMO.md`, `E2E_SCENARIOS.md`, `USER_GUIDE.md` |
| 6 | `TOB_admin_new_topic.png` | `admin` | Создание темы через `/new_topic`: пошаговый FSM-диалог (id → название → описание → материал) → «✅ Тема сохранена» | `SYSTEM_DEMO.md`, `OPERATOR_GUIDE.md`, `E2E_SCENARIOS.md` |
| 7 | `TOB_admin_list_set.png` | `admin` | Управление темами: `/list_topics` (список с отметкой активной) → `/set_topic <id>` (активация темы по умолчанию) | `SYSTEM_DEMO.md`, `OPERATOR_GUIDE.md`, `E2E_SCENARIOS.md` |
| 8 | `TOB_admin_denied.png` | `admin` | RBAC: админ-команда (`/admin`, `/new_topic`) от не-администратора отклоняется — «Эта команда доступна только администратору» | `SYSTEM_DEMO.md`, `OPERATOR_GUIDE.md`, `SECURITY_NOTES.md` |

---

## 🧩 5. Матрица использования по документам

| Документ | Категории медиа |
|----------|-----------------|
| `README.md` | `ui`, `demo` — диалог и демонстрация работы |
| `docs/SYSTEM_DEMO.md` | `ui`, `admin`, `result` — продукт как работающая система |
| `docs/E2E_SCENARIOS.md` | `ui`, `admin` — иллюстрации сценариев |
| `docs/TESTING.md` | `result` — записи в БД, итоги прогонов |
| `docs/USER_GUIDE.md` | `ui`, `admin` — шаги пользователя и оператора |
| `docs/OPERATOR_GUIDE.md` | `admin`, `result`, `ui` — управление темами и просмотр результатов |
| `docs/BUSINESS_VALUE.md` | `ui`, `demo` — продукт как работающая система |

---

## ✅ 6. Принцип выбора изображений

1. Определить тезис документа/раздела.
2. Определить, что требует визуализации.
3. Подобрать изображение, максимально помогающее понять тезис.
4. Если подходящего изображения нет — **не вставлять**.

> ❌ **Не делайте:** добавлять скриншоты «при необходимости» или «подобрать
> что-нибудь из screenshots». Каждое изображение доказывает конкретную мысль.

---

## 📚 7. Связанные документы

- [🏠 `README.md`](../../README.md)
- [🎬 `docs/SYSTEM_DEMO.md`](../SYSTEM_DEMO.md)
- [🎬 `docs/E2E_SCENARIOS.md`](../E2E_SCENARIOS.md)
- [🧪 `docs/TESTING.md`](../TESTING.md)
- [🏗️ `docs/ARCHITECTURE.md`](../ARCHITECTURE.md) — архитектурные схемы в Mermaid.