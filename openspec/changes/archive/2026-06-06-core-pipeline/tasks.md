# Tasks: Echo-Bering Core Pipeline

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 3500–4200 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 → PR 4 |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Foundation: pyproject, config, errors, base utils | PR 1 (base: main) | Tests + fixtures included |
| 2 | Providers: abstractions + Groq ASR + DeepSeek LLM | PR 2 (base: PR 1) | Factory + 2 impls + tests |
| 3 | Processing: audio, chunking, transcriber | PR 3 (base: PR 2) | ffmpeg wrapper + adaptive chunking |
| 4 | Intelligence: segmenter + enricher | PR 4 (base: PR 3) | LLM prompt injection + JSON validation |
| 5 | Materialization + Orchestrator + TUI | PR 5 (base: PR 4) | Pipeline glue, SRT, ffmpeg cut |
| 6 | Remaining providers + integration tests | PR 6 (base: PR 5) | AssemblyAI, OpenAI, e2e pipeline |

## Phase 1: Project Foundation (Infrastructure)

- [x] 1.1 Create `pyproject.toml` with uv metadata, dependencies (groq, assemblyai, openai, pydantic>=2, pyyaml, rich, python-dotenv, backoff, pytest, pytest-asyncio, pytest-cov), and build config (~50 lines)
- [x] 1.2 Create `src/__init__.py`, `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py` (~10 lines)
- [x] 1.3 Create `src/utils/errors.py` with exception hierarchy: `EchoBeringError`, `ConfigError`, `DependencyError`, `ProviderError`, `TransientProviderError`, `PermanentProviderError`, `BudgetError`, `CheckpointError` (~60 lines)
- [x] 1.4 Create `tests/unit/utils/test_errors.py` — instantiate each exception, verify message and attributes, test inheritance chain (~80 lines)
- [x] 1.5 Create `src/utils/logger.py` with `get_logger()` returning configured logger (console INFO + file DEBUG to `output/echo-bering.log`) (~40 lines)
- [x] 1.6 Create `src/config.py` with `Config` Pydantic model (all fields from design), YAML + .env loader with `.env` override, validation for provider names, API keys, input file existence, output dir creation (~120 lines)
- [x] 1.7 Create `tests/unit/test_config.py` — valid config load, .env override YAML, missing key raises ConfigError, invalid provider rejected, missing API key raises ConfigError, nonexistent input raises ConfigError, output dir auto-created (~150 lines)
- [x] 1.8 Create `src/utils/checkpoint.py` with `CheckpointManager` class (save/load/exists/clear using JSON files in `.checkpoint/stage/`) (~80 lines)
- [x] 1.9 Create `tests/unit/utils/test_checkpoint.py` — save and load Pydantic model, save and load dict, exists returns false for missing, clear removes all, handles nested directories (~100 lines)
- [x] 1.10 Create `src/utils/retry.py` with `RetryPolicy` class: exponential backoff with jitter (1s base, 2x, max 10s), `TransientProviderError` vs `PermanentProviderError` handling, async decorator, on_backoff callback (~80 lines)
- [x] 1.11 Create `tests/unit/utils/test_retry.py` — transient error retries and succeeds, permanent error raises immediately, max retries exhausted raises, backoff callback fires (~100 lines)
- [x] 1.12 Create `src/utils/cost_estimator.py` with `CostEstimator`: per-provider price constants, `estimate_asr_cost(duration_s)`, `estimate_llm_cost(tokens)`, `add_cost()`, `check_budget(max_budget)` (~80 lines)
- [x] 1.13 Create `tests/unit/utils/test_cost_estimator.py` — ASR cost calculation per provider, LLM cost per token, budget check true/false, cumulative tracking (~80 lines)
- [x] 1.14 Create `tests/conftest.py` with shared fixtures: `mock_asr_provider` (AsyncMock returning `TranscriptResult`), `mock_llm_provider` (AsyncMock returning chapter dict), `test_audio_path` (minimal WAV in tmp_path), `golden_transcript` dict, `mock_ffmpeg` (subprocess mock), `tmp_output_dir` (~100 lines)

## Phase 2: Provider Abstractions

- [x] 2.1 Create `src/providers/__init__.py`, `src/providers/asr/__init__.py`, `src/providers/llm/__init__.py` (package roots, ~5 lines)
- [x] 2.2 Create `src/providers/asr/base.py` with `WordTimestamp`, `TranscriptResult` Pydantic models, abstract `ASRProvider` with `transcribe(audio_path) -> TranscriptResult` and `supports_file(audio_path) -> bool` methods (~60 lines)
- [x] 2.3 Create `src/providers/llm/base.py` with abstract `LLMProvider` with `generate(prompt, schema, temperature=0.2) -> dict` method (~30 lines)
- [x] 2.4 Create `src/providers/factory.py` with `create_asr_provider(name, model)`, `create_llm_provider(name, model)`, `_get_api_key(name)` — maps provider names to env var keys, raises ValueError on unknown (~80 lines)
- [x] 2.5 Create `tests/unit/providers/test_factory.py` — valid ASR provider creation (groq/assemblyai/openai), valid LLM creation (deepseek/groq/openai), unknown provider raises ValueError, missing API key raises ValueError (~100 lines)
- [x] 2.6 Create `src/providers/asr/groq_asr.py` — `GroqASR` impl: init with api_key+model, `transcribe()` calls `client.audio.transcriptions.create(verbose_json)`, parses words → `WordTimestamp`, `supports_file()` checks duration ≤ 25min via ffprobe, wraps errors in `ProviderError` (~120 lines)
- [x] 2.7 Create `tests/unit/providers/asr/test_groq_asr.py` — successful transcription returns `TranscriptResult`, word timestamps parsed correctly, `supports_file` true for short audio false for long, API error raises `ProviderError` with status code, ffprobe duration call mocked (~130 lines)
- [x] 2.8 Create `src/providers/llm/deepseek_llm.py` — `DeepSeekLLM` impl: init with api_key+model, `generate()` calls chat completions with `response_format={"type": "json_object"}`, parses JSON response, retries with lower temp on JSON parse failure, max 2 retries (~100 lines)
- [x] 2.9 Create `tests/unit/providers/llm/test_deepseek_llm.py` — successful generation returns dict matching schema, malformed JSON triggers retry, second failure raises `ProviderError`, temperature passed correctly, `response_format` set to `json_object` (~120 lines)

## Phase 3: Audio Processing & Transcription

- [x] 3.1 Create `src/processors/__init__.py` (~2 lines)
- [x] 3.2 Create `src/processors/audio_extractor.py` — `AudioExtractor` class: `extract(video_path) -> Path` using subprocess ffmpeg (`-ar 16000 -ac 1`), validates ffmpeg on PATH (raises `DependencyError`), outputs to `output/.checkpoint/audio/audio.wav`, captures stderr for error propagation (~100 lines)
- [x] 3.3 Create `tests/unit/processors/test_audio_extractor.py` — successful extraction calls ffmpeg with correct args, ffmpeg not found raises `DependencyError` with instructions, ffmpeg error propagates stderr + return code, output path is 16kHz mono WAV (~120 lines)
- [x] 3.4 Create `src/processors/chunking.py` — `ChunkingStrategy` ABC with `create_chunks()` and `reassemble()`, `FullAudioStrategy` (returns single chunk), `TimedChunkingStrategy(chunk_duration_min=20, overlap_s=30)` splits audio via ffmpeg with overlap, `reassemble()` merges with confidence-based overlap resolution, marks failed chunks as `[TRANSCRIPTION_FAILED]` (~150 lines)
- [x] 3.5 Create `tests/unit/processors/test_chunking.py` — `FullAudioStrategy` returns single chunk, `TimedChunkingStrategy` produces correct chunk count for 45min audio (3 chunks), overlap boundaries correct (30s), reassembly uses higher-confidence segment, `[TRANSCRIPTION_FAILED]` on failed chunk (~160 lines)
- [x] 3.6 Create `src/processors/transcriber.py` — `Transcriber` class: `transcribe(audio_path)` with adaptive chunking (try full → catch rejection → chunk → reassemble), integrates `RetryPolicy`, tracks cost via `CostEstimator`, saves checkpoint to `.checkpoint/asr/raw_transcript.json` (~120 lines)
- [x] 3.7 Create `tests/unit/processors/test_transcriber.py` — full audio success (single call), full audio rejected triggers chunking, chunk partial failure handled with `[TRANSCRIPTION_FAILED]`, retry succeeds on transient error, checkpoint saved after completion (~160 lines)

## Phase 4: Intelligence Layer (Segmentation + Enrichment)

- [x] 4.1 Create `src/processors/segmenter.py` — `ChapterSegmenter` class with `PromptManager`: `segment(transcript, video_context) -> List[Chapter]`, builds LLM prompt with video context, validates JSON response against `Chapter` Pydantic schema, retries on parse failure (max 3), saves to `.checkpoint/segmentation/chapters.json`, emits confidence warning if < 0.7 threshold (~130 lines)
- [x] 4.2 Create `tests/unit/processors/test_segmenter.py` — successful segmentation returns chapters list, invalid JSON triggers retry then raises, confidence warning logged below threshold, prompt loading and caching works, variable injection handles missing placeholders (~140 lines)
- [x] 4.3 Create `src/processors/enricher.py` — `MetadataEnricher` class: `enrich(chapter, video_context) -> EnrichedChapter`, loads `prompts/enricher.md`, injects `{{variable}}` placeholders, calls LLM provider, validates against `EnrichedChapter` schema, retries on JSON parse failure (~130 lines)
- [x] 4.4 Create `tests/unit/processors/test_enricher.py` — prompt template loaded and variables injected, LLM called with correct params, JSON validated against schema, retry on malformed response, variable injection handles missing prev/next chapter, EnrichedChapter model_dump produces metadata.json structure (~150 lines)

## Phase 5: Materialization & Orchestration

- [x] 5.1 Create `src/processors/materializer.py` — `Materializer` class: `materialize(enriched_chapters, video_path, output_dir) -> List[ChapterFolder]`, creates `output/chapters/<slug>/` dirs, generates `metadata.json` (validated schema), generates `.srt` from word timestamps (SRT format: sequence, timestamps, text), cuts `.mp4` clip via ffmpeg `-ss -to -c copy` (~150 lines)
- [x] 5.2 Create `tests/unit/processors/test_materializer.py` — chapter folder structure created, `metadata.json` validates against schema, SRT generated with correct formatting (sequence numbers, timestamps, text), ffmpeg fast-cut called with stream copy, multiple chapters create separate folders (~180 lines)
- [x] 5.3 Create `src/utils/progress.py` — `ProgressEvent` dataclass, `TUIRenderer` class with Rich `Live` context manager: `__enter__`/`__exit__`, `update(event)` method, `_build_layout()` shows stage, progress bar, cost vs budget, 10Hz refresh (~100 lines)
- [x] 5.4 Create `tests/unit/utils/test_progress.py` — TUI renderer update with progress event, layout contains stage name and percentage, cost display formatted correctly, context manager starts/stops Live, progress bar renders (~100 lines)
- [x] 5.5 Create `src/orchestrators/pipeline.py` — `PipelineOrchestrator` class: stage-based execution with checkpoint resume, budget check, progress events, checkpoint cleanup on success (~200 lines)
- [x] 5.6 Create `tests/unit/orchestrators/test_pipeline_orchestrator.py` — full pipeline execution runs all stages in order, checkpoint resume skips completed stages, budget exceeded raises `BudgetError` before stage starts, checkpoint cleaned on success, TUI receives progress events (~200 lines)
- [x] 5.7 Create `src/main.py` — CLI entry point: argparse for `--config`, `--output`, `--budget`, loads config, creates `PipelineOrchestrator` context (TUI), calls `run()`, handles exceptions with user-friendly messages, exit codes (~80 lines)
- [x] 5.8 Create `tests/unit/test_main.py` — CLI argument parsing, config loaded from YAML, pipeline invoked with correct video path, exception handling returns non-zero exit code (~80 lines)

## Phase 6: Additional Providers & Integration

- [x] 6.1 Create `src/providers/asr/assemblyai_asr.py` — `AssemblyAIASR` impl: upload audio + transcribe (basic mode only), parse result to `TranscriptResult`, `supports_file` checks duration, wraps errors in `ProviderError` (~100 lines)
- [x] 6.2 Create `tests/unit/providers/asr/test_assemblyai_asr.py` — successful transcription, upload + transcribe flow, API error handling, `supports_file` logic (~100 lines)
- [x] 6.3 Create `src/providers/asr/openai_asr.py` — `OpenAIASR` impl: `whisper-1` model, `transcribe()` calls OpenAI API, `supports_file` checks duration, same error pattern (~80 lines)
- [x] 6.4 Create `tests/unit/providers/asr/test_openai_asr.py` — successful transcription, API error handling, model selection (~80 lines)
- [x] 6.5 Create `src/providers/llm/groq_llm.py` — `GroqLLM` impl: chat completions via Groq, `generate()` with JSON schema, same retry pattern as DeepSeek (~80 lines)
- [x] 6.6 Create `tests/unit/providers/llm/test_groq_llm.py` — successful generation, JSON parse retry (~80 lines)
- [x] 6.7 Create `src/providers/llm/openai_llm.py` — `OpenAILLM` impl: `gpt-4o-mini` default, chat completions with `response_format`, same pattern (~80 lines)
- [x] 6.8 Create `tests/unit/providers/llm/test_openai_llm.py` — successful generation, JSON parse retry (~80 lines)
- [x] 6.9 Create `tests/integration/test_pipeline.py` — full E2E test with all mock providers: 10min test video → extract → transcribe → segment → enrich → materialize, verify output chapter folder structure (metadata.json, .srt, .mp4), verify checkpoint resume, verify budget enforcement, verify TUI updates (~200 lines)
- [x] 6.10 Update `.gitignore`: add `.checkpoint/`, `output/`, `*.log` patterns (~5 lines)

## Phase 7: Polish & Documentation

- [ ] 7.1 Run full test suite, verify 90%+ coverage on core modules (providers, processors, utils), fix any failures (~varies)
- [ ] 7.2 Add inline docstrings to all public classes and methods (pydoc style, one-line summaries) (~varies)
- [ ] 7.3 Verify `prompts/enricher.md` variable injection matches `Enricher` impl, fix any placeholder mismatches (~varies)
