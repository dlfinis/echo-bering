"""Environment configuration loader."""
import os
from pathlib import Path

def load_env_config():
    """Load environment configuration from .env files automatically.
    
    Loads from:
    1. Current working directory .env
    2. Project root .env 
    3. System environment variables (fallback)
    
    Returns:
        dict with provider configurations
    """
    config = {}
    
    # Find project root
    current_dir = Path.cwd()
    project_root = current_dir
    while project_root.parent != project_root:
        if (project_root / ".env").exists():
            break
        project_root = project_root.parent
    else:
        project_root = current_dir
    
    # Load .env files
    env_files = []
    if (current_dir / ".env").exists():
        env_files.append(current_dir / ".env")
    if (project_root / ".env").exists() and project_root != current_dir:
        env_files.append(project_root / ".env")
    
    # Load environment variables
    for env_file in env_files:
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        os.environ[key] = value
    
    # Provider configurations
    config["groq"] = {
        "api_key": os.getenv("GROQ_API_KEY"),
        "enabled": bool(os.getenv("GROQ_API_KEY"))
    }
    config["deepseek"] = {
        "api_key": os.getenv("DEEPSEEK_API_KEY"), 
        "enabled": bool(os.getenv("DEEPSEEK_API_KEY"))
    }
    config["assemblyai"] = {
        "api_key": os.getenv("ASSEMBLYAI_API_KEY"),
        "enabled": bool(os.getenv("ASSEMBLYAI_API_KEY"))
    }
    
    return config