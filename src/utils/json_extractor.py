"""JSON extraction utilities for LLM responses."""

import json
import re
from typing import Any, Dict, List


def extract_json_from_llm_response(response: str) -> Dict[str, Any]:
    """Extract JSON object from LLM response with robust parsing.
    
    Handles common LLM JSON formatting issues:
    - Extra text before/after JSON
    - Missing quotes around keys
    - Trailing commas
    - Multiple JSON objects
    
    Args:
        response: Raw LLM response text.
        
    Returns:
        Parsed JSON dictionary.
        
    Raises:
        ValueError: If no valid JSON can be extracted.
    """
    # Try direct JSON parsing first
    try:
        return json.loads(response.strip())
    except json.JSONDecodeError:
        pass
    
    # Look for JSON object between { and }
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    # Look for JSON array between [ and ] (for lists)
    array_match = re.search(r'\[.*\]', response, re.DOTALL)
    if array_match:
        json_str = array_match.group(0)
        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, list) and len(parsed) > 0:
                return parsed[0]  # Return first object if it's a list
        except json.JSONDecodeError:
            pass
    
    # Try to fix common JSON issues
    cleaned_response = _fix_common_json_issues(response)
    try:
        return json.loads(cleaned_response)
    except json.JSONDecodeError:
        pass
    
    # Last resort: extract all key-value pairs
    return _extract_key_value_pairs(response)


def _fix_common_json_issues(text: str) -> str:
    """Fix common JSON formatting issues in LLM responses."""
    # Remove markdown code blocks
    text = re.sub(r'```json\s*|\s*```', '', text, flags=re.IGNORECASE)
    
    # Remove any text before the first {
    first_brace = text.find('{')
    if first_brace != -1:
        text = text[first_brace:]
    
    # Remove any text after the last }
    last_brace = text.rfind('}')
    if last_brace != -1:
        text = text[:last_brace + 1]
    
    # Fix trailing commas
    text = re.sub(r',\s*([}\]])', r'\1', text)
    
    # Add quotes to unquoted keys (simple heuristic)
    text = re.sub(r'([{,]\s*)(\w+)(\s*:)', r'\1"\2"\3', text)
    
    return text.strip()


def _extract_key_value_pairs(text: str) -> Dict[str, Any]:
    """Extract key-value pairs as fallback when JSON parsing fails."""
    result = {}
    
    # Simple key-value extraction patterns
    patterns = [
        r'"?(\w+)"?\s*:\s*"([^"]*)"',
        r'"?(\w+)"?\s*:\s*([^,\n}]+)',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for key, value in matches:
            try:
                # Try to parse as JSON value
                result[key] = json.loads(value.strip())
            except json.JSONDecodeError:
                # Keep as string
                result[key] = value.strip()
    
    return result if result else {"error": "Could not parse JSON", "raw_response": text[:500]}