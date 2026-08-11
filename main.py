import asyncio
import logging
import logging.config

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import admin_router, router
from bot.middlewares import LoggingMiddleware
from config import get_settings
from database import (
    BotSettingsRepository,
    TrainingTopicRepository,
    create_engine,
    create_session_factory,
    init_db,
)
from services import AITrainingService, TrainingService

logger = logging.getLogger(__name__)


def setup_logging(level: str) -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "level": level.upper(),
                }
            },
            "root": {
                "handlers": ["console"],
                "level": level.upper(),
            },
        }
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)


async def run_bot() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    storage = MemoryStorage()
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties())
    dp = Dispatcher(storage=storage)

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    training_service = TrainingService()
    ai_training_service = AITrainingService(settings)

    await init_db(engine)

    # The database is the single source of truth for training topics. Starter
    # topics from topics/*.json are loaded on explicit operator action via the
    # /import_topic admin command, not automatically at startup. The bot starts
    # regardless of whether any topics exist yet; /start then guides the
    # operator to /import_topic or /new_topic.
    async with session_factory() as session:
        topic_repository = TrainingTopicRepository(session)
        existing_ids = {topic.id for topic in await topic_repository.list_all()}

        settings_repository = BotSettingsRepository(session)
        db_active_topic_id = await settings_repository.get_active_topic_id()

        # The active topic is resolved with DB precedence over the .env value:
        # the .env ACTIVE_TOPIC is only a first-start hint. If the resolved id
        # refers to a topic that no longer exists, reset it instead of crashing.
        candidate_topic_id = db_active_topic_id or settings.active_topic_id
        if candidate_topic_id and candidate_topic_id not in existing_ids:
            logger.warning(
                "Active topic %r not found in database, resetting active topic", candidate_topic_id
            )
            if db_active_topic_id:
                await settings_repository.set_active_topic_id(None)
            candidate_topic_id = None
        settings.active_topic_id = candidate_topic_id

    dp.message.middleware(LoggingMiddleware())
    dp.include_router(admin_router)
    dp.include_router(router)
    dp["settings"] = settings
    dp["session_factory"] = session_factory
    dp["training_service"] = training_service
    dp["ai_training_service"] = ai_training_service
    dp["topic_repository"] = topic_repository

    logger.info("Starting AI training bot")
    try:
        await dp.start_polling(bot)
    finally:
        await ai_training_service.close()
        await engine.dispose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run_bot())
