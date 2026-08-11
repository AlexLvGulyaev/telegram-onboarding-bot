import json
import logging
from collections.abc import Sequence

import httpx
import numpy as np

from config import Settings
from schemas import LLMContext, TrainingAssistantTurn, TrainingSessionDraft, TrainingTopicConfig
from services.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)


class AITrainingService:
    # Cosine similarity threshold above which two questions are considered duplicates.
    # Short questions in Russian tend to cluster below the typical 0.80-0.85 range,
    # so a slightly lower threshold catches paraphrases without false positives.
    _DUPLICATE_EMBEDDING_THRESHOLD = 0.72

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._topic_config: TrainingTopicConfig | None = None
        self._prompt_loader = PromptLoader(settings.prompts_dir)
        self._client = httpx.AsyncClient(
            base_url=settings.openai_base_url,
            timeout=httpx.Timeout(120.0, connect=30.0),
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
        )

    def set_topic_config(self, topic_config: TrainingTopicConfig) -> None:
        self._topic_config = topic_config

    def _current_topic_config(self) -> TrainingTopicConfig:
        if self._topic_config is None:
            raise RuntimeError("Topic config is not set. Call set_topic_config() before generate_turn().")
        return self._topic_config

    async def generate_turn(
        self,
        draft: TrainingSessionDraft,
        user_message: str,
        is_new_dialogue: bool,
    ) -> TrainingAssistantTurn:
        topic_config = self._current_topic_config()
        system_content = self._prompt_loader.render_system_prompt(
            topic_config=topic_config,
            total_questions=draft.total_questions,
        )
        user_content = self._build_prompt(
            draft=draft,
            user_message=user_message,
            is_new_dialogue=is_new_dialogue,
        )
        payload = {
            "model": self._settings.openai_model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": self._prompt_loader.load_response_schema(
                    topic_config.prompts_version
                ),
            },
        }

        logger.info("OpenAI request: model=%s, user_message=%r", self._settings.openai_model, user_message)
        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        response_data = response.json()
        content = response_data["choices"][0]["message"]["content"]
        usage = response_data.get("usage", {})
        logger.info(
            "OpenAI raw response: %s | usage: prompt=%s completion=%s total=%s",
            content,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            usage.get("total_tokens"),
        )
        turn = TrainingAssistantTurn.model_validate(json.loads(content))
        turn.prompt_tokens = int(usage.get("prompt_tokens") or 0)
        turn.completion_tokens = int(usage.get("completion_tokens") or 0)
        turn.total_tokens = int(usage.get("total_tokens") or 0)
        logger.info(
            "OpenAI parsed turn: reply=%r, phase=%s, evaluated=%s, correct=%s, "
            "feedback=%r, next_question=%r, final_summary=%r, tokens=%s",
            turn.reply,
            turn.phase,
            turn.latest_answer_evaluated,
            turn.answer_is_correct,
            turn.answer_feedback,
            turn.next_question,
            turn.final_summary,
            turn.total_tokens,
        )
        return turn

    async def request_question(
        self,
        draft: TrainingSessionDraft,
    ) -> TrainingAssistantTurn:
        """Extra call when guard-logic detected a missing or invalid question."""
        user_message = (
            "Ты находишься в фазе testing. "
            f"Уже задано {draft.questions_answered} из {draft.total_questions} вопросов. "
            f"Уже заданные вопросы: {json.dumps(draft.asked_questions, ensure_ascii=False)}. "
            "Задай следующий вопрос по материалу, который проверяет факт, ещё не покрытый в списке выше. "
            "Вопрос должен быть вопросительным предложением, не должен повторять уже заданные по смыслу и должен быть в поле next_question."
        )
        logger.info("Guard fallback: requesting question explicitly")
        return await self.generate_turn(
            draft=draft,
            user_message=user_message,
            is_new_dialogue=False,
        )

    async def generate_summary(
        self,
        draft: TrainingSessionDraft,
    ) -> TrainingAssistantTurn:
        """Generate a final summary when the model failed to produce one."""
        user_message = (
            "Тест завершён. Составь краткий итог для сотрудника на основе результата. "
            f"Всего вопросов: {draft.total_questions}. Правильных ответов: {draft.correct_answers}. "
            f"Процент: {draft.score_percent()}%. "
            f"Список заданных вопросов: {json.dumps(draft.asked_questions, ensure_ascii=False)}. "
            "Укажи сильные стороны и что стоит повторить. Ответ верни в поле final_summary, phase=completed."
        )
        logger.info("Summary fallback: generating final summary explicitly")
        return await self.generate_turn(
            draft=draft,
            user_message=user_message,
            is_new_dialogue=False,
        )

    async def get_embeddings(self, texts: Sequence[str]) -> list[list[float]]:
        """Fetch OpenAI embeddings for a batch of texts."""
        if not texts:
            return []
        payload = {
            "model": "text-embedding-3-small",
            "input": list(texts),
        }
        logger.info("OpenAI embeddings request: texts=%d", len(texts))
        response = await self._client.post("/embeddings", json=payload)
        response.raise_for_status()
        data = response.json()["data"]
        # Sort by index because API does not guarantee order.
        sorted_data = sorted(data, key=lambda item: item["index"])
        return [item["embedding"] for item in sorted_data]

    def _embedding_is_duplicate(self, new_embedding: list[float], asked_embeddings: Sequence[list[float]]) -> tuple[bool, float]:
        """Return (is_duplicate, max_similarity) for a precomputed embedding."""
        if not asked_embeddings:
            return False, 0.0
        new_vec = np.array(new_embedding, dtype=np.float32)
        asked_matrix = np.array(asked_embeddings, dtype=np.float32)
        new_norm = new_vec / (np.linalg.norm(new_vec) or 1.0)
        asked_norms = asked_matrix / np.linalg.norm(asked_matrix, axis=1, keepdims=True)
        similarities = np.dot(asked_norms, new_norm)
        max_similarity = float(np.max(similarities)) if similarities.size else 0.0
        return max_similarity >= self._DUPLICATE_EMBEDDING_THRESHOLD, max_similarity

    async def is_semantic_duplicate(
        self,
        new_question: str,
        asked_questions: Sequence[str],
        asked_embeddings: Sequence[list[float]],
    ) -> tuple[bool, list[float] | None]:
        """Check if new_question is semantically equivalent to any asked question.

        Returns a tuple (is_duplicate, embedding) so callers can reuse the embedding
        instead of paying for a second API call.
        """
        if not asked_questions or not asked_embeddings:
            embedding = (await self.get_embeddings([new_question]))[0] if new_question else None
            return False, embedding
        new_embeddings = await self.get_embeddings([new_question])
        if not new_embeddings:
            return False, None
        new_embedding = new_embeddings[0]
        is_duplicate, max_similarity = self._embedding_is_duplicate(new_embedding, asked_embeddings)
        logger.info(
            "Semantic duplicate check: new=%r, max_similarity=%.3f, threshold=%.3f, is_duplicate=%s",
            new_question,
            max_similarity,
            self._DUPLICATE_EMBEDDING_THRESHOLD,
            is_duplicate,
        )
        return is_duplicate, new_embedding

    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _build_prompt(
        draft: TrainingSessionDraft,
        user_message: str,
        is_new_dialogue: bool,
    ) -> str:
        compact_context = draft.to_llm_context()
        serialized_draft = json.dumps(compact_context.model_dump(), ensure_ascii=False, indent=2)
        return (
            f"Новая сессия: {str(is_new_dialogue).lower()}\n"
            f"Текущее состояние сессии:\n{serialized_draft}\n\n"
            f"Последнее сообщение сотрудника:\n{user_message}\n\n"
            "Формат ответа — JSON со следующими полями:\n"
            "- reply: текст, который видит сотрудник. Когда задаёшь вопрос теста, сам вопрос должен быть в reply.\n"
            "- phase: learning | testing | completed.\n"
            "- latest_answer_evaluated: true только если в этом ходу ты оценил ответ сотрудника на вопрос теста.\n"
            "- answer_is_correct и answer_feedback: заполняй только вместе с latest_answer_evaluated=true.\n"
            "- next_question: техническая копия вопроса из reply. Заполняй всегда, когда phase=testing и задаёшь вопрос; иначе null.\n"
            "- final_summary: только при phase=completed.\n\n"
            "Учитывай текущее состояние:\n"
            "- phase=learning: если сотрудник сигнализирует о готовности (готов/давай/тест/экзамен/переходим), установи phase=testing и задай первый вопрос по материалу в next_question и reply. Иначе продолжай обучать и в конце спроси готовность.\n"
            "- phase=testing и current_question задан: оцени ответ на current_question, поставь latest_answer_evaluated=true.\n"
            "- phase=testing после оценки: задай следующий вопрос в next_question (вопросительное предложение со знаком вопроса).\n"
            "- next_question не должен повторять по смыслу вопросы из asked_questions — выбери факт, ещё не покрытый в asked_questions.\n"
            "- Когда questions_answered == total_questions: next_question=null и phase=completed.\n"
            "- completed разрешён только когда questions_answered == total_questions."
        )
