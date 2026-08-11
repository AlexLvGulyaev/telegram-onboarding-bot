import asyncio
import logging
import logging.config
from pathlib import Path

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
from schemas import TrainingTopicConfig
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

    async with session_factory() as session:
        topic_repository = TrainingTopicRepository(session)
        existing_ids = {topic.id for topic in await topic_repository.list_all()}
        # Seed database with built-in topics from disk. Idempotent: skips existing topics.
        topic_files = sorted(Path("topics").glob("*.json"))
        if not topic_files:
            raise RuntimeError(
                "No topic files found in topics/ and no topics in database. "
                "Create at least one topic file or use /new_topic after first start."
            )
        for topic_path in topic_files:
            try:
                topic = TrainingTopicConfig.model_validate_json(
                    topic_path.read_text(encoding="utf-8")
                )
                if topic.id not in existing_ids:
                    await topic_repository.create_or_update(topic)
            except Exception:
                logger.exception("Failed to seed topic from %s", topic_path)

        settings_repository = BotSettingsRepository(session)
        active_topic_id = await settings_repository.get_active_topic_id()
        if active_topic_id:
            topic = await topic_repository.get_by_id(active_topic_id)
            if topic is None:
                logger.warning(
                    "Active topic %r not found in database, resetting active topic", active_topic_id
                )
                await settings_repository.set_active_topic_id(None)
            else:
                settings.active_topic_id = active_topic_id

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
