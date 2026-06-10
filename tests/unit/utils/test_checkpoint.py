"""Tests for CheckpointManager in src.utils.checkpoint."""

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from src.utils.checkpoint import CheckpointManager


class DummyModel(BaseModel):
    name: str
    value: int


class TestCheckpointManager:
    """Test CheckpointManager CRUD operations."""

    @pytest.fixture
    def manager(self, tmp_path):
        return CheckpointManager(tmp_path)

    def test_save_pydantic_model(self, manager, tmp_path):
        model = DummyModel(name="test", value=42)
        filepath = manager.save("test_stage", model)
        assert filepath.exists()
        with open(filepath) as f:
            data = json.load(f)
        assert data["name"] == "test"
        assert data["value"] == 42

    def test_save_dict(self, manager, tmp_path):
        data = {"key": "value", "nested": {"a": 1}}
        filepath = manager.save("test_stage", data)
        assert filepath.exists()
        with open(filepath) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_load_returns_data(self, manager):
        manager.save("stage_a", {"x": 10, "y": 20})
        result = manager.load("stage_a")
        assert result == {"x": 10, "y": 20}

    def test_load_nonexistent_returns_none(self, manager):
        result = manager.load("does_not_exist")
        assert result is None

    def test_exists_true_for_saved_stage(self, manager):
        manager.save("my_stage", {"data": "here"})
        assert manager.exists("my_stage") is True

    def test_exists_false_for_missing_stage(self, manager):
        assert manager.exists("missing_stage") is False

    def test_clear_removes_all_checkpoints(self, manager, tmp_path):
        manager.save("stage_a", {"a": 1})
        manager.save("stage_b", {"b": 2})
        manager.clear()
        checkpoint_dir = tmp_path / ".checkpoint"
        assert not checkpoint_dir.exists()

    def test_custom_filename(self, manager):
        manager.save("stage_x", {"special": True}, filename="custom.json")
        result = manager.load("stage_x", filename="custom.json")
        assert result == {"special": True}

    def test_handles_nested_directories(self, manager, tmp_path):
        """save creates nested stage directories as needed."""
        manager.save("deep/nested/stage", {"deep": True})
        result = manager.load("deep/nested/stage")
        assert result == {"deep": True}

    def test_overwrite_existing_checkpoint(self, manager):
        manager.save("stage", {"version": 1})
        manager.save("stage", {"version": 2})
        result = manager.load("stage")
        assert result == {"version": 2}

    def test_save_unserializable_data_raises(self, manager):
        """Raises CheckpointError for unserializable data."""
        from src.utils.errors import CheckpointError

        class Unserializable:
            pass

        with pytest.raises(CheckpointError):
            manager.save("bad_stage", {"obj": Unserializable()})

    def test_load_corrupted_json_raises(self, manager, tmp_path):
        """Raises CheckpointError for corrupted checkpoint file."""
        from src.utils.errors import CheckpointError

        # Manually create a corrupted checkpoint file
        stage_dir = tmp_path / ".checkpoint" / "corrupt_stage"
        stage_dir.mkdir(parents=True)
        (stage_dir / "data.json").write_text("{invalid json!!!")

        with pytest.raises(CheckpointError):
            manager.load("corrupt_stage")

    def test_clear_nonexistent_directory(self, tmp_path):
        """Clear handles case where checkpoint dir doesn't exist."""
        manager = CheckpointManager(tmp_path)
        # Don't save anything, just clear
        manager.clear()  # Should not raise
