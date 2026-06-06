"""Prompt management for LLM interactions."""

import json
import re
from pathlib import Path
from typing import Any, Dict

from src.utils.logger import get_logger

logger = get_logger(__name__)


class PromptManager:
    """Manages LLM prompt templates with variable injection.
    
    Supports Mustache-style templating with conditional sections.
    """

    def __init__(self, prompts_dir: Path = None):
        """Initialize PromptManager.
        
        Args:
            prompts_dir: Directory containing prompt templates (default: ./prompts)
        """
        self.prompts_dir = prompts_dir or Path(__file__).parent.parent.parent / "prompts"
        self._cache = {}

    def load(self, filename: str) -> str:
        """Load prompt template from file.
        
        Args:
            filename: Name of the prompt file (e.g., "segmenter.md")
            
        Returns:
            Raw prompt template content.
        """
        if filename in self._cache:
            return self._cache[filename]
            
        prompt_path = self.prompts_dir / filename
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {prompt_path}")
            
        content = prompt_path.read_text(encoding="utf-8")
        self._cache[filename] = content
        return content

    def inject(self, template: str, **kwargs) -> str:
        """Inject variables into prompt template using Mustache-style syntax.
        
        Supports:
        - {{VARIABLE}} for simple substitution
        - {{#CONDITION}}...{{/CONDITION}} for conditional blocks
        - {{^CONDITION}}...{{/CONDITION}} for inverted conditionals
        
        Args:
            template: Prompt template with placeholders
            **kwargs: Variables to inject
            
        Returns:
            Rendered prompt with variables substituted
        """
        result = template
        
        # Handle conditional sections first
        def replace_conditionals(match):
            tag = match.group(1)
            content = match.group(2)
            is_inverted = tag.startswith('^')
            if is_inverted:
                tag = tag[1:]
                condition = kwargs.get(tag) is None or not kwargs.get(tag)
            else:
                condition = kwargs.get(tag) is not None and kwargs.get(tag)
                
            if condition:
                return content
            else:
                return ""
                
        # {{#condition}}content{{/condition}} and {{^condition}}content{{/condition}}
        result = re.sub(r'{{([#^]\w+)}}(.*?){{/\1}}', replace_conditionals, result, flags=re.DOTALL)
        
        # Handle simple variable substitution
        for key, value in kwargs.items():
            placeholder = f"{{{{{key}}}}}"
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value, ensure_ascii=False, indent=2)
            else:
                value_str = str(value)
            result = result.replace(placeholder, value_str)
            
        return result

    def load_and_inject(self, filename: str, **kwargs) -> str:
        """Load prompt template and inject variables in one step.
        
        Args:
            filename: Name of the prompt file
            **kwargs: Variables to inject
            
        Returns:
            Rendered prompt ready for LLM
        """
        template = self.load(filename)
        return self.inject(template, **kwargs)