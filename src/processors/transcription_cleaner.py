"""Transcription post-processing for error correction and quality improvement."""

import re
from typing import List, Optional

from src.models.transcription import WordTimestamp


class TranscriptionCleaner:
    """Clean and improve ASR transcription quality."""
    
    def __init__(self):
        # Common repetition patterns (remove immediate repetitions)
        self.repetition_patterns = [
            r'\b(\w+)\s+\1\b',  # Word word -> Word
            r'(?:\b\w+\b\s*){2,},?\s*(?:\b\w+\b\s*){2,}',  # Handle "Fortunately Fortunately..." 
        ]
        
        # Common misrecognitions in Spanish psychological context
        self.misrecognition_corrections = {
            # Medical/Psychological terms
            r'\bcicatras?\b': 'psiquiatras',
            r'\bquiatri[ae]s?\b': 'psiquiatras', 
            r'\bpsiqui[ae]tr[ia]\b': 'psiquiatría',
            r'\barbon[ií]a\b': 'armonía',
            r'\bdisina\b': 'decidí',
            r'\babolos?\b': 'ambos',
            r'\bsen[oó]\b': 'señor',
            r'\bcan[oó]\b': 'canción',
            r'\bficiinas\b': 'funciones',
            r'\bayototema\b': 'Ayotzinapa',
            r'\bayom[ií]\b': 'Ayomi',
            
            # Common fillers and noise words
            r'\b(?:eh|ah|um|uh|mhm|mmm|este|esto|tipo)\b': '',
            
            # Context-specific corrections
            r'\bpadre.*psiquiatra\b': 'padre psiquiatra',
            r'\bsalud.*mental\b': 'salud mental',
            r'\btrauma.*infancia\b': 'trauma de infancia',
            r'\bdepresi[oó]n\b': 'depresión',
            r'\bansiedad\b': 'ansiedad',
            r'\bestr[eé]s\b': 'estrés',
        }
        
        # Punctuation cleanup
        self.punctuation_patterns = {
            r'[.!?]{2,}': '.',
            r'\s{2,}': ' ',
            r'^[.,!?;:\s]+|[.,!?;:\s]+$', '',  # Trim punctuation and spaces
        }

    def clean_transcript_text(self, text: str) -> str:
        """Clean transcription texts using pattern-based corrections.
        
        Args:
            text: Raw transcription text.
            
        Returns:
            Cleaned transcription text.
        """
        if not text or not isinstance(text, str):
            return text
            
        cleaned = text.strip()
        
        # Apply repetition removal
        for pattern in self.repetition_patterns:
            cleaned = re.sub(pattern, r'\1', cleaned, flags=re.IGNORECASE)
            
        # Apply misrecognition corrections
        for pattern, replacement in self.misrecognition_corrections.items():
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
            
        # Apply punctuation cleanup
        for pattern, replacement in self.punctuation_patterns.items():
            cleaned = re.sub(pattern, replacement, cleaned)
            
        # Final normalization
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
        
        noise_words = {'eh', 'ah', 'um', 'uh', 'mhm', 'mmm', 'este', 'esto', 'tipo', 'pues', 'bueno'}
        
        for word in words:
            if not word.word or not isinstance(word.word, str):
                continue
                
            current_word = word.word.strip().lower()
            
            # Skip noise/filler words
            if current_word in noise_words:
                continue
                
            # Skip immediate repetitions
            if prev_word and current_word == prev_word:
                continue
                
            # Skip very short words that are likely noise (unless they're important)
            if (len(current_word) <= 2 and 
                current_word not in {'no', 'sí', 'yo', 'me', 'te', 'se', 'la', 'el', 'lo', 'un', 'es'}):
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
        # For psychological content, ensure proper terminology
        psychological_terms = {
            r'\bterapia\b': 'terapia psicológica',
            r'\bconsejer[íi]a\b': 'consejería psicológica',
            r'\bapoyo\b.*emocional': 'apoyo emocional',
        }
        
        improved = text
        for pattern, replacement in psychological_terms.items():
            if re.search(pattern, improved, re.IGNORECASE):
                improved = re.sub(pattern, replacement, improved, flags=re.IGNORECASE)
                
        return improved
            
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