"""Transcription domain models."""

from typing import List, Optional

from pydantic import BaseModel, Field

from src.providers.asr.base import TranscriptResult, WordTimestamp


class TranscriptionAttempt(BaseModel):
    """Track a single transcription attempt for cost and retry tracking."""

    attempt_number: int
    provider: str
    strategy: str  # "full" or "chunk"
    chunk_index: Optional[int] = None
    cost_usd: float = 0.0
    success: bool = False
    error_message: Optional[str] = None


class TranscriptionSummary(BaseModel):
    """Summary of the full transcription process."""

    result: TranscriptResult
    attempts: List[TranscriptionAttempt] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    used_chunking: bool = False
    chunk_count: int = 0
    failed_chunks: int = 0
