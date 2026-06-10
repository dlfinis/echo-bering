"""Unit tests for transcript preprocessing."""

import pytest

from src.processors.transcript_preprocessor import (
    clean_unicode,
    normalize_punctuation,
    preprocess_transcript,
    remove_filler_words,
    remove_repetitions,
)


class TestCleanUnicode:
    """Tests for unicode character cleaning."""
    
    def test_removes_control_characters(self):
        """Should remove control characters except newlines and tabs."""
        text = "Hello\x00World\x1fTest"
        result = clean_unicode(text)
        assert result == "HelloWorldTest"
    
    def test_preserves_newlines_and_tabs(self):
        """Should preserve newlines and tabs."""
        text = "Line1\nLine2\tTab"
        result = clean_unicode(text)
        assert result == "Line1\nLine2\tTab"
    
    def test_normalizes_non_breaking_spaces(self):
        """Should replace non-breaking spaces with regular spaces."""
        text = "Hello\xa0World"
        result = clean_unicode(text)
        assert result == "Hello World"
    
    def test_normalizes_multiple_spaces(self):
        """Should collapse multiple spaces into one."""
        text = "Hello    World"
        result = clean_unicode(text)
        assert result == "Hello World"
    
    def test_strips_whitespace(self):
        """Should strip leading and trailing whitespace."""
        text = "  Hello World  "
        result = clean_unicode(text)
        assert result == "Hello World"


class TestRemoveRepetitions:
    """Tests for word repetition removal."""
    
    def test_removes_excessive_repetitions(self):
        """Should reduce repetitions to max_repeats."""
        text = "la la la la la casa"
        result = remove_repetitions(text, max_repeats=2)
        assert result == "la la casa"
    
    def test_preserves_normal_repetitions(self):
        """Should preserve repetitions within limit."""
        text = "la la casa"
        result = remove_repetitions(text, max_repeats=2)
        assert result == "la la casa"
    
    def test_case_insensitive(self):
        """Should detect repetitions regardless of case."""
        text = "La la LA la casa"
        result = remove_repetitions(text, max_repeats=2)
        # Keeps first occurrence's case, reduces to max_repeats
        assert result.count(" ") == 2  # "La La casa" has 2 spaces
        assert "casa" in result.lower()
    
    def test_handles_multiple_repetition_groups(self):
        """Should handle multiple groups of repetitions."""
        text = "muy muy muy bien muy muy muy mal"
        result = remove_repetitions(text, max_repeats=2)
        assert result == "muy muy bien muy muy mal"
    
    def test_single_word(self):
        """Should handle single word without error."""
        text = "hola"
        result = remove_repetitions(text, max_repeats=2)
        assert result == "hola"
    
    def test_empty_string(self):
        """Should handle empty string."""
        text = ""
        result = remove_repetitions(text, max_repeats=2)
        assert result == ""


class TestNormalizePunctuation:
    """Tests for punctuation normalization."""
    
    def test_removes_spaces_before_punctuation(self):
        """Should remove spaces before punctuation."""
        text = "Hello , World !"
        result = normalize_punctuation(text)
        assert result == "Hello, World!"
    
    def test_adds_space_after_punctuation(self):
        """Should add space after punctuation if missing."""
        text = "Hello,World!Test"
        result = normalize_punctuation(text)
        assert result == "Hello, World! Test"
    
    def test_normalizes_exclamation_marks(self):
        """Should collapse multiple exclamation marks."""
        text = "Wow!!!"
        result = normalize_punctuation(text)
        assert result == "Wow!"
    
    def test_normalizes_question_marks(self):
        """Should collapse multiple question marks."""
        text = "What???"
        result = normalize_punctuation(text)
        assert result == "What?"
    
    def test_preserves_ellipsis(self):
        """Should preserve ellipsis."""
        text = "Wait....."
        result = normalize_punctuation(text)
        assert result == "Wait..."


class TestRemoveFillerWords:
    """Tests for filler word removal."""
    
    def test_removes_common_fillers(self):
        """Should remove common Spanish filler words."""
        text = "este um la casa"
        result = remove_filler_words(text)
        assert "este" not in result.lower()
        assert "um" not in result.lower()
        assert "la casa" in result
    
    def test_preserves_content_words(self):
        """Should not remove content words."""
        text = "La casa es grande"
        result = remove_filler_words(text)
        assert result == "La casa es grande"
    
    def test_cleans_extra_spaces(self):
        """Should clean up extra spaces after removal."""
        text = "este um la casa"
        result = remove_filler_words(text)
        # Should not have multiple consecutive spaces
        assert "  " not in result


class TestPreprocessTranscript:
    """Integration tests for full preprocessing pipeline."""
    
    def test_full_pipeline(self):
        """Should apply all preprocessing steps."""
        text = "Hola\xa0\xa0hola hola hola hola mundo!"
        result = preprocess_transcript(text)
        # Should normalize spaces, reduce repetitions, normalize punctuation
        assert "\xa0" not in result
        assert result.count("hola") <= 2
    
    def test_with_fillers_removal(self):
        """Should remove fillers when enabled."""
        text = "este um la casa"
        result = preprocess_transcript(text, remove_fillers=True)
        assert "este" not in result.lower()
    
    def test_without_fillers_removal(self):
        """Should preserve fillers by default."""
        text = "este um la casa"
        result = preprocess_transcript(text, remove_fillers=False)
        assert "este" in result.lower()
    
    def test_handles_unicode_transcription(self):
        """Should clean unicode characters from real transcription."""
        text = "\u00a1Gracias! \u00bfC\u00f3mo est\u00e1s?"
        result = preprocess_transcript(text)
        # Should preserve Spanish characters
        assert "¡" in result
        assert "¿" in result
        assert "está" in result
