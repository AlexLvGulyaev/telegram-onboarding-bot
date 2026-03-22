import json

import httpx

from config import Settings
from schemas import TrainingAssistantTurn, TrainingSessionDraft
from services.ai_training_prompts import AI_TRAINING_RESPONSE_SCHEMA, build_training_system_prompt


class AITrainingService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._training_material = settings.get_training_material()
        self._client = httpx.AsyncClient(
            base_url=settings.openai_base_url,
            timeout=httpx.Timeout(120.0, connect=30.0),
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
        )

    async def generate_turn(
        self,
        draft: TrainingSessionDraft,
        user_message: str,
        is_new_dialogue: bool,
    ) -> TrainingAssistantTurn:
        payload = {
            "model": self._settings.openai_model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": build_training_system_prompt(
                        topic=self._settings.training_topic,
                        material=self._training_material,
                        total_questions=draft.total_questions,
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_prompt(
                        draft=draft,
                        user_message=user_message,
                        is_new_dialogue=is_new_dialogue,
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": AI_TRAINING_RESPONSE_SCHEMA,
            },
        }

        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return TrainingAssistantTurn.model_validate(json.loads(content))

    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _build_prompt(
        draft: TrainingSessionDraft,
        user_message: str,
        is_new_dialogue: bool,
    ) -> str:
        serialized_draft = json.dumps(draft.model_dump(), ensure_ascii=False, indent=2)
        return (
            f"Новая сессия: {str(is_new_dialogue).lower()}\n"
            f"Текущее состояние сессии:\n{serialized_draft}\n\n"
            f"Последнее сообщение сотрудника:\n{user_message}\n\n"
            "Важно:\n"
            "- если phase сейчас learning, сначала обучай и только потом переводи в testing;\n"
            "- если phase сейчас testing и current_question заполнен, оцени именно ответ на current_question;\n"
            "- questions_answered уже содержит число проверенных ответов;\n"
            "- когда проверенных ответов станет столько же, сколько total_questions, заверши сессию через phase=completed."
        )
