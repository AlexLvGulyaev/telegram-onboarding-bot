import logging
import re

from database.models import TrainingResult
from database.repository import TrainingResultRepository
from schemas import TrainingAssistantTurn, TrainingResultCreate, TrainingSessionDraft, TrainingTurnLogEntry

logger = logging.getLogger(__name__)


class TrainingServiceError(Exception):
    pass


class TrainingService:
    _END_LEARNING_KEYWORDS = (
        "готов",
        "начинай",
        "проверим",
        "тест",
        "давай",
        "переходи",
        "перейдем",
        "экзамен",
    )

    @staticmethod
    def validate_employee_name(value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if len(cleaned) < 2:
            raise ValueError("Укажите имя сотрудника хотя бы из двух символов.")
        return cleaned

    def start_session(self, total_questions: int) -> TrainingSessionDraft:
        return TrainingSessionDraft(total_questions=total_questions)

    def register_employee_name(self, draft: TrainingSessionDraft, employee_name: str) -> TrainingSessionDraft:
        updated = TrainingSessionDraft.model_validate(draft.model_dump())
        updated.employee_name = self.validate_employee_name(employee_name)
        updated.phase = "learning"
        return updated

    @staticmethod
    def wants_to_start_test(user_message: str) -> bool:
        text = user_message.lower()
        return any(keyword in text for keyword in TrainingService._END_LEARNING_KEYWORDS)

    @staticmethod
    def _is_question(value: str | None) -> bool:
        if not value:
            return False
        return "?" in value or value.strip().endswith("?")

    @staticmethod
    def _extract_question_from_reply(reply: str) -> str | None:
        """Try to extract the last question-looking sentence from reply."""
        if not reply:
            return None
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", reply) if s.strip()]
        for sentence in reversed(sentences):
            if "?" in sentence:
                return sentence
        return None

    @staticmethod
    def _normalize_question(value: str) -> str:
        """Strip framing words and punctuation so duplicates are detected reliably."""
        lowered = value.lower()
        lowered = re.sub(
            r"^(?:первый|второй|третий|четвертый|пятый|шестой|седьмой|восьмой|девятый|десятый|следующий|такой|новый)\s+(?:вопрос[:\?]?\s*)",
            "",
            lowered,
        )
        lowered = re.sub(r"[^\w\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered

    def _is_duplicate(self, new: str, asked: list[str]) -> bool:
        """Detect exact/semantic duplicates using normalisation and keyword overlap."""
        new_normalized = self._normalize_question(new)
        if not new_normalized:
            return False
        new_words = {w for w in re.findall(r"[а-яёa-z0-9]+", new_normalized) if len(w) > 3}
        for asked_q in asked:
            asked_normalized = self._normalize_question(asked_q)
            asked_words = {w for w in re.findall(r"[а-яёa-z0-9]+", asked_normalized) if len(w) > 3}
            if not asked_words:
                continue
            if new_normalized == asked_normalized:
                return True
            if not new_words:
                continue
            overlap = new_words & asked_words
            if len(overlap) >= 2 and len(overlap) / max(len(asked_words), 1) >= 0.5:
                return True
        return False

    def apply_ai_turn(
        self,
        current: TrainingSessionDraft,
        ai_turn: TrainingAssistantTurn,
        user_message: str,
    ) -> TrainingSessionDraft:
        updated = TrainingSessionDraft.model_validate(current.model_dump())

        logger.info(
            "apply_ai_turn start: current_phase=%s, current_question=%r, questions_answered=%d, "
            "asked=%s, ai_phase=%s, ai_next_question=%r, ai_evaluated=%s",
            current.phase,
            current.current_question,
            current.questions_answered,
            current.asked_questions,
            ai_turn.phase,
            ai_turn.next_question,
            ai_turn.latest_answer_evaluated,
        )

        # Transition learning -> testing is driven by user signal OR model signal
        forced_to_testing_by_keyword = False
        if current.phase == "learning" and ai_turn.phase == "testing":
            updated.phase = "testing"
        elif current.phase == "learning" and self.wants_to_start_test(user_message):
            updated.phase = "testing"
            forced_to_testing_by_keyword = True

        # If model thinks we are testing, ensure we are testing
        if current.phase == "testing" or ai_turn.phase == "testing":
            updated.phase = "testing"

        # Guard: no phase regression
        phase_order = {"collecting_name": 0, "learning": 1, "testing": 2, "completed": 3}
        if phase_order[ai_turn.phase] < phase_order[current.phase]:
            ai_turn.phase = current.phase

        # Evaluate answer first, before looking at the next question.
        # This ensures questions_answered always equals len(asked_questions).
        if (
            updated.phase == "testing"
            and current.current_question
            and ai_turn.latest_answer_evaluated
        ):
            updated.asked_questions.append(current.current_question)
            # Preserve the embedding of the answered question for future duplicate checks.
            if current.current_question_embedding:
                updated.asked_questions_embeddings.append(current.current_question_embedding)
            if ai_turn.answer_is_correct:
                updated.correct_answers += 1
            if ai_turn.answer_feedback is not None:
                updated.last_answer_feedback = ai_turn.answer_feedback
            logger.info(
                "Evaluated answer: asked_count=%d, correct_answers=%d, is_correct=%s",
                len(updated.asked_questions),
                updated.correct_answers,
                ai_turn.answer_is_correct,
            )

        # Determine the question text: prefer next_question, fallback to reply extraction
        effective_question = ai_turn.next_question
        if updated.phase == "testing" and not self._is_question(effective_question):
            extracted = self._extract_question_from_reply(ai_turn.reply)
            if extracted:
                effective_question = extracted
                logger.info("Extracted question from reply: %r", extracted)
            elif self._is_question(ai_turn.reply):
                effective_question = ai_turn.reply
            else:
                effective_question = None

        # If the user explicitly asked to start the test but the model returned a
        # meta/ready question in its reply, ignore it and ask a real question via fallback.
        if forced_to_testing_by_keyword and not self._is_question(ai_turn.next_question):
            logger.info("Ignoring extracted meta-question after keyword-driven transition to testing")
            effective_question = None

        # Skip duplicate questions. The answer above has already been counted,
        # so the duplicate does not inflate the score: len(asked_questions)
        # remains the real number of unique questions answered.
        if effective_question and self._is_duplicate(effective_question, updated.asked_questions):
            logger.info("Rejected duplicate question: %r", effective_question)
            effective_question = None

        updated.current_question = effective_question

        # Recalculate the canonical counters from the list of unique asked questions.
        updated.questions_answered = len(updated.asked_questions)

        # Track token spend for the turn.
        updated.total_tokens_spent += ai_turn.total_tokens
        updated.turns_log.append(
            TrainingTurnLogEntry(
                phase=ai_turn.phase,
                reply_preview=ai_turn.reply,
                prompt_tokens=ai_turn.prompt_tokens,
                completion_tokens=ai_turn.completion_tokens,
                total_tokens=ai_turn.total_tokens,
            )
        )

        # Hard cap: never allow more unique questions than planned. When the cap
        # is reached we force completion and drop any extra question the model tried
        # to ask. This prevents models from losing count and asking question N+1.
        if updated.questions_answered >= updated.total_questions:
            updated.phase = "completed"
            updated.current_question = None
            if ai_turn.final_summary is not None:
                updated.final_summary = ai_turn.final_summary
        # If the model itself signalled completion, make sure it actually has enough answers.
        elif ai_turn.phase == "completed":
            if updated.questions_answered >= updated.total_questions:
                updated.phase = "completed"
                if ai_turn.final_summary is not None:
                    updated.final_summary = ai_turn.final_summary
            else:
                updated.phase = "testing"

        logger.info(
            "apply_ai_turn end: phase=%s, current_question=%r, questions_answered=%d, "
            "asked=%s, completed=%s",
            updated.phase,
            updated.current_question,
            updated.questions_answered,
            updated.asked_questions,
            updated.phase == "completed",
        )

        return updated

    def should_request_question(self, draft: TrainingSessionDraft) -> bool:
        """True when bot is in testing phase but has no valid current question.

        This intentionally ignores questions_answered: a duplicate question that
        was rejected leaves the session without a current_question, so we must
        request a replacement even if the score counter has reached total_questions.
        Completion is decided only after we genuinely have no question and enough
        unique answers have been recorded.
        """
        needs = draft.phase == "testing" and not draft.current_question
        logger.info("should_request_question: phase=%s, answered=%d, total=%d, current=%r, needs=%s",
                    draft.phase, draft.questions_answered, draft.total_questions, draft.current_question, needs)
        return needs

    async def ensure_summary(
        self,
        ai_training_service: "AITrainingService",
        draft: TrainingSessionDraft,
    ) -> TrainingSessionDraft:
        """Ensure the draft has a final summary before saving the result."""
        if draft.final_summary:
            return draft
        logger.info("Final summary missing, generating fallback summary")
        summary_turn = await ai_training_service.generate_summary(draft)
        draft = TrainingSessionDraft.model_validate(draft.model_dump())
        draft.total_tokens_spent += summary_turn.total_tokens
        draft.turns_log.append(
            TrainingTurnLogEntry(
                phase=summary_turn.phase,
                reply_preview=summary_turn.reply,
                prompt_tokens=summary_turn.prompt_tokens,
                completion_tokens=summary_turn.completion_tokens,
                total_tokens=summary_turn.total_tokens,
            )
        )
        if summary_turn.final_summary:
            draft.final_summary = summary_turn.final_summary
        else:
            draft.final_summary = summary_turn.reply
        return draft

    async def create_result(
        self,
        repository: TrainingResultRepository,
        draft: TrainingSessionDraft,
        topic: str,
        telegram_user_id: int,
        telegram_chat_id: int,
    ) -> TrainingResult:
        result_in = TrainingResultCreate(
            employee_name=draft.employee_name or "Неизвестный сотрудник",
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            topic=topic,
            total_questions=draft.total_questions,
            correct_answers=draft.correct_answers,
            score_percent=draft.score_percent(),
            final_summary=draft.final_summary,
            total_tokens_spent=draft.total_tokens_spent,
        )
        return await repository.create(result_in)
