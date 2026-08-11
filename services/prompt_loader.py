"""Load versioned prompts and response schemas for the training bot."""

import json
from pathlib import Path

from schemas import TrainingTopicConfig


class PromptLoader:
    def __init__(self, prompts_dir: Path) -> None:
        self._prompts_dir = prompts_dir

    def load_system_prompt(self, version: str) -> str:
        path = self._prompts_dir / version / "system.md"
        return path.read_text(encoding="utf-8").strip()

    def load_response_schema(self, version: str) -> dict:
        path = self._prompts_dir / version / "response-schema.json"
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def render_system_prompt(
        self,
        topic_config: TrainingTopicConfig,
        total_questions: int,
    ) -> str:
        template = self.load_system_prompt(topic_config.prompts_version)
        return (
            template.replace("{{topic}}", topic_config.name)
            .replace("{{material}}", topic_config.material)
            .replace("{{total_questions}}", str(total_questions))
        )
