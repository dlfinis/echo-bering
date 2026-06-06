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
