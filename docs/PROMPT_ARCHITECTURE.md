# 🧩 Telegram Onboarding Bot · PROMPT_ARCHITECTURE

**Проект:** telegram-onboarding-bot  
**Дата:** 2026-08-11  
**Статус:** Описание системы версионированных промптов и тем.

---

## 1. Цель

Сделать бота универсальным обучающим помощником: тема обучения и поведение модели задаются внешними файлами, а не кодом. Это позволяет адаптировать бота под новую предметную область без изменения Python-кода.

## 2. Принципы

- **Разделение ответственности:** код отвечает за жизненный цикл сессии, а промпты и темы — за содержание и стиль диалога.
- **Версионирование:** каждая версия промптов живёт в отдельном каталоге `prompts/<version>/`.
- **Переиспользование:** одну и ту же версию промптов можно использовать с разными темами через `prompts_version` в конфиге темы.
- **Контроль качества:** guard-logic в `TrainingService` подстраховывает поведение модели, но не заменяет качество промпта.

## 3. Структура

```text
prompts/
└── v1/
    ├── system.md          # Системный промпт с плейсхолдерами
    └── response-schema.json  # JSON Schema для structured output

topics/
├── onboarding.json        # Тема «Корпоративный онбординг»
└── customer-service.json  # Тема «Правила работы с клиентами»
```

## 4. Двухслойная архитектура промпта

Промпт разделён на два слоя ответственности.

### Пользовательский уровень — `prompts/v1/system.md`

Описывает только роль и поведение, без технических деталей:

- роль AI-наставника;
- тему и материал, подставляемые из конфига темы;
- формат работы (обучение → тест → итог);
- поведенческие правила (спроси готовность → перейди к тесту → задавай по одному вопросу → не повторяй факты по смыслу → дай итог);
- запреты.

**В `system.md` нет имён JSON-полей, нет `phase=...`, нет `asked_questions`.**
Файл редактируется нетехническим пользователем для настройки роли и поведения.

### Технический слой — `_build_prompt()` / `request_question()` в коде

В `services/ai_training_service.py` формируется per-turn пользовательское сообщение, которое несёт технический контракт:

- сериализованное текущее состояние сессии (через `TrainingSessionDraft.to_llm_context()`);
- правила заполнения JSON-полей ответа (`reply`, `phase`, `latest_answer_evaluated`, `answer_is_correct`, `answer_feedback`, `next_question`, `final_summary`);
- логику переходов между фазами, привязанную к текущему состоянию;
- дедупликацию по `asked_questions` (выбирать факт, ещё не покрытый в сессии).

### Плейсхолдеры `system.md`

| Плейсхолдер | Значение |
|-------------|----------|
| `{{topic}}` | Название темы (`topic_config.name`) |
| `{{material}}` | Материал для обучения (`topic_config.material`) |
| `{{total_questions}}` | Количество вопросов теста (`settings.quiz_question_count`) |

## 5. JSON Schema ответа

`prompts/v1/response-schema.json` фиксирует контракт ответа LLM:

```json
{
  "name": "training_turn",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "reply": {"type": "string"},
      "phase": {"type": "string", "enum": ["learning", "testing", "completed"]},
      "latest_answer_evaluated": {"type": "boolean"},
      "answer_is_correct": {"type": ["boolean", "null"]},
      "answer_feedback": {"type": ["string", "null"]},
      "next_question": {"type": ["string", "null"]},
      "final_summary": {"type": ["string", "null"]}
    },
    "required": [...],
    "additionalProperties": false
  }
}
```

## 6. Конфигурация темы

Каждая тема — JSON-файл с полями:

```json
{
  "id": "onboarding",
  "name": "Корпоративный онбординг",
  "description": "...",
  "material": "...",
  "prompts_version": "v1"
}
```

`prompts_version` связывает тему с конкретной версией промптов.

## 7. Как добавить новую тему

1. Создать `topics/<id>.json`.
2. Указать `prompts_version`, соответствующий каталогу в `prompts/`.
3. Задать `ACTIVE_TOPIC=<id>` в `.env`.
4. Пересоздать контейнер бота:

```bash
docker compose up -d --force-recreate bot
```

## 8. Как добавить новую версию промптов

1. Скопировать `prompts/v1/` в `prompts/v2/`.
2. Внести изменения в `system.md` и/или `response-schema.json`.
3. В конфигах тем, которые должны использовать новую версию, изменить `prompts_version` на `v2`.
4. Протестировать E2E и зафиксировать результаты в `docs/TESTING.md`.

## 9. Соответствие кода и промптов

- `services/prompt_loader.py` загружает пользовательский промпт (`system.md`) и схему (`response-schema.json`) по версии.
- `services/ai_training_service.py` рендерит пользовательский промпт в `system`-сообщение, а в `_build_prompt()` / `request_question()` формирует технический слой (JSON-контракт, переходы фаз, дедуп по `asked_questions`) как `user`-сообщение.
- `prompts/v1/response-schema.json` уходит в OpenAI API через `response_format` — модель видит структуру ответа отдельно от промпта.
- `services/training_service.py` валидирует ответ модели и не позволяет нарушить жизненный цикл сессии, даже если модель ошиблась.

**Правило правок:** поведенческое правило идёт в `system.md`; всё, что ссылается на поля JSON или динамическое состояние draft (`asked_questions`, `phase`, `questions_answered`), — в `_build_prompt()` / `request_question()`.
