"""Checkpoint management using filesystem JSON files.

Saves and loads intermediate pipeline artifacts in `.checkpoint/stage/` directories.
"""

import json
import shutil
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

from src.utils.errors import CheckpointError


class CheckpointManager:
    """Manage checkpoint files for pipeline stage resumption."""

    def __init__(self, output_dir: Path):
        self.checkpoint_dir = output_dir / ".checkpoint"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save(self, stage: str, data: Any, filename: str = "data.json") -> Path:
        """Save checkpoint data as JSON in the stage directory.

        Args:
            stage: Pipeline stage name (e.g., "asr", "segmentation").
            data: Pydantic model or dict to serialize.
            filename: Name of the checkpoint file within the stage dir.

        Returns:
            Path to the saved checkpoint file.
        """
        stage_dir = self.checkpoint_dir / stage
        stage_dir.mkdir(parents=True, exist_ok=True)
        filepath = stage_dir / filename

        try:
            if isinstance(data, BaseModel):
                content = data.model_dump()
            else:
                content = data
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(content, f, indent=2)
        except (OSError, TypeError) as e:
            raise CheckpointError(f"Failed to save checkpoint for stage '{stage}': {e}")

        return filepath

    def load(self, stage: str, filename: str = "data.json") -> Optional[Any]:
        """Load checkpoint data from JSON.

        Args:
            stage: Pipeline stage name.
            filename: Name of the checkpoint file.

        Returns:
            Loaded data dict, or None if checkpoint does not exist.
        """
        filepath = self.checkpoint_dir / stage / filename
        if not filepath.exists():
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise CheckpointError(f"Failed to load checkpoint for stage '{stage}': {e}")

    def exists(self, stage: str) -> bool:
        """Check if a checkpoint exists for the given stage.

        Args:
            stage: Pipeline stage name.

        Returns:
            True if the stage directory exists.
        """
        return (self.checkpoint_dir / stage).exists()

    def clear(self) -> None:
        """Delete all checkpoint files."""
        if self.checkpoint_dir.exists():
            shutil.rmtree(self.checkpoint_dir)
