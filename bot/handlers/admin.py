import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.access import is_admin as _is_admin
from config import Settings
from database import (
    BotSettingsRepository,
    TrainingResultRepository,
    TrainingTopicRepository,
)
from schemas import TrainingTopicConfig

logger = logging.getLogger(__name__)
router = Router()


class AdminTopicStates(StatesGroup):
    id = State()
    name = State()
    description = State()
    material = State()


class EditTopicStates(StatesGroup):
    # Wizard edits fields of an existing topic one by one; each field accepts
    # /skip to keep the current value.
    name = State()
    description = State()
    material = State()
    prompts_version = State()


async def _guard_wizard_input(message: Message, state: FSMContext, text: str, *, allow_skip: bool) -> bool:
    """Shared guard for FSM wizard text inputs.

    Wizard handlers match any text while a wizard state is active, otherwise
    they would swallow commands (/cancel, /help, ...) and strand the operator
    with no way out. Returns True when the input was consumed here.

    - `/cancel` — exits the wizard, nothing is saved;
    - `/skip` — handled by the step itself when allow_skip is True, otherwise
      rejected with a hint;
    - any other command — rejected with a hint.
    """
    if not text.startswith("/"):
        return False
    if text == "/cancel":
        await state.clear()
        await message.answer("Отменено. Введённые данные не сохранены. Для новой сессии отправьте команду ещё раз.")
        return True
    if text == "/skip":
        if allow_skip:
            return False
        await message.answer("На этом шаге /skip недоступен: поле обязательное. Введите значение или /cancel, чтобы выйти.")
        return True
    await message.answer(
        "Команды внутри визарда не обрабатываются. Завершите ввод или отправьте /cancel, чтобы выйти."
    )
    return True


@router.message(Command("admin"))
async def handle_admin(message: Message, settings: Settings) -> None:
    if not _is_admin(message, settings):
        await message.answer("Эта команда доступна только администратору.")
        return

    await message.answer(
        "👨‍💼 Панель администратора\n\n"
        "Доступные команды:\n"
        "/new_topic — создать новую тему обучения\n"
        "/import_topic [id] — загрузить темы из topics/*.json в базу (перезапись)\n"
        "/list_topics — список тем\n"
        "/edit_topic <id> — отредактировать существующую тему\n"
        "/delete_topic <id> — удалить тему\n"
        "/set_topic <id> — сделать тему активной по умолчанию"
    )


@router.message(Command("new_topic"))
async def handle_new_topic_start(
    message: Message,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not _is_admin(message, settings):
        await message.answer("Эта команда доступна только администратору.")
        return

    await state.set_state(AdminTopicStates.id)
    await message.answer(
        "Создание новой темы. Шаг 1/4\n\n"
        "Введите идентификатор темы (латиницей, без пробелов, например: customer-service)."
    )


@router.message(AdminTopicStates.id, F.text)
async def handle_topic_id(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if await _guard_wizard_input(message, state, text, allow_skip=False):
        return
    raw_id = text.lower().replace(" ", "-")
    if not raw_id or not raw_id.replace("-", "").replace("_", "").isalnum():
        await message.answer(
            "Идентификатор должен содержать только латинские буквы, цифры, дефисы и подчёркивания. Попробуйте ещё раз."
        )
        return

    await state.update_data(id=raw_id)
    await state.set_state(AdminTopicStates.name)
    await message.answer("Шаг 2/4. Введите название темы (человекочитаемое).")


@router.message(AdminTopicStates.name, F.text)
async def handle_topic_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if await _guard_wizard_input(message, state, name, allow_skip=False):
        return
    if len(name) < 2:
        await message.answer("Название должно быть не короче 2 символов. Попробуйте ещё раз.")
        return

    await state.update_data(name=name)
    await state.set_state(AdminTopicStates.description)
    await message.answer("Шаг 3/4. Введите краткое описание темы.")


@router.message(AdminTopicStates.description, F.text)
async def handle_topic_description(message: Message, state: FSMContext) -> None:
    description = (message.text or "").strip()
    if await _guard_wizard_input(message, state, description, allow_skip=False):
        return
    if len(description) < 10:
        await message.answer("Описание должно быть не короче 10 символов. Попробуйте ещё раз.")
        return

    await state.update_data(description=description)
    await state.set_state(AdminTopicStates.material)
    await message.answer(
        "Шаг 4/4. Введите материал для обучения.\n\n"
        "Это может быть один или несколько абзацев. Бот будет опираться на этот текст при обучении и тестировании."
    )


@router.message(AdminTopicStates.material, F.text)
async def handle_topic_material(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    material = (message.text or "").strip()
    if await _guard_wizard_input(message, state, material, allow_skip=False):
        return
    if len(material) < 10:
        await message.answer("Материал должен быть не короче 10 символов. Попробуйте ещё раз.")
        return

    data = await state.get_data()
    topic = TrainingTopicConfig(
        id=data["id"],
        name=data["name"],
        description=data["description"],
        material=material,
        prompts_version="v1",
    )

    async with session_factory() as session:
        repository = TrainingTopicRepository(session)
        try:
            await repository.create_or_update(topic)
        except Exception as exc:
            logger.exception("Failed to save topic config")
            await message.answer(f"Не удалось сохранить тему: {exc}")
            return

    await state.clear()
    await message.answer(
        f"✅ Тема «{topic.name}» сохранена.\n\n"
        f"Для активации отправьте /set_topic {topic.id}"
    )


@router.message(Command("import_topic"))
async def handle_import_topic(
    message: Message,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not _is_admin(message, settings):
        await message.answer("Эта команда доступна только администратору.")
        return

    args = message.text.split(maxsplit=1) if message.text else []
    requested_id = args[1].strip().lstrip("/") if len(args) > 1 else None

    topics_dir = Path("topics")
    if requested_id:
        files = [topics_dir / f"{requested_id}.json"]
    else:
        files = sorted(topics_dir.glob("*.json"))

    imported: list[str] = []
    async with session_factory() as session:
        repository = TrainingTopicRepository(session)
        for path in files:
            if not path.exists():
                await message.answer(f"Файл темы не найден: {path}")
                return
            try:
                topic = TrainingTopicConfig.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
                # create_or_update overwrites all fields, including prompts_version,
                # so /import_topic is also the way to move an existing topic to a
                # new prompt version: edit topics/<id>.json, then /import_topic <id>.
                await repository.create_or_update(topic)
                imported.append(topic.id)
            except Exception as exc:
                logger.exception("Failed to import topic from %s", path)
                await message.answer(f"Не удалось импортировать тему из {path.name}: {exc}")
                return

    if not imported:
        await message.answer(
            "Файлы тем не найдены в каталоге topics/. "
            "Создайте topics/<id>.json или используйте /new_topic."
        )
        return

    await message.answer(
        f"✅ Импортировано/обновлено тем: {len(imported)} ({', '.join(imported)}).\n\n"
        "Для активации отправьте /set_topic <id>"
    )


@router.message(Command("list_topics"))
async def handle_list_topics(
    message: Message,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not _is_admin(message, settings):
        await message.answer("Эта команда доступна только администратору.")
        return

    async with session_factory() as session:
        repository = TrainingTopicRepository(session)
        topics = await repository.list_all()

    if not topics:
        await message.answer("Тем пока нет. Создайте первую через /new_topic.")
        return

    active_topic_exists = any(topic.id == settings.active_topic_id for topic in topics)
    lines = []
    for topic in topics:
        marker = " ✅" if topic.id == settings.active_topic_id else ""
        lines.append(f"/{topic.id}{marker} — {topic.name}")
    if settings.active_topic_id and not active_topic_exists:
        lines.append(
            f"\n⚠️ Активная тема /{settings.active_topic_id} не найдена. "
            "Используйте /set_topic <id>, чтобы выбрать существующую."
        )

    await message.answer("Доступные темы:\n\n" + "\n".join(lines))


@router.message(Command("delete_topic"))
async def handle_delete_topic(
    message: Message,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not _is_admin(message, settings):
        await message.answer("Эта команда доступна только администратору.")
        return

    args = message.text.split(maxsplit=1) if message.text else []
    if len(args) < 2:
        await message.answer("Укажите id темы: /delete_topic <id>")
        return

    topic_id = args[1].strip().lstrip("/")

    async with session_factory() as session:
        repository = TrainingTopicRepository(session)
        topic = await repository.get_by_id(topic_id)
        if topic is None:
            await message.answer(f"Тема '{topic_id}' не найдена.")
            return

        # Results are immutable history (training_results.topic is a free-form
        # string with no foreign key), so deleting a topic never touches them.
        # Report how many are preserved so the operator knows they still exist.
        result_repository = TrainingResultRepository(session)
        results_count = await result_repository.count_by_topic_name(topic.name)

        try:
            await repository.delete(topic_id)
        except Exception as exc:
            logger.exception("Failed to delete topic")
            await message.answer(f"Не удалось удалить тему: {exc}")
            return

        if settings.active_topic_id == topic_id:
            settings_repository = BotSettingsRepository(session)
            await settings_repository.set_active_topic_id(None)
            settings.active_topic_id = None

    deletion_message = f"Тема '{topic_id}' удалена."
    if results_count:
        deletion_message += (
            f"\n\nРезультаты обучения ({results_count}) сохранены как историческая запись."
        )
    await message.answer(deletion_message)


@router.message(Command("set_topic"))
async def handle_set_default_topic(
    message: Message,
    state: FSMContext,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not _is_admin(message, settings):
        await message.answer("Эта команда доступна только администратору.")
        return

    args = message.text.split(maxsplit=1) if message.text else []
    if len(args) < 2:
        await message.answer("Укажите id темы: /set_topic <id>")
        return

    topic_id = args[1].strip().lstrip("/")

    async with session_factory() as session:
        topic_repository = TrainingTopicRepository(session)
        topic = await topic_repository.get_by_id(topic_id)
        if topic is None:
            await message.answer(f"Тема '{topic_id}' не найдена.")
            return

        settings_repository = BotSettingsRepository(session)
        await settings_repository.set_active_topic_id(topic_id)

    settings.active_topic_id = topic_id
    await state.clear()
    await message.answer(
        f"Тема по умолчанию изменена на «{topic.name}».\n\n"
        f"Отправьте /start, чтобы начать обучение по новой теме."
    )


@router.message(Command("edit_topic"))
async def handle_edit_topic_start(
    message: Message,
    state: FSMContext,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not _is_admin(message, settings):
        await message.answer("Эта команда доступна только администратору.")
        return

    args = message.text.split(maxsplit=1) if message.text else []
    if len(args) < 2:
        await message.answer("Укажите id темы: /edit_topic <id>. Список: /list_topics")
        return

    topic_id = args[1].strip().lstrip("/")
    async with session_factory() as session:
        repository = TrainingTopicRepository(session)
        topic = await repository.get_by_id(topic_id)
        if topic is None:
            await message.answer(f"Тема '{topic_id}' не найдена. Список: /list_topics")
            return

    # The DB record is the merge base: the wizard keeps every field the
    # operator skips and sends only changed fields through create_or_update
    # (which otherwise overwrites ALL fields from the wizard data alone).
    await state.set_state(EditTopicStates.name)
    await state.update_data(
        id=topic.id,
        name=topic.name,
        description=topic.description or "",
        material=topic.material,
        prompts_version=topic.prompts_version,
    )
    await message.answer(
        f"Редактирование темы «{topic.id}».\n\n"
        f"Шаг 1/4. Название. Текущее:\n{topic.name}\n\n"
        "Введите новое или /skip, чтобы оставить."
    )


async def _ask_next_field(
    message: Message,
    state: FSMContext,
    next_state: State,
    label: str,
    current: str,
) -> None:
    await state.set_state(next_state)
    await message.answer(
        f"{label}. Текущее:\n{current[:500]}\n\n"
        "Введите новое значение или /skip, чтобы оставить."
    )


@router.message(EditTopicStates.name, F.text)
async def handle_edit_topic_name(message: Message, state: FSMContext, settings: Settings) -> None:
    text = (message.text or "").strip()
    if await _guard_wizard_input(message, state, text, allow_skip=True):
        return
    if text != "/skip":
        if len(text) < 2:
            await message.answer("Название должно быть не короче 2 символов. Попробуйте ещё раз.")
            return
        await state.update_data(name=text)
    data = await state.get_data()
    await _ask_next_field(message, state, EditTopicStates.description, "Шаг 2/4. Описание", data["description"])


@router.message(EditTopicStates.description, F.text)
async def handle_edit_topic_description(message: Message, state: FSMContext, settings: Settings) -> None:
    text = (message.text or "").strip()
    if await _guard_wizard_input(message, state, text, allow_skip=True):
        return
    if text != "/skip":
        if len(text) < 10:
            await message.answer("Описание должно быть не короче 10 символов. Попробуйте ещё раз.")
            return
        await state.update_data(description=text)
    data = await state.get_data()
    await _ask_next_field(message, state, EditTopicStates.material, "Шаг 3/4. Материал", data["material"])


@router.message(EditTopicStates.material, F.text)
async def handle_edit_topic_material(message: Message, state: FSMContext, settings: Settings) -> None:
    text = (message.text or "").strip()
    if await _guard_wizard_input(message, state, text, allow_skip=True):
        return
    if text != "/skip":
        if len(text) < 10:
            await message.answer("Материал должен быть не короче 10 символов. Попробуйте ещё раз.")
            return
        await state.update_data(material=text)
    data = await state.get_data()
    await _ask_next_field(
        message,
        state,
        EditTopicStates.prompts_version,
        "Шаг 4/4. Версия промптов",
        data["prompts_version"],
    )


@router.message(EditTopicStates.prompts_version, F.text)
async def handle_edit_topic_prompts_version(
    message: Message,
    state: FSMContext,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    text = (message.text or "").strip()
    if await _guard_wizard_input(message, state, text, allow_skip=True):
        return
    if text != "/skip":
        # Mirrors PromptLoader: a version is usable when
        # prompts/<version>/system.md exists, otherwise sessions would crash
        # on /start with FileNotFoundError.
        version_dir = Path(settings.prompts_dir) / text
        if not (version_dir / "system.md").is_file():
            await message.answer(
                f"Версия «{text}» недоступна: нет {settings.prompts_dir}/{text}/system.md. "
                f"Посмотрите в {settings.prompts_dir} и попробуйте ещё раз (или /skip)."
            )
            return
        await state.update_data(prompts_version=text)

    data = await state.get_data()
    topic = TrainingTopicConfig(
        id=data["id"],
        name=data["name"],
        description=data["description"] or None,
        material=data["material"],
        prompts_version=data["prompts_version"],
    )

    async with session_factory() as session:
        repository = TrainingTopicRepository(session)
        try:
            await repository.create_or_update(topic)
        except Exception as exc:
            logger.exception("Failed to update topic config")
            await message.answer(f"Не удалось сохранить тему: {exc}")
            return

    await state.clear()
    await message.answer(
        f"✅ Тема «{topic.id}» обновлена ({topic.prompts_version}).\n\n"
        "Изменения применяются на следующих /start (идущая сессия продолжает старую тему)."
    )
