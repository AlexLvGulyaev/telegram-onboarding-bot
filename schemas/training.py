from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned or None


class TrainingTopicConfig(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    material: str = Field(min_length=10, max_length=8000)
    prompts_version: str = Field(default="v1", min_length=1, max_length=32)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not value.replace("-", "").replace("_", "").isalnum():
            raise ValueError("id must contain only letters, digits, hyphens and underscores")
        return value

    @field_validator("name", "description", "material")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _normalize_text(value)


class TrainingResultCreate(BaseModel):
    employee_name: str = Field(min_length=2, max_length=255)
    telegram_user_id: int
    telegram_chat_id: int
    topic: str = Field(min_length=2, max_length=255)
    total_questions: int = Field(ge=1, le=20)
    correct_answers: int = Field(ge=0, le=20)
    score_percent: int = Field(ge=0, le=100)
    final_summary: str | None = Field(default=None, max_length=4000)
    total_tokens_spent: int = Field(default=0, ge=0)

    @field_validator("employee_name", "topic", "final_summary")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _normalize_text(value)


class TrainingResultRead(TrainingResultCreate):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TrainingTurnLogEntry(BaseModel):
    phase: str
    reply_preview: str
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class TrainingSessionDraft(BaseModel):
    employee_name: str | None = None
    phase: Literal["collecting_name", "learning", "testing", "completed"] = "collecting_name"
    total_questions: int = Field(default=5, ge=1, le=20)
    questions_answered: int = Field(default=0, ge=0, le=20)
    correct_answers: int = Field(default=0, ge=0, le=20)
    current_question: str | None = None
    current_question_embedding: list[float] | None = None
    asked_questions: list[str] = Field(default_factory=list)
    asked_questions_embeddings: list[list[float]] = Field(default_factory=list)
    last_answer_feedback: str | None = None
    final_summary: str | None = None
    total_tokens_spent: int = Field(default=0, ge=0)
    turns_log: list[TrainingTurnLogEntry] = Field(default_factory=list)

    @field_validator("employee_name", "current_question", "last_answer_feedback", "final_summary")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_text(value)

    def remaining_questions(self) -> int:
        return max(self.total_questions - self.questions_answered, 0)

    def score_percent(self) -> int:
        if self.total_questions == 0:
            return 0
        effective_correct = min(self.correct_answers, self.total_questions)
        return round((effective_correct / self.total_questions) * 100)

    def format_turns_log(self) -> str:
        if not self.turns_log:
            return "Нет записанных ходов."
        lines = ["Ход | Фаза | Токены (prompt/completion/total) | Текст"]
        for idx, entry in enumerate(self.turns_log, start=1):
            preview = entry.reply_preview[:40] + "..." if len(entry.reply_preview) > 40 else entry.reply_preview
            lines.append(
                f"{idx:2d} | {entry.phase:<8} | "
                f"{entry.prompt_tokens}/{entry.completion_tokens}/{entry.total_tokens} | {preview}"
            )
        lines.append(f"Итого токенов: {self.total_tokens_spent}")
        return "\n".join(lines)

    def to_llm_context(self) -> "LLMContext":
        return LLMContext(
            phase=self.phase,
            total_questions=self.total_questions,
            questions_answered=self.questions_answered,
            correct_answers=self.correct_answers,
            current_question=self.current_question,
            asked_questions=self.asked_questions,
            employee_name=self.employee_name,
        )


class LLMContext(BaseModel):
    """Compact state exposed to the LLM prompt.

    Never include embeddings, turns_log, or any other large/auxiliary state here.
    """

    phase: Literal["collecting_name", "learning", "testing", "completed"]
    total_questions: int = Field(ge=1, le=20)
    questions_answered: int = Field(ge=0, le=20)
    correct_answers: int = Field(ge=0, le=20)
    current_question: str | None = None
    asked_questions: list[str] = Field(default_factory=list)
    employee_name: str | None = None


class TrainingAssistantTurn(BaseModel):
    reply: str = Field(min_length=1)
    phase: Literal["learning", "testing", "completed"]
    latest_answer_evaluated: bool = False
    answer_is_correct: bool | None = None
    answer_feedback: str | None = None
    next_question: str | None = None
    final_summary: str | None = None
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    @field_validator("reply", "answer_feedback", "next_question", "final_summary")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_text(value)
