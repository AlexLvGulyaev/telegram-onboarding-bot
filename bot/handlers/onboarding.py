import logging
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards import cancel_keyboard, remove_keyboard
from config import Settings
from database import BotSettingsRepository, TrainingResultRepository, TrainingTopicRepository
from schemas import TrainingAssistantTurn, TrainingSessionDraft, TrainingTopicConfig
from services import AITrainingService, TrainingService

logger = logging.getLogger(__name__)
router = Router()


class TrainingStates(StatesGroup):
    active = State()


def _format_bot_reply(draft: TrainingSessionDraft, reply: str) -> str:
    """Ensure the user sees only the canonical current question in testing phase.

    The model sometimes returns a duplicate of the previous question inside
    `reply` while placing the real next question in `next_question` (which is
    stored as `draft.current_question`). To avoid showing duplicates, we keep
    only the non-question sentences (feedback/acknowledgement) from `reply` and
    always append the canonical current question.
    """
    if draft.phase != "testing" or not draft.current_question:
        return reply

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", reply) if s.strip()]
    feedback_parts = [s for s in sentences if "?" not in s]
    feedback = " ".join(feedback_parts).strip()

    question = draft.current_question.strip()
    if feedback:
        return f"{feedback}\n\n{question}"
    return question


async def _resolve_topic_config(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> TrainingTopicConfig | None:
    """Resolve the active topic into a config, or return None if none is set.

    The database is the single source of truth for topics. When no active topic
    is configured (or the configured one was deleted), this returns None instead
    of raising — callers surface a friendly message and never enter the training
    flow without a topic.
    """
    if settings.active_topic_id:
        async with session_factory() as session:
            repository = TrainingTopicRepository(session)
            topic = await repository.get_by_id(settings.active_topic_id)
            if topic:
                return TrainingTopicConfig(
                    id=topic.id,
                    name=topic.name,
                    description=topic.description,
                    material=topic.material,
                    prompts_version=topic.prompts_version,
                )
    return None


async def _ensure_topic_config(
    ai_training_service: AITrainingService,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> TrainingTopicConfig | None:
    topic_config = await _resolve_topic_config(settings, session_factory)
    if topic_config is not None:
        ai_training_service.set_topic_config(topic_config)
    return topic_config


async def _has_any_topics(session_factory: async_sessionmaker[AsyncSession]) -> bool:
    async with session_factory() as session:
        repository = TrainingTopicRepository(session)
        topics = await repository.list_all()
    return bool(topics)


async def _send_final_result(
    message: Message,
    state: FSMContext,
    training_service: TrainingService,
    ai_training_service: AITrainingService,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    draft: TrainingSessionDraft,
    last_ai_turn: TrainingAssistantTurn,
) -> None:
    """Finalize the draft, save result to PostgreSQL and send the final message."""
    topic_config = await _ensure_topic_config(ai_training_service, settings, session_factory)
    # The topic could have been deleted mid-session. Results are immutable history
    # keyed by topic name, so fall back to the name captured at /start time and
    # still save the result. ensure_summary uses the topic config cached on the
    # AI service from /start, so summary generation is unaffected.
    state_data = await state.get_data()
    topic_name = (
        topic_config.name
        if topic_config is not None
        else state_data.get("topic_name", "—")
    )
    finalized_draft = await training_service.ensure_summary(
        ai_training_service=ai_training_service,
        draft=draft,
    )
    async with session_factory() as session:
        repository = TrainingResultRepository(session)
        await training_service.create_result(
            repository=repository,
            draft=finalized_draft,
            topic=topic_name,
            telegram_user_id=message.from_user.id if message.from_user else 0,
            telegram_chat_id=message.chat.id,
        )

    await state.clear()
    turns_log_text = finalized_draft.format_turns_log()
    final_summary = finalized_draft.final_summary or last_ai_turn.reply
    await message.answer(
        f"{final_summary}\n\n"
        f"Результат сохранен в Postgres.\n"
        f"Итог: {finalized_draft.correct_answers}/{finalized_draft.total_questions} "
        f"({finalized_draft.score_percent()}%).\n\n"
        f"{turns_log_text}",
        reply_markup=remove_keyboard(),
    )


@router.message(Command("start"))
async def handle_start(
    message: Message,
    state: FSMContext,
    settings: Settings,
    training_service: TrainingService,
    ai_training_service: AITrainingService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await state.clear()
    # Resolve the topic BEFORE entering the training state. If there is no
    # usable topic, surface a friendly message and stay out of the FSM — never
    # crash and never start a session without material to teach.
    topic_config = await _ensure_topic_config(ai_training_service, settings, session_factory)
    if topic_config is None:
        has_topics = await _has_any_topics(session_factory)
        if has_topics:
            await message.answer(
                "Нет активной темы обучения.\n\n"
                "Администратор: /set_topic <id> — выбрать активную тему.",
                reply_markup=remove_keyboard(),
            )
        else:
            await message.answer(
                "Тем обучения пока нет.\n\n"
                "Администратор: /import_topic (загрузить из topics/*.json) "
                "или /new_topic (создать вручную).",
                reply_markup=remove_keyboard(),
            )
        return

    await state.set_state(TrainingStates.active)
    await state.update_data(
        draft=training_service.start_session(settings.quiz_question_count).model_dump(),
        topic_name=topic_config.name,
        result_id=None,
        name_collected=False,
    )
    await message.answer(
        f"Здравствуйте! Я помогу изучить материал, а затем проведу тестирование.\n\n"
        f"Тема: {topic_config.name}\n"
        f"Количество вопросов теста: {settings.quiz_question_count}\n\n"
        "Напишите имя сотрудника, которого нужно обучить.",
        reply_markup=cancel_keyboard(),
    )


async def _list_topics_text(
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    async with session_factory() as session:
        repository = TrainingTopicRepository(session)
        topics = await repository.list_all()
    if not topics:
        return "Тем пока нет. Создайте первую через /new_topic."
    lines = [f"/{topic.id} — {topic.name}" for topic in topics]
    return "Доступные темы:\n\n" + "\n".join(lines)


@router.message(Command("topic"))
async def handle_topic(
    message: Message,
    state: FSMContext,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    args = message.text.split(maxsplit=1) if message.text else []
    if len(args) < 2:
        topics_text = await _list_topics_text(session_factory)
        await message.answer(
            topics_text + "\n\n"
            "Чтобы сменить тему, отправьте /topic <id>. Текущая сессия будет сброшена.",
            reply_markup=remove_keyboard(),
        )
        return

    topic_id = args[1].strip().lstrip("/")
    async with session_factory() as session:
        repository = TrainingTopicRepository(session)
        topic = await repository.get_by_id(topic_id)
        if topic is None:
            await message.answer(
                f"Тема '{topic_id}' не найдена. Отправьте /topic, чтобы увидеть список.",
                reply_markup=remove_keyboard(),
            )
            return

        settings_repository = BotSettingsRepository(session)
        await settings_repository.set_active_topic_id(topic_id)

    settings.active_topic_id = topic_id
    await state.clear()
    await message.answer(
        f"Тема изменена на '{topic_id}'. Отправьте /start для начала обучения.",
        reply_markup=remove_keyboard(),
    )


@router.message(Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Сейчас нет активной сессии обучения.", reply_markup=remove_keyboard())
        return

    await state.clear()
    await message.answer(
        "Сессия обучения отменена. Чтобы начать заново, отправьте /start.",
        reply_markup=remove_keyboard(),
    )


@router.message(TrainingStates.active, F.text)
async def process_ai_training(
    message: Message,
    state: FSMContext,
    settings: Settings,
    training_service: TrainingService,
    ai_training_service: AITrainingService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    state_data = await state.get_data()
    draft = TrainingSessionDraft.model_validate(state_data.get("draft", {}))
    name_collected = bool(state_data.get("name_collected"))
    user_message = message.text or ""

    try:
        if not name_collected:
            current_draft = training_service.register_employee_name(draft=draft, employee_name=user_message)
            await state.update_data(draft=current_draft.model_dump(), name_collected=True)
            # Use a neutral prompt for the first learning turn. The real employee name is
            # already stored in the draft; passing the name as user_message here would
            # accidentally trigger readiness keywords if the name contains words like "тест".
            turn_user_message = "Пожалуйста, начни объяснение материала."
            ai_turn = await ai_training_service.generate_turn(
                draft=current_draft,
                user_message=turn_user_message,
                is_new_dialogue=True,
            )
        else:
            current_draft = draft
            turn_user_message = user_message
            ai_turn = await ai_training_service.generate_turn(
                draft=current_draft,
                user_message=turn_user_message,
                is_new_dialogue=False,
            )

        updated_draft = training_service.apply_ai_turn(current_draft, ai_turn, turn_user_message)

        # Semantic duplicate check for model-generated questions. Keyword-based
        # detection is fast, but embeddings catch reformulations like
        # "что фиксировать письменно?" vs "что сделать с важными решениями?".
        if (
            updated_draft.phase == "testing"
            and updated_draft.current_question
            and updated_draft.asked_questions
        ):
            is_duplicate, embedding = await ai_training_service.is_semantic_duplicate(
                updated_draft.current_question,
                updated_draft.asked_questions,
                updated_draft.asked_questions_embeddings,
            )
            if is_duplicate:
                logger.info("Semantic duplicate detected, clearing current_question: %r", updated_draft.current_question)
                updated_draft = TrainingSessionDraft.model_validate(updated_draft.model_dump())
                updated_draft.current_question = None
                updated_draft.current_question_embedding = None
            elif embedding:
                updated_draft = TrainingSessionDraft.model_validate(updated_draft.model_dump())
                updated_draft.current_question_embedding = embedding

        await state.update_data(draft=updated_draft.model_dump())

        # Guard: if testing phase has no valid question, ask LLM explicitly (with retry).
        # This covers duplicate questions, missing next_question, or malformed replies.
        fallback_reply: str | None = None
        for attempt in range(3):
            if not training_service.should_request_question(updated_draft):
                break
            logger.info("Guard fallback attempt %d", attempt + 1)
            # Preserve feedback from the last evaluated answer so the user still sees
            # it even when the model failed to include the next question in its reply.
            feedback_for_fallback = updated_draft.last_answer_feedback
            ai_turn = await ai_training_service.request_question(updated_draft)
            updated_draft = training_service.apply_ai_turn(updated_draft, ai_turn, "")

            # Semantic duplicate check for fallback-generated questions.
            if updated_draft.current_question and updated_draft.asked_questions:
                is_duplicate, embedding = await ai_training_service.is_semantic_duplicate(
                    updated_draft.current_question,
                    updated_draft.asked_questions,
                    updated_draft.asked_questions_embeddings,
                )
                if is_duplicate:
                    logger.info("Fallback produced semantic duplicate: %r", updated_draft.current_question)
                    updated_draft = TrainingSessionDraft.model_validate(updated_draft.model_dump())
                    updated_draft.current_question = None
                    updated_draft.current_question_embedding = None
                elif embedding:
                    updated_draft = TrainingSessionDraft.model_validate(updated_draft.model_dump())
                    updated_draft.current_question_embedding = embedding

            await state.update_data(draft=updated_draft.model_dump())
            if not training_service.should_request_question(updated_draft):
                if feedback_for_fallback:
                    fallback_reply = f"{feedback_for_fallback}\n\n{updated_draft.current_question}"
                else:
                    fallback_reply = ai_turn.reply
                break

        if training_service.should_request_question(updated_draft):
            await message.answer(
                "Не удалось подобрать следующий вопрос. Попробуйте написать любой текст, чтобы продолжить.",
                reply_markup=cancel_keyboard(),
            )
            return

        # If the turn completed the test, always show the final summary and save
        # the result. Do not display ai_turn.reply, because it may contain an extra
        # question the model tried to ask after the last answer.
        if updated_draft.phase == "completed":
            await _send_final_result(
                message=message,
                state=state,
                training_service=training_service,
                ai_training_service=ai_training_service,
                settings=settings,
                session_factory=session_factory,
                draft=updated_draft,
                last_ai_turn=ai_turn,
            )
            return

        # If guard fallback produced a real question, prefer its reply so the user
        # does not see the original duplicate/malformed question text.
        display_reply = fallback_reply if fallback_reply is not None else ai_turn.reply
        reply_text = _format_bot_reply(updated_draft, display_reply)
        await message.answer(reply_text, reply_markup=cancel_keyboard())
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=cancel_keyboard())
    except Exception:
        logger.exception("Failed to process AI training")
        await message.answer(
            "Не удалось обработать сообщение. Попробуйте еще раз или отправьте /cancel.",
            reply_markup=cancel_keyboard(),
        )


@router.message(TrainingStates.active)
async def handle_invalid_collecting_input(message: Message) -> None:
    await message.answer("Пожалуйста, отправьте ответ текстом.", reply_markup=cancel_keyboard())


@router.message(F.text)
async def handle_text_without_flow(message: Message) -> None:
    await message.answer("Чтобы начать обучение и тестирование, отправьте /start.")


@router.message()
async def handle_unsupported_input(message: Message) -> None:
    await message.answer("Пожалуйста, используйте текстовые сообщения или команду /start.")
