"""Configuration model and loader for Echo-Bering pipeline.

Provides a Config Pydantic model with YAML + .env loading, validation,
and auto-creation of the output directory.
"""

import os
from pathlib import Path
from typing import List, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

from src.utils.errors import ConfigError


class Config(BaseModel):
    """Pipeline configuration validated at construction time."""

    # Provider configuration
    asr_provider: str = Field(..., pattern="^(groq|assemblyai|openai|mlx-whisper)$")
    asr_model: Optional[str] = None
    llm_provider: str = Field(..., pattern="^(deepseek|groq|openai)$")
    llm_model: Optional[str] = None

    # ASR capability requirements
    required_asr_features: List[str] = Field(default_factory=list)

    # Input/Output
    input_video: Optional[Path] = None
    output_dir: Path = Field(default=Path("./output"))
    project_name: Optional[str] = Field(default=None, description="Nombre del proyecto para subdirectorio")
    language: str = "es"

    # Processing
    cut_mode: str = Field(default="fast", pattern="^(fast|precise)$")
    max_budget_usd: float = Field(default=2.0, ge=0)  # Allow 0 for local processing
    chunk_duration_minutes: int = Field(default=20, gt=0)
    chunk_overlap_seconds: int = Field(default=30, ge=0, lt=60)
    
    # Provider-specific rate limiting (seconds between requests)
    groq_request_delay_seconds: float = Field(default=0.6, ge=0)  # 100 RPM for free tier
    assemblyai_request_delay_seconds: float = Field(default=0.1, ge=0)
    
    # Hugging Face token for private models
    hf_token: Optional[str] = None

    # Confidence thresholds
    segmentation_confidence_threshold: float = Field(default=0.7, ge=0, le=1)
    transcription_confidence_threshold: float = Field(default=0.6, ge=0, le=1)

    # Segmentation
    preferred_chapters: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Target chapter count (recommendation). The LLM may produce fewer if the "
                    "content has fewer natural themes, but should not exceed it by more than ~20%.",
    )

    # Output generation flags
    generate_subtitles: bool = True
    generate_summaries: bool = True
    generate_highlights: bool = True
    generate_index: bool = False
    
    # Checkpoint management
    keep_checkpoints: bool = Field(default=True, description="Keep checkpoints after successful pipeline completion for debugging")

    @field_validator("input_video")
    @classmethod
    def validate_input_exists(cls, v: Optional[Path]) -> Optional[Path]:
        if v is None:
            return v
        if not v.exists():
            raise ValueError(f"Input video not found: {v}")
        return v

    @field_validator("output_dir")
    @classmethod
    def ensure_output_dir(cls, v: Path) -> Path:
        v.mkdir(parents=True, exist_ok=True)
        return v


def load_config(config_path: Path) -> Config:
    """Load configuration from YAML file with .env override.

    Environment variables take precedence over YAML values.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Validated Config instance.

    Raises:
        ConfigError: If config file not found or validation fails.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    # Load .env file if present
    env_path = config_path.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    # Also load from current directory .env
    load_dotenv()

    # Parse YAML
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {config_path}: {e}")

    # Apply environment variable overrides
    env_mappings = {
        "ASR_PROVIDER": "asr_provider",
        "ASR_MODEL": "asr_model",
        "LLM_PROVIDER": "llm_provider",
        "LLM_MODEL": "llm_model",
        "INPUT_VIDEO": "input_video",
        "OUTPUT_DIR": "output_dir",
        "LANGUAGE": "language",
        "CUT_MODE": "cut_mode",
        "MAX_BUDGET_USD": "max_budget_usd",
        "REQUIRED_ASR_FEATURES": "required_asr_features",
    }

    for env_key, config_key in env_mappings.items():
        env_value = os.environ.get(env_key)
        if env_value is not None:
            # Type coercion for numeric fields
            if config_key == "max_budget_usd":
                yaml_data[config_key] = float(env_value)
            elif config_key in ("output_dir", "input_video"):
                yaml_data[config_key] = Path(env_value)
            elif config_key == "required_asr_features":
                # Parse comma-separated list
                yaml_data[config_key] = [f.strip() for f in env_value.split(",") if f.strip()]
            else:
                yaml_data[config_key] = env_value

    # Build Config — validation errors become ConfigError.
    # input_video is Optional at the model level so the CLI --video flag
    # in main.py can supply it after loading.
    try:
        return Config(**yaml_data)
    except ValueError as e:
        raise ConfigError(f"Config validation failed: {e}")
