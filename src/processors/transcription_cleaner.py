"""Transcription post-processing for error correction and quality improvement."""

import re
from typing import List, Optional

from src.models.transcription import WordTimestamp


class TranscriptionCleaner:
    """Clean and improve ASR transcription quality."""
    
    def __init__(self):
        # Common error patterns and corrections (Spanish-focused)
        self.error_patterns = {
            # Repetition patterns
            r'\b(\w+)\s+\1\b': r'\1',  # Remove immediate word repetitions
            r'(?:\b\w+\b\s*){1,3},?\s*(?:\b\w+\b\s*){1,3}': '',  # Handle "Fortunately Fortunately..." patterns
            
            # Common misrecognitions (Spanish context)
            r'\bcicatras?\b': 'psiquiatras',
            r'\bquiatri[ae]s?\b': 'psiquiatras', 
            r'\barbon[ií]a\b': 'armonía',
            r'\bdisina\b': 'decidí',
            r'\babolos?\b': 'ambos',
            r'\bsen[oó]\b': 'señor',
            r'\bcan[oó]\b': 'canción',
            
            # Noise and filler removal
            r'\b(?:eh|ah|um|uh|mhm|mmm)\b': '',
            r'\b(?:tipo|este|esto|aquí|allí)\b\s*,?\s*': '',
            
            # Multiple punctuation cleanup
            r'[.!?]{2,}': '.',
            r'\s{2,}': ' ',
        }
        
        # Context-aware corrections
        self.context_corrections = [
            (r'padre.*psiquiatra', 'padre psiquiatra'),
            (r'salud.*mental', 'salud mental'),
            (r'trauma.*infancia', 'trauma de infancia'),
        ]

    def clean_transcript_text(self, text: str) -> str:
        """Clean transcription text using pattern-based corrections.
        
        Args:
            text: Raw transcription text.
            
        Returns:
            Cleaned transcription text.
        """
        if not text:
            return text
            
        cleaned = text.strip()
        
        # Apply pattern-based corrections
        for pattern, replacement in self.error_patterns.items():
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
            
        # Apply context-aware corrections  
        for pattern, replacement in self.context_corrections:
            if re.search(pattern, cleaned, re.IGNORECASE):
                cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
                
        # Final cleanup
        cleaned = re.sub(r'\s+', ' ', cleaned)  # Normalize whitespace
        cleaned = cleaned.strip('.,!?;: ')
        
        return cleaned if cleaned else text

    def clean_word_timestamps(self, words: List[WordTimestamp]) -> List[WordTimestamp]:
        """Clean word-level timestamps by removing noise words and repetitions.
        
        Args:
            words: List of word timestamps.
            
        Returns:
            Cleaned list of word timestamps.
        """
        if not words:
            return words
            
        cleaned_words = []
        prev_word = None
        
        for word in words:
            current_word = word.word.strip().lower()
            
            # Skip noise/filler words
            if current_word in {'eh', 'ah', 'um', 'uh', 'mhm', 'mmm', 'tipo', 'este'}:
                continue
                
            # Skip immediate repetitions
            if prev_word and current_word == prev_word:
                continue
                
            # Skip very short words that are likely noise (unless they're important)
            if len(current_word) <= 2 and current_word not in {'no', 'sí', 'yo', 'me', 'te', 'se', 'la', 'el', 'lo'}:
                continue
                
            cleaned_words.append(word)
            prev_word = current_word
            
        return cleaned_words if cleaned_words else words

    def apply_contextual_improvement(self, text: str, video_context: Optional[str] = None) -> str:
        """Apply contextual improvements based on video topic.
        
        Args:
            text: Cleaned transcription text.
            video_context: Video topic or domain context.
            
        Returns:
            Contextually improved transcription text.
        """
        # For now, return as-is. Could integrate domain-specific dictionaries later.
        return text