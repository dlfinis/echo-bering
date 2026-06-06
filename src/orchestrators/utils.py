import re
import time
from pathlib import Path


def _format_duration(seconds: float) -> str:
    """Convert seconds to HH:MM:SS.mmm format.
    
    Args:
        seconds: Duration in seconds.
        
    Returns:
        Formatted duration string.
    """
    if seconds <= 0:
        return "00:00:00.000"
        
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug.
    
    Args:
        text: Input text to convert.
        
    Returns:
        Clean slug with only lowercase letters, numbers, and hyphens.
    """
    # Convert to lowercase
    text = text.lower()
    # Replace accented characters
    text = re.sub(r'[áàâãäå]', 'a', text)
    text = re.sub(r'[éèêë]', 'e', text)
    text = re.sub(r'[íìîï]', 'i', text)
    text = re.sub(r'[óòôõö]', 'o', text)
    text = re.sub(r'[úùûü]', 'u', text)
    text = re.sub(r'[ñ]', 'n', text)
    text = re.sub(r'[ç]', 'c', text)
    # Keep only alphanumeric and spaces/hyphens
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    # Replace multiple spaces/hyphens with single hyphen
    text = re.sub(r'[\s-]+', '-', text)
    # Remove leading/trailing hyphens
    text = text.strip('-')
    return text or 'chapter'


def generate_project_name(config, existing_projects=None):
    """Generate a project name based on config and existing projects.
    
    Args:
        config: Pipeline configuration
        existing_projects: Set of existing project names to avoid conflicts
        
    Returns:
        Project name string
    """
    if config.project_name:
        return config.project_name
        
    # Extract base name from video title
    video_stem = config.input_video.stem.replace(" ", "_").replace("-", "_")
    base_name = video_stem.lower()
    
    # Radio alphabet suffixes
    radio_alphabet = [
        "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel",
        "india", "juliett", "kilo", "lima", "mike", "november", "oscar", "papa",
        "quebec", "romeo", "sierra", "tango", "uniform", "victor", "whiskey", 
        "xray", "yankee", "zulu"
    ]
    
    if not existing_projects:
        return f"{base_name}_{radio_alphabet[0]}"
        
    # Find next available suffix
    for i, suffix in enumerate(radio_alphabet):
        candidate = f"{base_name}_{suffix}"
        if candidate not in existing_projects:
            return candidate
            
    # Fallback to timestamp if all radio alphabet exhausted
    return f"{base_name}_{int(time.time())}"