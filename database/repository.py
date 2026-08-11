from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BotSettings, TrainingResult, TrainingTopic
from schemas import TrainingResultCreate, TrainingTopicConfig


class TrainingResultRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, result_in: TrainingResultCreate) -> TrainingResult:
        result = TrainingResult(**result_in.model_dump())
        self._session.add(result)
        await self._session.commit()
        await self._session.refresh(result)
        return result

    async def get_by_id(self, result_id: int) -> TrainingResult | None:
        statement = select(TrainingResult).where(TrainingResult.id == result_id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()


class BotSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _load_or_create(self) -> BotSettings:
        statement = select(BotSettings).order_by(BotSettings.id.desc()).limit(1)
        result = await self._session.execute(statement)
        settings = result.scalar_one_or_none()
        if settings is None:
            settings = BotSettings()
            self._session.add(settings)
            await self._session.commit()
            await self._session.refresh(settings)
        return settings

    async def get_active_topic_id(self) -> str | None:
        settings = await self._load_or_create()
        return settings.active_topic_id

    async def set_active_topic_id(self, topic_id: str | None) -> BotSettings:
        settings = await self._load_or_create()
        settings.active_topic_id = topic_id
        await self._session.commit()
        await self._session.refresh(settings)
        return settings


class TrainingTopicRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_or_update(self, topic: TrainingTopicConfig) -> TrainingTopic:
        existing = await self.get_by_id(topic.id)
        if existing:
            existing.name = topic.name
            existing.description = topic.description
            existing.material = topic.material
            existing.prompts_version = topic.prompts_version
        else:
            db_topic = TrainingTopic(
                id=topic.id,
                name=topic.name,
                description=topic.description,
                material=topic.material,
                prompts_version=topic.prompts_version,
            )
            self._session.add(db_topic)
        await self._session.commit()
        return await self.get_by_id(topic.id)

    async def get_by_id(self, topic_id: str) -> TrainingTopic | None:
        statement = select(TrainingTopic).where(TrainingTopic.id == topic_id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[TrainingTopic]:
        statement = select(TrainingTopic).order_by(TrainingTopic.id)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def delete(self, topic_id: str) -> bool:
        topic = await self.get_by_id(topic_id)
        if topic is None:
            return False
        await self._session.delete(topic)
        await self._session.commit()
        return True
