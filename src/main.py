"""CLI entry point for Echo-Bering pipeline.

Provides command-line interface for running the video-to-chapters pipeline.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

# Load environment configuration automatically before any other imports
from src.utils.env_loader import load_env_config
load_env_config()

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)

from src.config import Config, load_config
from src.orchestrators.pipeline import PipelineOrchestrator, StageResult
from src.utils.errors import BudgetError, ConfigError, EchoBeringError
from src.utils.logger import get_logger
from src.utils.progress import (
    ProgressEvent,
    ProgressEventType,
    PipelineState,
    format_cost,
    format_eta,
)

logger = get_logger(__name__)

# Default config file location
DEFAULT_CONFIG_NAME = "config.yaml"


def create_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="echo-bering",
        description="Transform video files into enriched chapter packages with ASR and LLM intelligence.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  echo-bering --config configs/large_mlx.yaml --video sources/mi_clase.mp4
  echo-bering --config configs/large_mlx.yaml --video X.mp4 --project mi_proyecto
  echo-bering --config configs/large_mlx.yaml --video X.mp4 --project foo --output ./out --budget 3.0
  echo-bering --config configs/large_mlx.yaml          # uses input_video from config
        """,
    )

    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Path to config.yaml file (default: ./config.yaml)",
    )
    parser.add_argument(
        "--video",
        type=str,
        default=None,
        help="Path to input video file (overrides config's input_video).",
    )
    parser.add_argument(
        "--project", "-p",
        type=str,
        default=None,
        help="Project name used as the output subdirectory (overrides config's project_name). "
             "If omitted and config has no project_name, it's auto-derived from the video filename.",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output directory (overrides config's output_dir).",
    )
    parser.add_argument(
        "--budget", "-b",
        type=float,
        default=None,
        help="Maximum budget in USD (overrides config's max_budget_usd).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-run all stages from scratch, ignoring cached checkpoints.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable verbose logging output.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="echo-bering 0.1.0",
    )

    return parser


def find_config(config_path: Optional[str] = None, search_dir: Optional[Path] = None) -> Path:
    """Find the configuration file.

    Args:
        config_path: Explicit path to config file.
        search_dir: Directory to search for default config.

    Returns:
        Path to the config file.

    Raises:
        ConfigError: If config file not found.
    """
    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise ConfigError(f"Config file not found: {config_path}")
        return path

    search_path = search_dir or Path.cwd()
    default_path = search_path / DEFAULT_CONFIG_NAME

    if default_path.exists():
        return default_path

    raise ConfigError(
        f"No config file found. Create {DEFAULT_CONFIG_NAME} or use --config to specify a path."
    )


def load_and_validate_config(config_path: Path) -> Config:
    """Load and validate configuration.

    Args:
        config_path: Path to the YAML config file.

    Returns:
        Validated Config instance.

    Raises:
        ConfigError: If config is invalid.
    """
    try:
        return load_config(config_path)
    except ConfigError:
        raise
    except Exception as e:
        raise ConfigError(f"Failed to load config: {e}")


def setup_progress_display() -> callable:
    """Set up the Rich-based progress display.

    Returns:
        Callback function for ProgressEvent handling.
    """
    console = Console()

    def progress_callback(event: ProgressEvent) -> None:
        """Handle progress events and display to the console."""
        if event.type == ProgressEventType.STAGE_START:
            console.print(
                f"\n[bold blue]▶[/] Stage {event.stage_index + 1}/{event.total_stages}: "
                f"[cyan]{event.stage}[/]"
            )

        elif event.type == ProgressEventType.STAGE_PROGRESS:
            pct = int(event.progress * 100)
            eta = format_eta(event.eta_seconds)
            console.print(f"  [{pct}%] ETA: {eta}", end="\r")

        elif event.type == ProgressEventType.STAGE_COMPLETE:
            duration = format_eta(event.duration_seconds) if event.duration_seconds else ""
            console.print(f"[bold green]✓[/] Stage '{event.stage}' complete {duration}")

        elif event.type == ProgressEventType.STAGE_ERROR:
            console.print(f"[bold red]✗[/] Stage '{event.stage}' failed: {event.message}")

        elif event.type == ProgressEventType.COST_UPDATE:
            cost_str = format_cost(event.cost_usd)
            budget_str = format_cost(event.budget_usd)
            remaining = event.budget_usd - event.cost_usd
            console.print(f"  [dim]Cost: {cost_str} / {budget_str} (remaining: {format_cost(remaining)})[/]")

        elif event.type == ProgressEventType.WARNING:
            console.print(f"  [yellow]⚠ WARNING:[/] {event.message}")

        elif event.type == ProgressEventType.CHAPTER_COMPLETE:
            console.print(f"  [dim]Chapter {event.chapter_number}/{event.total_chapters} materialized[/]")

    return progress_callback


def setup_orchestrator(config: Config, callback: callable) -> PipelineOrchestrator:
    """Set up the pipeline orchestrator with all components.

    Args:
        config: Validated pipeline configuration.
        callback: Progress event callback.

    Returns:
        Configured PipelineOrchestrator instance.
    """
    return PipelineOrchestrator(config=config, progress_callback=callback)


async def run_pipeline(config: Config, callback: callable, force: bool = False) -> bool:
    """Run the full pipeline with progress display.

    Args:
        config: Validated pipeline configuration.
        callback: Progress event callback.
        force: If True, re-run all stages from scratch.

    Returns:
        True if pipeline completed successfully.
    """
    orchestrator = setup_orchestrator(config, callback)

    console = Console()
    console.print(Panel(
        f"[bold]Echo-Bering Pipeline[/]\n"
        f"Input:  {config.input_video}\n"
        f"Project: {config.project_name or '(auto)'}\n"
        f"Output: {config.output_dir}\n"
        f"ASR: {config.asr_provider} | LLM: {config.llm_provider}\n"
        f"Budget: {format_cost(config.max_budget_usd)}"
        + ("\n[yellow]FORCE: re-running all stages, checkpoints will be cleared[/]" if force else ""),
        title="Starting Pipeline",
        border_style="blue",
    ))

    try:
        result = await orchestrator.execute(force=force)

        if result.success:
            console.print(Panel(
                "[bold green]Pipeline completed successfully![/]\n"
                f"Output: {config.output_dir}",
                title="Success",
                border_style="green",
            ))
            return True
        else:
            console.print(Panel(
                f"[bold red]Pipeline failed:[/] {result.error}",
                title="Failure",
                border_style="red",
            ))
            return False

    except BudgetError as e:
        console.print(Panel(
            f"[bold red]Budget exceeded:[/] {e}",
            title="Budget Error",
            border_style="red",
        ))
        return False
    except EchoBeringError as e:
        console.print(Panel(
            f"[bold red]Error:[/] {e}",
            title="Pipeline Error",
            border_style="red",
        ))
        return False
    except KeyboardInterrupt:
        console.print("\n[yellow]Pipeline interrupted by user. Cleaning up...[/]")
        return False
    except Exception as e:
        console.print(Panel(
            f"[bold red]Unexpected error:[/] {e}",
            title="Error",
            border_style="red",
        ))
        logger.exception("Unexpected pipeline error")
        return False


def _derive_project_name_from_video(video_path: Path) -> str:
    """Generate a project name from a video filename.

    Strips extension and replaces non-alphanumeric characters with underscores.
    Examples:
        'mi clase.mp4' -> 'mi_clase'
        '2022-Curso Dental Inicial.mp4' -> '2022_curso_dental_inicial'
    """
    import re
    stem = video_path.stem
    # Replace any non-alphanumeric/underscore character with underscore
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", stem).strip("_").lower()
    return normalized or "untitled"


def cli() -> None:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    try:
        # Find and load config
        config_path = find_config(args.config)
        config = load_and_validate_config(config_path)

        # Apply CLI overrides
        if args.video:
            video_path = Path(args.video)
            if not video_path.exists():
                raise ConfigError(f"Input video not found: {args.video}")
            config.input_video = video_path

        if args.project:
            config.project_name = args.project
        elif args.video and not config.project_name:
            # Auto-derive project name from the video filename
            config.project_name = _derive_project_name_from_video(config.input_video)
            logger.info("Auto-derived project_name: %s", config.project_name)

        if args.output:
            config.output_dir = Path(args.output)
            config.output_dir.mkdir(parents=True, exist_ok=True)

        if args.budget is not None:
            config.max_budget_usd = args.budget

        # Set up progress display
        callback = setup_progress_display()

        # Run pipeline
        success = asyncio.run(run_pipeline(config, callback, force=args.force))

        sys.exit(0 if success else 1)

    except ConfigError as e:
        console = Console(stderr=True)
        console.print(f"[bold red]Config Error:[/] {e}")
        sys.exit(2)
    except KeyboardInterrupt:
        console = Console()
        console.print("\n[yellow]Interrupted by user.[/]")
        sys.exit(130)
    except Exception as e:
        console = Console(stderr=True)
        console.print(f"[bold red]Error:[/] {e}")
        logger.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    cli()
