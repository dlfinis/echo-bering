# Design: Echo-Bering Core Pipeline

## Technical Approach

This design implements a **four-layer pipeline architecture** that transforms video files into enriched chapter packages. The design follows the approved spec (33 requirements, 43 scenarios) and adheres to the architectural principles in `arch-vision.md`.

**Key architectural decisions**:

1. **Provider-as-Visitors Pattern**: External providers (Groq, AssemblyAI, OpenAI, DeepSeek) are abstracted through interfaces. The domain layer never references concrete provider implementations.

2. **Filesystem as Database**: All intermediate artifacts are stored in `.checkpoint/` directory. The final output is self-contained chapter folders with no external dependencies.

3. **Adaptive Chunking**: Full audio is attempted first; chunking only occurs when providers reject oversized files with specific error codes.

4. **Checkpoint-Based Resumption**: Each pipeline stage saves checkpoints, enabling recovery from mid-run failures without reprocessing.

5. **Strategy for Chunking**: Two strategies implemented—`full` (attempt entire audio) and `timed` (split by duration with overlap).

---

## Architecture Decisions

### Decision: Four-Layer Architecture

**Choice**: Separate pipeline into Orchestration → Processing → Adaptation → External layers

**Alternatives considered**:
- Single monolithic pipeline class (rejected: violates single responsibility, hard to test)
- Event-driven architecture with message queue (rejected: overkill for CLI tool, adds complexity)
- Microservices split (rejected: scope creep, adds infrastructure dependencies)

**Rationale**: The four-layer pattern matches `arch-vision.md` exactly, provides clear boundaries for testing, and allows provider swapping without touching domain logic. Each layer has a single, well-defined responsibility:

- **Orchestration**: Coordinates stages, manages checkpoints, enforces budget
- **Processing**: Domain logic (transcription, segmentation, enrichment, materialization)
- **Adaptation**: Provider implementations and ffmpeg wrappers
- **External**: APIs, filesystem, subprocess calls

---

### Decision: Pydantic Models for All Contracts

**Choice**: Use Pydantic v2 models for all data structures passed between layers

**Alternatives considered**:
- Dataclasses (rejected: less validation, no JSON schema generation)
- Pure dicts (rejected: no type safety, runtime errors)
- TypedDict (rejected: limited validation, no nested models)

**Rationale**: Pydantic provides runtime validation, JSON schema generation for API contracts, and seamless serialization/deserialization. V2's performance improvements make it suitable for high-throughput scenarios.

---

### Decision: Factory Pattern for Provider Instantiation

**Choice**: Use factory functions in `providers/factory.py` to instantiate providers based on config

**Alternatives considered**:
- Dependency injection container (rejected: overkill for this scope)
- Direct instantiation in orchestrator (rejected: violates separation, hard to test)
- Registry pattern with string keys (rejected: runtime errors on typos)

**Rationale**: Factory functions are simple, testable, and provide compile-time safety through type hints. Config-driven instantiation is straightforward and matches the "provider-as-visitor" pattern.

---

### Decision: Event-Based TUI Updates

**Choice**: Use Rich's `Live` context manager with custom `ProgressEvent` dataclass for TUI updates

**Alternatives considered**:
- Textual (rejected: full TUI framework, overkill for progress display)
- Raw print statements (rejected: no real-time updates, flickering)
- Asyncio with curses (rejected: complexity not justified for CLI tool)

**Rationale**: Rich's `Live` provides smooth real-time progress updates with minimal code. The `ProgressEvent` dataclass allows structured data (stage, percentage, cost, messages) to be passed to the renderer.

---

### Decision: Exponential Backoff with Jitter for Retries

**Choice**: Implement retry policy using `backoff` library with jitter (1s base, 2x multiplier, max 10s)

**Alternatives considered**:
- Simple linear retry (rejected: thundering herd problem)
- Custom retry loop (rejected: reinventing wheel, error-prone)
- Tenacity library (rejected: similar to backoff, backoff is lighter)

**Rationale**: Exponential backoff with jitter prevents thundering herd problems and handles transient failures gracefully. The `backoff` library is lightweight and battle-tested.

---

### Decision: Filesystem Checkpointing with Structured Artifacts

**Choice**: Save checkpoints as JSON files in `.checkpoint/stage_name/` directory

**Alternatives considered**:
- SQLite database (rejected: adds dependency, overkill for CLI tool)
- Pickle files (rejected: security risk, not human-readable)
- In-memory state with no persistence (rejected: no recovery from crashes)

**Rationale**: JSON files are human-readable, portable, and easily debugged. Structured artifacts (e.g., `.checkpoint/asr/raw_transcript.json`) allow partial recovery and inspection.

---

### Decision: Strategy Pattern for Chunking

**Choice**: Implement `ChunkingStrategy` abstract base class with `FullAudioStrategy` and `TimedChunkingStrategy`

**Alternatives considered**:
- Conditional logic in transcriber (rejected: violates single responsibility)
- Hardcoded chunk size (rejected: inflexible for different video lengths)
- Config-driven without strategy pattern (rejected: no polymorphism benefits)

**Rationale**: Strategy pattern allows adding new chunking strategies (e.g., `SemanticChunkingStrategy` for future) without modifying the transcriber. Each strategy encapsulates its own chunk boundary calculation and reassembly logic.

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  INPUT                                                                      │
│  video.mp4 + config.yaml + .env                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ORCHESTRATION LAYER (pipeline.py)                                          │
│  - Load config (Pydantic validation)                                        │
│  - Build execution plan (stage sequence)                                    │
│  - Check for resume (checkpoint detection)                                  │
│  - Enforce budget (cost tracking)                                           │
│  - Coordinate stages with checkpoint persistence                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
┌─────────────────────────────┐ ┌─────────────────────────────┐ ┌─────────────────────────────┐
│  PROCESSING LAYER           │ │  PROCESSING LAYER           │ │  PROCESSING LAYER           │
│  (domain logic, provider-   │ │  (domain logic, provider-   │ │  (domain logic, provider-   │
│   agnostic)                 │ │   agnostic)                 │ │   agnostic)                 │
│                             │ │                             │ │                             │
│  AudioExtractor             │ │  Transcriber                │ │  Segmenter                  │
│  - ffmpeg wrapper           │ │  - ASR invocation           │ │  - LLM prompt injection     │
│  - 16kHz mono WAV output    │ │  - Adaptive chunking        │ │  - JSON schema validation   │
│                             │ │  - Transcript reassembly    │ │                             │
│                             │ │                             │ │  Enricher                   │
│                             │ │                             │ │  - Load enricher prompt     │
│                             │ │                             │ │  - Inject chapter context   │
│                             │ │                             │ │  - Parse enriched metadata  │
│                             │ │                             │ │                             │
│                             │ │                             │ │  Materializer               │
│                             │ │                             │ │  - Chapter folder creation  │
│                             │ │                             │ │  - Video clip (ffmpeg cut)  │
│                             │ │                             │ │  - SRT generation           │
└─────────────────────────────┘ └─────────────────────────────┘ └─────────────────────────────┘
                                    │               │               │
                    ┌───────────────┼───────────────┼───────────────┘
                    │               │               │
                    ▼               ▼               ▼
┌─────────────────────────────┐ ┌─────────────────────────────┐ ┌─────────────────────────────┐
│  ADAPTATION LAYER           │ │  ADAPTATION LAYER           │ │  ADAPTATION LAYER           │
│  (provider implementations) │ │  (provider implementations) │ │  (provider implementations) │
│                             │ │                             │ │                             │
│  ASR Providers:             │ │  LLM Providers:             │ │  External World:            │
│  - GroqASR                  │ │  - DeepSeekLLM              │ │  - ffmpeg subprocess        │
│  - AssemblyAIASR            │ │  - GroqLLM                  │ │  - Groq API                 │
│  - OpenAIASR                │ │  - OpenAILLM                │ │  - AssemblyAI API           │
│                             │ │                             │ │  - OpenAI API               │
│                             │ │                             │ │  - DeepSeek API             │
└─────────────────────────────┘ └─────────────────────────────┘ └─────────────────────────────┘
```

### Stage-by-Stage Data Flow

#### Stage 1: Audio Extraction

```
Input:  video_path: str
Output: audio_path: str (16kHz mono WAV)
Artifact: .checkpoint/audio/audio.wav

Data Flow:
  video.mp4 → ffmpeg -i video.mp4 -ar 16000 -ac 1 audio.wav → .checkpoint/audio/audio.wav
```

#### Stage 2: Transcription

```
Input:  audio_path: str, chunking_strategy: ChunkingStrategy
Output: TranscriptResult (text, confidence, words, duration_s)
Artifact: .checkpoint/asr/raw_transcript.json

Data Flow:
  audio.wav → Transcriber → [FullAudioStrategy OR TimedChunkingStrategy] → TranscriptResult
  → .checkpoint/asr/raw_transcript.json
```

#### Stage 3: Segmentation

```
Input:  transcript: str, video_context: VideoContext
Output: List[Chapter] with title, start_time, end_time, confidence
Artifact: .checkpoint/segmentation/chapters.json

Data Flow:
  transcript + video_context → Segmenter (LLM) → chapters.json
```

#### Stage 4: Enrichment

```
Input:  chapters: List[Chapter], transcript: str, video_context: VideoContext
Output: List[EnrichedChapter] with description, context, highlights, pedagogy
Artifact: .checkpoint/enrichment/enriched_chapters.json

Data Flow:
  chapters + transcript + video_context → Enricher (LLM) → enriched_chapters.json
```

#### Stage 5: Materialization

```
Input:  enriched_chapters: List[EnrichedChapter], video_path: str, output_dir: str
Output: List[ChapterFolder] with metadata.json, .srt, .mp4
Artifact: output/chapters/{chapter_slug}/

Data Flow:
  enriched_chapters → Materializer → output/chapters/introduccion/
    ├── metadata.json
    ├── introduccion.srt
    └── introduccion.mp4 (fast cut)
```

---

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Create | uv project definition with dependencies (groq, assemblyai, openai, pydantic, pyyaml, rich, python-dotenv, pytest, backoff, python-multipart) |
| `src/__init__.py` | Create | Package root |
| `src/main.py` | Create | CLI entry point, config loading, pipeline invocation, TUI setup |
| `src/config.py` | Create | Config model (Pydantic), YAML + .env loader, validation |
| `src/pipeline.py` | Create | Pipeline orchestrator with checkpoint management, budget enforcement, stage coordination |
| `src/providers/__init__.py` | Create | Provider package root |
| `src/providers/factory.py` | Create | Factory functions for ASR and LLM provider instantiation |
| `src/providers/asr/__init__.py` | Create | ASR provider package root |
| `src/providers/asr/base.py` | Create | Abstract `ASRProvider` interface with `transcribe()` method |
| `src/providers/asr/groq_asr.py` | Create | Groq Whisper implementation |
| `src/providers/asr/assemblyai_asr.py` | Create | AssemblyAI implementation (basic transcription only) |
| `src/providers/asr/openai_asr.py` | Create | OpenAI Whisper implementation |
| `src/providers/llm/__init__.py` | Create | LLM provider package root |
| `src/providers/llm/base.py` | Create | Abstract `LLMProvider` interface with `generate()` method |
| `src/providers/llm/deepseek_llm.py` | Create | DeepSeek implementation |
| `src/providers/llm/groq_llm.py` | Create | Groq LLM implementation |
| `src/providers/llm/openai_llm.py` | Create | OpenAI LLM implementation |
| `src/processors/__init__.py` | Create | Processor package root |
| `src/processors/audio_extractor.py` | Create | ffmpeg subprocess wrapper with progress reporting |
| `src/processors/chunking.py` | Create | Chunking strategies (FullAudioStrategy, TimedChunkingStrategy) and reassembly logic |
| `src/processors/transcriber.py` | Create | ASR invocation with adaptive chunking orchestration |
| `src/processors/segmenter.py` | Create | LLM-based chapter segmentation with prompt injection |
| `src/processors/enricher.py` | Create | LLM-based chapter enrichment (loads `prompts/enricher.md`) |
| `src/processors/materializer.py` | Create | Chapter folder creation, ffmpeg cut, .srt generation |
| `src/utils/__init__.py` | Create | Utils package root |
| `src/utils/checkpoint.py` | Create | Filesystem checkpoint read/write utilities |
| `src/utils/logger.py` | Create | Structured logging configuration |
| `src/utils/retry.py` | Create | Retry with exponential backoff + fallback orchestration |
| `src/utils/progress.py` | Create | TUI progress event system with Rich integration |
| `src/utils/cost_estimator.py` | Create | Cost calculator for ASR and LLM providers |
| `src/utils/validators.py` | Create | Input validation utilities |
| `tests/__init__.py` | Create | Test package root |
| `tests/conftest.py` | Create | Pytest fixtures (mock providers, test videos, golden files) |
| `tests/unit/providers/asr/` | Create | Unit tests for ASR providers |
| `tests/unit/providers/llm/` | Create | Unit tests for LLM providers |
| `tests/unit/processors/` | Create | Unit tests for processors |
| `tests/unit/utils/` | Create | Unit tests for utilities |
| `tests/integration/` | Create | Integration tests for full pipeline |
| `tests/fixtures/` | Create | Test fixtures (sample audio, mock API responses) |
| `prompts/enricher.md` | Modify | Update prompt template with variable injection placeholders |
| `.gitignore` | Modify | Add `.checkpoint/`, `.env`, `output/` patterns |

---

## Interfaces / Contracts

### Pydantic Data Models

```python
# src/config.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from pathlib import Path

class Config(BaseModel):
    # Provider configuration
    asr_provider: str = Field(..., pattern="^(groq|assemblyai|openai)$")
    asr_model: Optional[str] = None
    llm_provider: str = Field(..., pattern="^(deepseek|groq|openai)$")
    llm_model: Optional[str] = None
    
    # Input/Output
    input_video: Path
    output_dir: Path = Path("./output")
    language: str = "es"
    
    # Processing
    cut_mode: str = Field(default="fast", pattern="^(fast|precise)$")
    max_budget_usd: float = Field(default=2.0, gt=0)
    chunk_duration_minutes: int = Field(default=20, gt=0)
    chunk_overlap_seconds: int = Field(default=30, ge=0, lt=60)
    
    # Confidence thresholds
    segmentation_confidence_threshold: float = Field(default=0.7, ge=0, le=1)
    transcription_confidence_threshold: float = Field(default=0.6, ge=0, le=1)
    
    # Output generation
    generate_subtitles: bool = True
    generate_summaries: bool = True
    generate_highlights: bool = True
    generate_index: bool = False  # Phase 2

    @field_validator("input_video")
    @classmethod
    def validate_input_exists(cls, v):
        if not v.exists():
            raise ValueError(f"Input video not found: {v}")
        return v
```

```python
# src/providers/asr/base.py
from abc import ABC, abstractmethod
from typing import List
from pydantic import BaseModel

class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float
    confidence: float

class TranscriptResult(BaseModel):
    text: str
    confidence: float
    words: List[WordTimestamp]
    duration_s: float
    provider: str
    model: str

class ASRProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_path: str) -> TranscriptResult:
        """Transcribe audio file and return structured result."""
        pass
    
    @abstractmethod
    async def supports_file(self, audio_path: str) -> bool:
        """Check if provider can process file (size/duration limits)."""
        pass
```

```python
# src/providers/llm/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any

class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        schema: Dict[str, Any],
        temperature: float = 0.2
    ) -> Dict[str, Any]:
        """Generate structured output matching schema."""
        pass
```

```python
# src/processors/chunking.py
from abc import ABC, abstractmethod
from typing import List, Tuple
from pathlib import Path

class ChunkingStrategy(ABC):
    @abstractmethod
    def create_chunks(self, audio_path: Path, duration_s: float) -> List[Tuple[Path, float, float]]:
        """Create chunk files and return list of (chunk_path, start_s, end_s)."""
        pass
    
    @abstractmethod
    def reassemble(self, chunk_results: List[TranscriptResult]) -> TranscriptResult:
        """Merge chunk transcripts with overlap resolution."""
        pass

class FullAudioStrategy(ChunkingStrategy):
    def create_chunks(self, audio_path: Path, duration_s: float) -> List[Tuple[Path, float, float]]:
        # Return single chunk: entire file
        return [(audio_path, 0, duration_s)]
    
    def reassemble(self, chunk_results: List[TranscriptResult]) -> TranscriptResult:
        # Return first (and only) result
        return chunk_results[0]

class TimedChunkingStrategy(ChunkingStrategy):
    def __init__(self, chunk_duration_minutes: int = 20, overlap_seconds: int = 30):
        self.chunk_duration_minutes = chunk_duration_minutes
        self.overlap_seconds = overlap_seconds
    
    def create_chunks(self, audio_path: Path, duration_s: float) -> List[Tuple[Path, float, float]]:
        # Split audio into chunks with overlap
        # Returns list of (chunk_path, start_s, end_s)
        pass
    
    def reassemble(self, chunk_results: List[TranscriptResult]) -> TranscriptResult:
        # Merge with overlap resolution using confidence scores
        pass
```

```python
# src/processors/chunking.py (continued)
class Chapter(BaseModel):
    number: int
    title: str
    start_time: str  # HH:MM:SS.mmm
    end_time: str    # HH:MM:SS.mmm
    start_seconds: float
    end_seconds: float
    confidence: float
    transcript: str

class EnrichedChapter(BaseModel):
    chapter: Chapter
    description: str
    context: str
    summary_bullets: List[str]
    terms_used: List[Dict[str, Any]]
    key_concepts: List[str]
    entities_detected: Dict[str, List[str]]
    highlights: List[Highlight]
    pedagogy: Dict[str, Any]
    confidence: Dict[str, float]

class Highlight(BaseModel):
    timestamp: str  # Absolute timestamp in video
    type: str  # insight, example, warning, takeaway, hook, controversial, definition, demo
    label: str
    quote: str
    importance: str  # alta, media, baja
```

```python
# src/utils/checkpoint.py
from pathlib import Path
import json
from typing import Any

class CheckpointManager:
    def __init__(self, output_dir: Path):
        self.checkpoint_dir = output_dir / ".checkpoint"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    
    def save(self, stage: str, data: Any, filename: str = "data.json"):
        """Save checkpoint data."""
        stage_dir = self.checkpoint_dir / stage
        stage_dir.mkdir(exist_ok=True)
        filepath = stage_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            if isinstance(data, BaseModel):
                json.dump(data.model_dump(), f, indent=2)
            else:
                json.dump(data, f, indent=2)
        return filepath
    
    def load(self, stage: str, filename: str = "data.json") -> Optional[Any]:
        """Load checkpoint data."""
        filepath = self.checkpoint_dir / stage / filename
        if not filepath.exists():
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def exists(self, stage: str) -> bool:
        """Check if checkpoint exists for stage."""
        return (self.checkpoint_dir / stage).exists()
    
    def clear(self):
        """Delete all checkpoints."""
        import shutil
        shutil.rmtree(self.checkpoint_dir)
```

### JSON Schemas

```json
// .checkpoint/asr/raw_transcript.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["text", "confidence", "words", "duration_s", "provider", "model"],
  "properties": {
    "text": { "type": "string" },
    "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
    "words": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["word", "start", "end", "confidence"],
        "properties": {
          "word": { "type": "string" },
          "start": { "type": "number" },
          "end": { "type": "number" },
          "confidence": { "type": "number", "minimum": 0, "maximum": 1 }
        }
      }
    },
    "duration_s": { "type": "number" },
    "provider": { "type": "string" },
    "model": { "type": "string" }
  }
}
```

```json
// .checkpoint/segmentation/chapters.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["number", "title", "start_time", "end_time", "start_seconds", "end_seconds", "confidence", "transcript"],
    "properties": {
      "number": { "type": "integer" },
      "title": { "type": "string" },
      "start_time": { "type": "string", "pattern": "^\\d{2}:\\d{2}:\\d{2}\\.\\d{3}$" },
      "end_time": { "type": "string", "pattern": "^\\d{2}:\\d{2}:\\d{2}\\.\\d{3}$" },
      "start_seconds": { "type": "number" },
      "end_seconds": { "type": "number" },
      "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
      "transcript": { "type": "string" }
    }
  }
}
```

```json
// output/chapters/{slug}/metadata.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["chapter", "content", "knowledge", "highlights", "pedagogy", "confidence", "source"],
  "properties": {
    "chapter": {
      "type": "object",
      "required": ["number", "title", "title_seo", "slug"],
      "properties": {
        "number": { "type": "integer" },
        "title": { "type": "string" },
        "title_seo": { "type": "string" },
        "slug": { "type": "string" }
      }
    },
    "timing": {
      "type": "object",
      "required": ["start_time", "end_time", "duration_seconds", "word_count"],
      "properties": {
        "start_time": { "type": "string" },
        "end_time": { "type": "string" },
        "duration_seconds": { "type": "integer" },
        "word_count": { "type": "integer" }
      }
    },
    "content": {
      "type": "object",
      "required": ["description", "context", "summary_bullets"],
      "properties": {
        "description": { "type": "string" },
        "context": { "type": "string" },
        "summary_bullets": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    },
    "knowledge": {
      "type": "object",
      "required": ["terms_used", "key_concepts", "entities_detected"],
      "properties": {
        "terms_used": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["term", "type", "frequency"],
            "properties": {
              "term": { "type": "string" },
              "type": { "type": "string" },
              "frequency": { "type": "integer" },
              "definition": { "type": "string" }
            }
          }
        },
        "key_concepts": {
          "type": "array",
          "items": { "type": "string" }
        },
        "entities_detected": {
          "type": "object",
          "properties": {
            "personas": { "type": "array", "items": { "type": "string" } },
            "organizaciones": { "type": "array", "items": { "type": "string" } },
            "tecnologías": { "type": "array", "items": { "type": "string" } },
            "lenguajes": { "type": "array", "items": { "type": "string" } }
          }
        }
      }
    },
    "highlights": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["timestamp", "type", "label", "quote"],
        "properties": {
          "timestamp": { "type": "string" },
          "type": { "type": "string" },
          "label": { "type": "string" },
          "quote": { "type": "string" },
          "importance": { "type": "string" }
        }
      }
    },
    "pedagogy": {
      "type": "object",
      "required": ["difficulty_level", "prerequisites", "learning_objectives", "teaching_methods"],
      "properties": {
        "difficulty_level": { "type": "string" },
        "prerequisites": { "type": "array", "items": { "type": "string" } },
        "learning_objectives": {
          "type": "array",
          "items": { "type": "string" }
        },
        "teaching_methods": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    },
    "confidence": {
      "type": "object",
      "required": ["segmentation_score", "transcription_quality", "content_coherence", "needs_review"],
      "properties": {
        "segmentation_score": { "type": "number", "minimum": 0, "maximum": 1 },
        "transcription_quality": { "type": "number", "minimum": 0, "maximum": 1 },
        "content_coherence": { "type": "number", "minimum": 0, "maximum": 1 },
        "needs_review": { "type": "boolean" },
        "review_reasons": { "type": "array", "items": { "type": "string" } }
      }
    },
    "source": {
      "type": "object",
      "required": ["video", "asr_provider", "llm_provider", "processing_date", "cost_usd"],
      "properties": {
        "video": { "type": "string" },
        "asr_provider": { "type": "string" },
        "llm_provider": { "type": "string" },
        "processing_date": { "type": "string", "format": "date-time" },
        "cost_usd": { "type": "number" }
      }
    }
  }
}
```

---

## Implementation Guidelines

### Provider Implementation Pattern

All providers follow this pattern:

```python
# src/providers/asr/groq_asr.py
from typing import Optional
from pathlib import Path
from groq import Groq
from src.providers.asr.base import ASRProvider, TranscriptResult, WordTimestamp

class GroqASR(ASRProvider):
    def __init__(self, api_key: str, model: str = "whisper-large-v3-turbo"):
        self.client = Groq(api_key=api_key)
        self.model = model
        self.max_duration_minutes = 25  # Groq Whisper limit
    
    async def supports_file(self, audio_path: str) -> bool:
        """Check if file is within duration limits."""
        duration_s = self._get_audio_duration(audio_path)
        return duration_s <= self.max_duration_minutes * 60
    
    async def transcribe(self, audio_path: str) -> TranscriptResult:
        """Transcribe audio using Groq Whisper API."""
        try:
            with open(audio_path, "rb") as file:
                transcription = self.client.audio.transcriptions.create(
                    file=(Path(audio_path).name, file),
                    model=self.model,
                    response_format="verbose_json"
                )
            
            # Convert to domain model
            words = [
                WordTimestamp(
                    word=w.word,
                    start=w.start,
                    end=w.end,
                    confidence=w.confidence or 1.0
                )
                for w in transcription.words
            ]
            
            return TranscriptResult(
                text=transcription.text,
                confidence=transcription.duration > 0,
                words=words,
                duration_s=transcription.duration,
                provider="groq",
                model=self.model
            )
        
        except Exception as e:
            raise ProviderError(f"Groq transcription failed: {e}", status_code=None)
    
    def _get_audio_duration(self, audio_path: str) -> float:
        """Get audio duration using ffprobe."""
        # Implementation using subprocess + ffprobe
        pass
```

### Factory Pattern

```python
# src/providers/factory.py
import os
from typing import Optional
from src.providers.asr.base import ASRProvider
from src.providers.llm.base import LLMProvider
from src.providers.asr.groq_asr import GroqASR
from src.providers.asr.assemblyai_asr import AssemblyAIASR
from src.providers.asr.openai_asr import OpenAIASR
from src.providers.llm.deepseek_llm import DeepSeekLLM
from src.providers.llm.groq_llm import GroqLLM
from src.providers.llm.openai_llm import OpenAILLM

def create_asr_provider(provider_name: str, model: Optional[str] = None) -> ASRProvider:
    """Create ASR provider based on config."""
    api_key = _get_api_key(provider_name)
    
    if provider_name == "groq":
        return GroqASR(api_key=api_key, model=model or "whisper-large-v3-turbo")
    elif provider_name == "assemblyai":
        return AssemblyAIASR(api_key=api_key)
    elif provider_name == "openai":
        return OpenAIASR(api_key=api_key, model=model or "whisper-1")
    else:
        raise ValueError(f"Unknown ASR provider: {provider_name}")

def create_llm_provider(provider_name: str, model: Optional[str] = None) -> LLMProvider:
    """Create LLM provider based on config."""
    api_key = _get_api_key(provider_name)
    
    if provider_name == "deepseek":
        return DeepSeekLLM(api_key=api_key, model=model or "deepseek-chat")
    elif provider_name == "groq":
        return GroqLLM(api_key=api_key, model=model or "llama-3-70b-8192")
    elif provider_name == "openai":
        return OpenAILLM(api_key=api_key, model=model or "gpt-4o-mini")
    else:
        raise ValueError(f"Unknown LLM provider: {provider_name}")

def _get_api_key(provider_name: str) -> str:
    """Get API key from environment."""
    keys = {
        "groq": "GROQ_API_KEY",
        "assemblyai": "ASSEMBLYAI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
    }
    key_name = keys.get(provider_name)
    if not key_name:
        raise ValueError(f"No API key mapping for provider: {provider_name}")
    
    api_key = os.environ.get(key_name)
    if not api_key:
        raise ValueError(f"Missing API key: {key_name}")
    
    return api_key
```

### Pipeline Orchestrator

```python
# src/pipeline.py
import asyncio
from pathlib import Path
from typing import List

from src.config import Config
from src.providers.factory import create_asr_provider, create_llm_provider
from src.utils.checkpoint import CheckpointManager
from src.utils.progress import TUIRenderer, ProgressEvent
from src.utils.cost_estimator import CostEstimator
from src.utils.logger import get_logger

logger = get_logger(__name__)

class Pipeline:
    def __init__(self, config: Config):
        self.config = config
        self.checkpoint_manager = CheckpointManager(config.output_dir)
        self.cost_estimator = CostEstimator()
        self.tui = TUIRenderer()
        
        # Create providers
        self.asr_provider = create_asr_provider(config.asr_provider, config.asr_model)
        self.llm_provider = create_llm_provider(config.llm_provider, config.llm_model)
    
    async def run(self, video_path: Path) -> List[dict]:
        """Execute the full pipeline."""
        logger.info(f"Starting pipeline for {video_path}")
        
        try:
            # Stage 1: Audio extraction
            audio_path = await self._stage_extract_audio(video_path)
            
            # Stage 2: Transcription
            transcript = await self._stage_transcribe(audio_path)
            
            # Stage 3: Segmentation
            chapters = await self._stage_segment(transcript)
            
            # Stage 4: Enrichment
            enriched_chapters = await self._stage_enrich(chapters, transcript)
            
            # Stage 5: Materialization
            chapter_folders = await self._stage_materialize(enriched_chapters, video_path)
            
            # Clean checkpoints on success
            self.checkpoint_manager.clear()
            
            return chapter_folders
        
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            raise
    
    async def _stage_extract_audio(self, video_path: Path) -> Path:
        """Stage 1: Extract audio from video."""
        if self.checkpoint_manager.exists("audio"):
            logger.info("Resuming from audio checkpoint")
            audio_path = self.checkpoint_manager.load("audio", "audio.wav")
            return Path(audio_path)
        
        self.tui.update(ProgressEvent(stage="extracting_audio", percentage=0))
        
        # Implementation using AudioExtractor
        # ...
        
        self.tui.update(ProgressEvent(stage="extracting_audio", percentage=100))
        return audio_path
    
    async def _stage_transcribe(self, audio_path: Path) -> dict:
        """Stage 2: Transcribe audio."""
        if self.checkpoint_manager.exists("asr"):
            logger.info("Resuming from ASR checkpoint")
            return self.checkpoint_manager.load("asr", "raw_transcript.json")
        
        self.tui.update(ProgressEvent(stage="transcribing", percentage=0))
        
        # Implementation using Transcriber with adaptive chunking
        # ...
        
        self.tui.update(ProgressEvent(stage="transcribing", percentage=100))
        return transcript
    
    # ... other stages
```

### TUI Progress System

```python
# src/utils/progress.py
from typing import Optional
from dataclasses import dataclass
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.table import Table
from rich.console import Console

@dataclass
class ProgressEvent:
    stage: str
    percentage: float
    cost_usd: Optional[float] = None
    budget_usd: Optional[float] = None
    message: Optional[str] = None
    eta_seconds: Optional[int] = None

class TUIRenderer:
    def __init__(self):
        self.console = Console()
        self.live = Live(self._build_layout(), console=self.console, refresh_per_second=10)
        self.current_stage = ""
        self.cost_usd = 0.0
        self.budget_usd = 0.0
    
    def __enter__(self):
        self.live.start()
        return self
    
    def __exit__(self, *args):
        self.live.stop()
    
    def update(self, event: ProgressEvent):
        """Update TUI with progress event."""
        self.current_stage = event.stage
        self.cost_usd = event.cost_usd or self.cost_usd
        self.budget_usd = event.budget_usd or self.budget_usd
        self.layout = self._build_layout(event)
        self.live.update(self.layout)
    
    def _build_layout(self, event: Optional[ProgressEvent] = None) -> Panel:
        """Build the TUI layout."""
        table = Table(show_header=False, box=None)
        table.add_column("Stage", style="cyan")
        table.add_column("Progress", style="green")
        
        stage = event.stage if event else self.current_stage
        percentage = event.percentage if event else 0
        cost = f"${self.cost_usd:.2f}" if self.cost_usd else "N/A"
        budget = f"${self.budget_usd:.2f}" if self.budget_usd else "N/A"
        
        table.add_row("Current Stage", stage)
        table.add_row("Progress", f"[{'█' * int(percentage/5)}{'░' * (20 - int(percentage/5))}] {percentage:.0f}%")
        table.add_row("Cost", f"{cost} / {budget}")
        
        return Panel(table, title="Echo-Bering Pipeline", border_style="green")
```

### Error Handling and Retry

```python
# src/utils/retry.py
import asyncio
import backoff
from typing import Callable, Type, Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)

class ProviderError(Exception):
    """Base exception for provider errors."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class TransientProviderError(ProviderError):
    """Transient error that may succeed on retry."""
    pass

class PermanentProviderError(ProviderError):
    """Permanent error that should not be retried."""
    pass

class RetryPolicy:
    """Retry policy with exponential backoff and fallback."""
    
    def __init__(
        self,
        max_retries: int = 2,
        base_delay: float = 1.0,
        max_delay: float = 10.0,
        fallback_providers: Optional[list] = None
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.fallback_providers = fallback_providers or []
    
    def retry(self, func: Callable):
        """Decorator to add retry logic with fallback."""
        
        @backoff.on_exception(
            backoff.expo,
            TransientProviderError,
            max_tries=self.max_retries + 1,
            max_value=self.max_delay,
            on_backoff=self._on_backoff
        )
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except PermanentProviderError:
                raise
            except ProviderError as e:
                raise TransientProviderError(e.message, e.status_code)
        
        return wrapper
    
    def _on_backoff(self, details):
        """Callback on retry attempt."""
        logger.warning(
            f"Retry {details['tries']}/{self.max_retries + 1} for {details['target'].__name__}"
            f" after {details['wait']:.2f}s"
        )
```

---

## Testing Strategy

### Unit Test Structure

```
tests/
├── conftest.py                    # Pytest fixtures
├── unit/
│   ├── providers/
│   │   ├── asr/
│   │   │   ├── test_groq_asr.py
│   │   │   ├── test_assemblyai_asr.py
│   │   │   └── test_openai_asr.py
│   │   └── llm/
│   │       ├── test_deepseek_llm.py
│   │       ├── test_groq_llm.py
│   │       └── test_openai_llm.py
│   ├── processors/
│   │   ├── test_audio_extractor.py
│   │   ├── test_chunking.py
│   │   ├── test_transcriber.py
│   │   ├── test_segmenter.py
│   │   ├── test_enricher.py
│   │   └── test_materializer.py
│   └── utils/
│       ├── test_checkpoint.py
│       ├── test_retry.py
│       ├── test_cost_estimator.py
│       └── test_progress.py
└── integration/
    └── test_pipeline.py
```

### Mocking Strategy

```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
from src.providers.asr.base import TranscriptResult, WordTimestamp

@pytest.fixture
def mock_asr_provider():
    """Mock ASR provider for unit tests."""
    provider = MagicMock()
    provider.transcribe = AsyncMock(
        return_value=TranscriptResult(
            text="Sample transcription",
            confidence=0.95,
            words=[
                WordTimestamp(word="Sample", start=0.0, end=0.5, confidence=0.95),
                WordTimestamp(word="transcription", start=0.5, end=1.0, confidence=0.95)
            ],
            duration_s=1.0,
            provider="mock",
            model="mock-model"
        )
    )
    provider.supports_file = AsyncMock(return_value=True)
    return provider

@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider for unit tests."""
    provider = MagicMock()
    provider.generate = AsyncMock(
        return_value={
            "chapters": [
                {
                    "number": 1,
                    "title": "Introduction",
                    "start_time": "00:00:00.000",
                    "end_time": "00:00:30.000",
                    "start_seconds": 0.0,
                    "end_seconds": 30.0,
                    "confidence": 0.92,
                    "transcript": "Sample transcript"
                }
            ]
        }
    )
    return provider

@pytest.fixture
def test_audio_path(tmp_path):
    """Create a test audio file."""
    audio_path = tmp_path / "test.wav"
    # Create minimal WAV file
    audio_path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00\x00}\x00\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
    return audio_path

@pytest.fixture
def golden_transcript():
    """Golden file for transcript validation."""
    return {
        "text": "Sample transcription",
        "confidence": 0.95,
        "words": [
            {"word": "Sample", "start": 0.0, "end": 0.5, "confidence": 0.95},
            {"word": "transcription", "start": 0.5, "end": 1.0, "confidence": 0.95}
        ],
        "duration_s": 1.0,
        "provider": "mock",
        "model": "mock-model"
    }
```

### Unit Test Examples

```python
# tests/unit/processors/test_transcriber.py
import pytest
from pathlib import Path
from src.processors.transcriber import Transcriber
from src.processors.chunking import FullAudioStrategy, TimedChunkingStrategy

@pytest.mark.asyncio
async def test_transcriber_full_audio_success(mock_asr_provider, test_audio_path):
    """Transcriber succeeds with full audio when provider supports it."""
    transcriber = Transcriber(
        asr_provider=mock_asr_provider,
        chunking_strategy=FullAudioStrategy()
    )
    
    result = await transcriber.transcribe(test_audio_path)
    
    assert result.text == "Sample transcription"
    assert result.confidence == 0.95
    assert len(result.words) == 2
    mock_asr_provider.transcribe.assert_called_once_with(str(test_audio_path))

@pytest.mark.asyncio
async def test_transcriber_fallback_to_chunking(mock_asr_provider, test_audio_path):
    """Transcriber falls back to chunking when provider rejects file."""
    # Mock provider to reject file initially
    mock_asr_provider.supports_file = AsyncMock(return_value=False)
    
    transcriber = Transcriber(
        asr_provider=mock_asr_provider,
        chunking_strategy=TimedChunkingStrategy(chunk_duration_minutes=5)
    )
    
    result = await transcriber.transcribe(test_audio_path)
    
    # Verify chunking was triggered
    assert result is not None

@pytest.mark.asyncio
async def test_transcriber_partial_failure(mock_asr_provider, test_audio_path):
    """Transcriber handles partial chunk failure."""
    # Mock provider to fail on one chunk
    call_count = 0
    async def mock_transcribe(audio_path):
        nonlocal call_count
        call_count += 1
        if call_count == 2:  # Second chunk fails
            raise TransientProviderError("Chunk 2 failed", status_code=500)
        return TranscriptResult(
            text=f"Chunk {call_count} transcription",
            confidence=0.95,
            words=[],
            duration_s=300.0,
            provider="mock",
            model="mock-model"
        )
    
    mock_asr_provider.transcribe = mock_transcribe
    mock_asr_provider.supports_file = AsyncMock(return_value=False)
    
    transcriber = Transcriber(
        asr_provider=mock_asr_provider,
        chunking_strategy=TimedChunkingStrategy(chunk_duration_minutes=5)
    )
    
    result = await transcriber.transcribe(test_audio_path)
    
    # Verify partial failure handling
    assert "[TRANSCRIPTION_FAILED]" in result.text
```

### Integration Test Example

```python
# tests/integration/test_pipeline.py
import pytest
from pathlib import Path
from src.config import Config
from src.pipeline import Pipeline

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline_e2e(tmp_path):
    """End-to-end pipeline test with mock providers."""
    # Setup test video
    test_video = tmp_path / "test.mp4"
    test_video.write_bytes(b"fake video data")
    
    # Setup config
    config = Config(
        input_video=test_video,
        output_dir=tmp_path / "output",
        asr_provider="groq",
        llm_provider="deepseek",
        max_budget_usd=10.0
    )
    
    # Setup pipeline with mock providers
    pipeline = Pipeline(config)
    
    # Mock provider calls
    # ...
    
    # Run pipeline
    chapters = await pipeline.run(test_video)
    
    # Verify output structure
    assert len(chapters) >= 1
    for chapter in chapters:
        chapter_dir = config.output_dir / "chapters" / chapter["slug"]
        assert (chapter_dir / "metadata.json").exists()
        assert (chapter_dir / f"{chapter['slug']}.srt").exists()
        assert (chapter_dir / f"{chapter['slug']}.mp4").exists()
```

### TUI Snapshot Testing

```python
# tests/unit/utils/test_progress.py
def test_tui_renderer_update(mock_live):
    """Test TUI renderer updates layout correctly."""
    renderer = TUIRenderer()
    event = ProgressEvent(
        stage="transcribing",
        percentage=60,
        cost_usd=1.23,
        budget_usd=10.0
    )
    
    renderer.update(event)
    
    # Verify layout contains expected elements
    assert "transcribing" in renderer.layout.renderable
    assert "60%" in renderer.layout.renderable
    assert "$1.23" in renderer.layout.renderable
```

---

## Error Handling and Resilience

### Exception Hierarchy

```python
# src/utils/errors.py
class EchoBeringError(Exception):
    """Base exception for all Echo-Bering errors."""
    pass

class ConfigError(EchoBeringError):
    """Configuration validation error."""
    def __init__(self, message: str, missing_keys: list = None):
        self.missing_keys = missing_keys or []
        super().__init__(message)

class DependencyError(EchoBeringError):
    """Missing system dependency (e.g., ffmpeg)."""
    def __init__(self, dependency: str, instructions: str):
        self.dependency = dependency
        self.instructions = instructions
        super().__init__(f"Dependency '{dependency}' not found: {instructions}")

class ProviderError(EchoBeringError):
    """Provider API error."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class TransientProviderError(ProviderError):
    """Transient error that may succeed on retry."""
    pass

class PermanentProviderError(ProviderError):
    """Permanent error that should not be retried."""
    pass

class BudgetError(EchoBeringError):
    """Budget exceeded error."""
    def __init__(self, current_cost: float, max_budget: float):
        self.current_cost = current_cost
        self.max_budget = max_budget
        super().__init__(f"Budget exceeded: ${current_cost:.2f} > ${max_budget:.2f}")

class CheckpointError(EchoBeringError):
    """Checkpoint read/write error."""
    pass
```

### Retry with Fallback

```python
# src/utils/retry.py (continued)
class ProviderOrchestrator:
    """Orchestrates provider calls with retry and fallback."""
    
    def __init__(self, primary_provider, fallback_providers: list = None):
        self.primary = primary_provider
        self.fallbacks = fallback_providers or []
        self.retry_policy = RetryPolicy()
    
    async def transcribe(self, audio_path: str) -> TranscriptResult:
        """Transcribe with fallback to next provider on failure."""
        providers = [self.primary] + self.fallbacks
        
        for i, provider in enumerate(providers):
            try:
                return await self.retry_policy.retry(provider.transcribe)(audio_path)
            except PermanentProviderError as e:
                raise
            except TransientProviderError as e:
                logger.warning(f"Provider {i} ({provider.__class__.__name__}) failed: {e.message}")
                if i < len(providers) - 1:
                    logger.info(f"Falling back to next provider...")
                else:
                    raise
        
        raise ProviderError("All providers failed")
```

### Budget Enforcement

```python
# src/utils/cost_estimator.py
class CostEstimator:
    """Estimates and tracks API costs."""
    
    # Groq Whisper: $0.0001/s (https://console.groq.com/pricing)
    GROQ_WHISPER_PRICE_PER_SECOND = 0.0001
    
    # AssemblyAI: $0.0002/s (https://www.assemblyai.com/pricing)
    ASSEMBLYAI_PRICE_PER_SECOND = 0.0002
    
    # OpenAI Whisper: $0.00006/s (https://openai.com/api/pricing)
    OPENAI_WHISPER_PRICE_PER_SECOND = 0.00006
    
    # DeepSeek: $0.00014/s (estimated)
    DEEPSEEK_PRICE_PER_SECOND = 0.00014
    
    # Groq LLM: $0.00007/s (https://console.groq.com/pricing)
    GROQ_LLM_PRICE_PER_SECOND = 0.00007
    
    def __init__(self):
        self.total_cost = 0.0
        self.cost_history = []
    
    def estimate_asr_cost(self, provider: str, duration_s: float) -> float:
        """Estimate ASR cost for audio duration."""
        prices = {
            "groq": self.GROQ_WHISPER_PRICE_PER_SECOND,
            "assemblyai": self.ASSEMBLYAI_PRICE_PER_SECOND,
            "openai": self.OPENAI_WHISPER_PRICE_PER_SECOND,
        }
        return prices.get(provider, 0) * duration_s
    
    def estimate_llm_cost(self, provider: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate LLM cost for token count."""
        # Simplified: assume 1 token ≈ 4 characters, ~3 tokens/second
        duration_s = (prompt_tokens + completion_tokens) / 3
        prices = {
            "deepseek": self.DEEPSEEK_PRICE_PER_SECOND,
            "groq": self.GROQ_LLM_PRICE_PER_SECOND,
            "openai": self.GROQ_LLM_PRICE_PER_SECOND * 2,  # GPT-4o-mini is ~2x Groq
        }
        return prices.get(provider, 0) * duration_s
    
    def add_cost(self, cost: float, description: str):
        """Record a cost."""
        self.total_cost += cost
        self.cost_history.append({
            "cost": cost,
            "description": description,
            "timestamp": datetime.now().isoformat()
        })
    
    def check_budget(self, max_budget: float) -> bool:
        """Check if budget is exceeded."""
        return self.total_cost <= max_budget
```

### Partial Failure Handling

```python
# src/processors/transcriber.py (continued)
class Transcriber:
    async def transcribe(self, audio_path: str) -> TranscriptResult:
        """Transcribe with adaptive chunking and partial failure handling."""
        strategy = self._select_strategy(audio_path)
        chunks = strategy.create_chunks(Path(audio_path), self._get_duration(audio_path))
        
        results = []
        for i, (chunk_path, start_s, end_s) in enumerate(chunks):
            try:
                result = await self.provider.transcribe(str(chunk_path))
                results.append((result, start_s, end_s))
            except Exception as e:
                logger.error(f"Chunk {i} failed: {e}")
                # Record failure but continue with other chunks
                results.append((None, start_s, end_s))
        
        # Reassemble with overlap resolution
        return strategy.reassemble(results)
```

---

## Logging Strategy

```python
# src/utils/logger.py
import logging
from pathlib import Path
from datetime import datetime

def get_logger(name: str) -> logging.Logger:
    """Get configured logger."""
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        
        # Console handler (INFO+)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter("%(levelname)s: %(message)s")
        console_handler.setFormatter(console_format)
        logger.addHandler(console_handler)
        
        # File handler (DEBUG+)
        log_file = Path("output") / f"echo-bering-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    
    return logger
```

---

## Migration / Rollout

**No migration required.** This is a greenfield implementation with no existing data structures or schemas to migrate.

---

## Open Questions

- [ ] **Chunking overlap strategy**: Current design uses 30-second overlap with confidence-based selection. Should we consider semantic overlap detection (e.g., using sentence boundaries) for better coherence?

- [ ] **LLM JSON schema validation**: Should we implement strict JSON schema validation (e.g., using `jsonschema` library) for LLM responses, or rely on Pydantic model parsing with fallback?

- [ ] **Precise cut mode implementation**: The spec allows for `precise` cut mode with re-encoding. Should this be implemented in Phase 1, or deferred to Phase 2?

- [ ] **Cost estimator accuracy**: Current cost estimates are based on public pricing pages. Should we add a calibration mechanism to adjust estimates based on actual usage?

- [ ] **Provider feature detection**: Should we add automatic feature detection (e.g., "does this provider support word-level timestamps?") to enable/disable features dynamically?

- [ ] **TUI cost display format**: Should cost be displayed in real-time (after each provider call) or batched (after each pipeline stage)?

---

## Next Step

Ready for tasks (`sdd-tasks`). The design document provides:

- **Approach**: Four-layer architecture with provider-as-visitors pattern
- **Key Decisions**: Pydantic models, factory pattern, strategy pattern for chunking, event-based TUI
- **Files Affected**: 20 new files (package structure, providers, processors, utils, tests)
- **Testing Strategy**: Comprehensive pytest suite with mocking for providers and ffmpeg

### Delivery Strategy

**400-line budget risk**: **Medium** - The design includes 20+ new files with substantial implementation. The orchestrator and provider abstractions are well-factored, but each provider implementation (~150 lines each) and processor (~200 lines each) will add up.

**Recommendation**: Use `auto-chain` delivery strategy with the following slices:

1. **PR #1**: Core infrastructure (config, utils, checkpoint, logger) + 1 ASR provider + 1 LLM provider
2. **PR #2**: Processor implementations (transcriber, segmenter, enricher, materializer)
3. **PR #3**: Pipeline orchestrator + TUI integration + integration tests
4. **PR #4**: Additional ASR/LLM providers + documentation + cleanup

This keeps each PR under 150 lines of actual implementation while maintaining logical cohesion.
