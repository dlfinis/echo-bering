"""Transcript preprocessing for cleaning and normalization.

Handles common ASR transcription issues:
- Unicode character cleanup (removes control characters, normalizes)
- Repetition removal (e.g., "la la la" → "la")
- Spacing and punctuation normalization
"""

import re
import unicodedata
from typing import List


def clean_unicode(text: str) -> str:
    """Remove control characters and normalize unicode.
    
    Args:
        text: Raw transcript text.
        
    Returns:
        Cleaned text with normalized unicode characters.
    """
    # Normalize unicode to NFC form (composed characters)
    text = unicodedata.normalize("NFC", text)
    
    # Remove control characters (except newlines and tabs)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
    
    # Replace non-breaking spaces with regular spaces
    text = text.replace("\xa0", " ")
    
    # Normalize multiple spaces to single space
    text = re.sub(r" +", " ", text)
    
    return text.strip()


def remove_repetitions(text: str, max_repeats: int = 2) -> str:
    """Remove word repetitions that are likely ASR errors.
    
    Args:
        text: Transcript text.
        max_repeats: Maximum allowed consecutive repetitions (default 2).
        
    Returns:
        Text with excessive repetitions removed.
        
    Examples:
        "la la la la casa" → "la casa"
        "muy muy muy bien" → "muy bien"
    """
    words = text.split()
    if len(words) <= max_repeats:
        return text
    
    result = []
    i = 0
    
    while i < len(words):
        # Count consecutive repetitions of current word
        word = words[i].lower()
        count = 1
        
        while i + count < len(words) and words[i + count].lower() == word:
            count += 1
        
        # If repetitions exceed max_repeats, keep only max_repeats
        if count > max_repeats:
            result.extend([words[i]] * max_repeats)
            i += count
        else:
            result.extend([words[i]] * count)
            i += count
    
    return " ".join(result)


def normalize_punctuation(text: str) -> str:
    """Normalize punctuation and spacing.
    
    Args:
        text: Transcript text.
        
    Returns:
        Text with normalized punctuation.
    """
    # Remove spaces before punctuation
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    
    # Add space after punctuation if missing
    text = re.sub(r"([,.!?;:])([A-Za-záéíóúñÁÉÍÓÚÑ])", r"\1 \2", text)
    
    # Normalize multiple punctuation (except ellipsis)
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\?{2,}", "?", text)
    text = re.sub(r"\.{4,}", "...", text)
    
    return text.strip()


def remove_filler_words(text: str) -> str:
    """Remove common filler words and hesitation markers.
    
    Args:
        text: Transcript text.
        
    Returns:
        Text with filler words removed.
    """
    # Spanish filler words
    fillers = [
        r"\beh\b",
        r"\bem\b", 
        r"\bum\b",
        r"\buh\b",
        r"\bhm+\b",
        r"\bmmm+\b",
        r"\beste\b",
        r"\besta\b",
        r"\bueno\b",
        r"\b¿\s*",  # Remove opening question marks at start
        r"\b¡\s*",  # Remove opening exclamation marks at start
    ]
    
    for filler in fillers:
        text = re.sub(filler, "", text, flags=re.IGNORECASE)
    
    # Clean up extra spaces
    text = re.sub(r" +", " ", text)
    
    return text.strip()


def remove_asr_markers(text: str) -> str:
    """Remove ASR transcription markers and non-speech indicators.
    
    Args:
        text: Transcript text.
        
    Returns:
        Text with ASR markers removed.
    """
    # Common ASR markers for non-speech events
    markers = [
        r"\[aplausos\]",
        r"\[risas\]",
        r"\[música\]",
        r"\[risa\]",
        r"\[aplauso\]",
        r"\(aplausos\)",
        r"\(risas\)",
        r"\(música\)",
        r"\(risa\)",
        r"\(aplauso\)",
        r"<aplausos>",
        r"<risas>",
        r"<música>",
        r"<risa>",
        r"<aplauso>",
        r"\[.*?ininteligible.*?\]",
        r"\[.*?inaudible.*?\]",
        r"\[.*?indistinto.*?\]",
        r"\[.*?background.*?\]",
        r"\[.*?noise.*?\]",
        r"\[.*?silence.*?\]",
    ]
    
    for marker in markers:
        text = re.sub(marker, "", text, flags=re.IGNORECASE)
    
    # Clean up extra spaces
    text = re.sub(r" +", " ", text)
    
    return text.strip()


def normalize_spanish_punctuation(text: str) -> str:
    """Normalize Spanish-specific punctuation marks.
    
    Converts unicode escape sequences to actual characters and normalizes.
    
    Args:
        text: Transcript text.
        
    Returns:
        Text with normalized Spanish punctuation.
    """
    # Replace unicode escape sequences with actual characters
    replacements = {
        r"\u00a1": "¡",  # Inverted exclamation
        r"\u00bf": "¿",  # Inverted question
        r"\u00ed": "í",  # í with accent
        r"\u00e9": "é",  # é with accent
        r"\u00e1": "á",  # á with accent
        r"\u00f3": "ó",  # ó with accent
        r"\u00fa": "ú",  # ú with accent
        r"\u00f1": "ñ",  # ñ
        r"\u00c1": "Á",  # Á with accent
        r"\u00c9": "É",  # É with accent
        r"\u00cd": "Í",  # Í with accent
        r"\u00d3": "Ó",  # Ó with accent
        r"\u00da": "Ú",  # Ú with accent
        r"\u00d1": "Ñ",  # Ñ
    }
    
    for escaped, actual in replacements.items():
        text = text.replace(escaped, actual)
    
    return text


def preprocess_transcript(text: str, remove_fillers: bool = True) -> str:
    """Apply full preprocessing pipeline to transcript.
    
    Args:
        text: Raw transcript text from ASR.
        remove_fillers: Whether to remove filler words (default True).
        
    Returns:
        Fully preprocessed and cleaned transcript.
    """
    # Step 1: Normalize Spanish punctuation (convert unicode escapes)
    text = normalize_spanish_punctuation(text)
    
    # Step 2: Clean unicode characters
    text = clean_unicode(text)
    
    # Step 3: Remove ASR markers (aplausos, risas, música, etc.)
    text = remove_asr_markers(text)
    
    # Step 4: Remove excessive repetitions
    text = remove_repetitions(text, max_repeats=2)
    
    # Step 5: Normalize punctuation
    text = normalize_punctuation(text)
    
    # Step 6: Remove filler words (always enabled)
    if remove_fillers:
        text = remove_filler_words(text)
    
    return text
