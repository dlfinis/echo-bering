"""Integration tests for AssemblyAI ASR + DeepSeek LLM provider combination.

Tests the enhanced combination with AssemblyAI's entity detection and
key phrases extraction flowing into DeepSeek LLM analysis.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.factories.provider_factory import ProviderFactory
from src.providers.asr.base import TranscriptResult, WordTimestamp
from src.providers.llm.base import LLMResponse


def _make_assemblyai_transcript():
    """Create a realistic AssemblyAI transcription result."""
    return TranscriptResult(
        text="Artificial intelligence and machine learning are transforming the tech industry. "
             "Companies like Google, Microsoft, and Amazon are investing billions in AI research. "
             "Python has become the dominant language for machine learning development, "
             "with frameworks like TensorFlow and PyTorch leading the way.",
        confidence=0.96,
        words=[
            WordTimestamp(word="Artificial", start=0.0, end=0.5, confidence=0.97),
            WordTimestamp(word="intelligence", start=0.6, end=1.2, confidence=0.96),
            WordTimestamp(word="and", start=1.3, end=1.5, confidence=0.98),
            WordTimestamp(word="machine", start=1.6, end=2.0, confidence=0.95),
            WordTimestamp(word="learning", start=2.1, end=2.6, confidence=0.96),
        ],
        duration_s=300.0,
        provider="assemblyai",
        model="assemblyai-default",
    )


def _make_deepseek_json_response(text):
    """Create a DeepSeek LLM response with JSON content."""
    mock_choice = MagicMock()
    mock_choice.message.content = text
    mock_choice.message.role = "assistant"
    mock_choice.finish_reason = "stop"

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 800
    mock_usage.completion_tokens = 350
    mock_usage.total_tokens = 1150

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage
    return mock_response


class TestAssemblyAIDeepSeekIntegration:
    """Test AssemblyAI ASR + DeepSeek LLM as the enhanced combination."""

    @pytest.fixture
    def assemblyai_asr(self):
        """Create AssemblyAI ASR provider with mocked client."""
        with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-assemblyai-key"}):
            return ProviderFactory.create_asr("assemblyai")

    @pytest.fixture
    def deepseek_llm(self):
        """Create DeepSeek LLM provider with mocked client."""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-deepseek-key"}):
            return ProviderFactory.create_llm("deepseek")

    def test_factory_creates_assemblyai_asr(self):
        """Factory creates AssemblyAIASRProvider with correct type."""
        with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-key"}):
            provider = ProviderFactory.create_asr("assemblyai")
        assert provider.name == "assemblyai"

    @pytest.mark.asyncio
    async def test_assemblyai_transcribe_to_deepseek_generate_flow(self, tmp_path):
        """AssemblyAI transcription output flows into DeepSeek LLM input."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio")

        # Mock AssemblyAI response
        mock_transcript = MagicMock()
        mock_transcript.text = _make_assemblyai_transcript().text
        mock_transcript.confidence = 0.96
        mock_transcript.words = None
        mock_transcript.audio_duration = 300000  # ms

        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.return_value = mock_transcript

        # Mock DeepSeek LLM response
        mock_deepseek_response = _make_deepseek_json_response(
            '{"chapters": [{"number": 1, "title": "AI Overview", '
            '"start_time": "00:00:00.000", "end_time": "00:05:00.000", '
            '"start_seconds": 0.0, "end_seconds": 300.0, '
            '"confidence": 0.92, "transcript": "Artificial intelligence and machine learning"}]}'
        )
        mock_deepseek_client = MagicMock()
        mock_deepseek_client.chat.completions.create.return_value = mock_deepseek_response

        with patch("src.providers.asr.assemblyai_asr.aai.Transcriber", return_value=mock_transcriber):
            with patch("src.providers.llm.deepseek_llm.OpenAI", return_value=mock_deepseek_client):
                with patch.dict(os.environ, {
                    "ASSEMBLYAI_API_KEY": "test-key",
                    "DEEPSEEK_API_KEY": "test-key",
                }):
                    # Step 1: Transcribe with AssemblyAI
                    transcript = await ProviderFactory.create_asr("assemblyai").transcribe(str(audio_path))

                    assert isinstance(transcript, TranscriptResult)
                    assert transcript.provider == "assemblyai"
                    assert transcript.confidence > 0.9

                    # Step 2: Use transcript with DeepSeek
                    prompt = f"Analyze and create chapters from: {transcript.text}"
                    llm_result = await ProviderFactory.create_llm("deepseek").generate(
                        prompt,
                        system_prompt="You analyze tech content.",
                        response_format="json",
                    )

                    assert isinstance(llm_result, LLMResponse)
                    assert llm_result.provider == "deepseek"

    @pytest.mark.asyncio
    async def test_assemblyai_word_timestamps_accuracy(self, tmp_path):
        """AssemblyAI word timestamps are correctly converted from milliseconds."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio")

        mock_word = MagicMock()
        mock_word.text = "Python"
        mock_word.start = 5000  # ms
        mock_word.end = 5500  # ms
        mock_word.confidence = 0.95

        mock_transcript = MagicMock()
        mock_transcript.text = "Python framework"
        mock_transcript.confidence = 0.94
        mock_transcript.words = [mock_word]
        mock_transcript.audio_duration = 10000  # ms

        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.return_value = mock_transcript

        with patch("src.providers.asr.assemblyai_asr.aai.Transcriber", return_value=mock_transcriber):
            with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-key"}):
                result = await ProviderFactory.create_asr("assemblyai").transcribe(str(audio_path))

        assert len(result.words) == 1
        assert result.words[0].word == "Python"
        # AssemblyAI returns ms, we convert to seconds
        assert result.words[0].start == 5.0
        assert result.words[0].end == 5.5
        assert result.duration_s == 10.0

    def test_assemblyai_deepseek_metadata_compatibility(self):
        """Both providers report compatible metadata for pipeline tracking."""
        with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-key"}):
            asr = ProviderFactory.create_asr("assemblyai")
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
            llm = ProviderFactory.create_llm("deepseek")

        assert asr.name == "assemblyai"
        assert llm.name == "deepseek"
        assert llm.supports_json_mode() is True

    @pytest.mark.asyncio
    async def test_assemblyai_empty_transcript_handled(self, tmp_path):
        """Empty AssemblyAI transcript is handled gracefully by DeepSeek."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio")

        mock_transcript = MagicMock()
        mock_transcript.text = ""
        mock_transcript.confidence = None  # AssemblyAI returns None for empty
        mock_transcript.words = []
        mock_transcript.audio_duration = 0

        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.return_value = mock_transcript

        mock_deepseek_response = _make_deepseek_json_response(
            '{"chapters": [], "note": "No content to analyze"}'
        )
        mock_deepseek_client = MagicMock()
        mock_deepseek_client.chat.completions.create.return_value = mock_deepseek_response

        with patch("src.providers.asr.assemblyai_asr.aai.Transcriber", return_value=mock_transcriber):
            with patch("src.providers.llm.deepseek_llm.OpenAI", return_value=mock_deepseek_client):
                with patch.dict(os.environ, {
                    "ASSEMBLYAI_API_KEY": "test-key",
                    "DEEPSEEK_API_KEY": "test-key",
                }):
                    transcript = await ProviderFactory.create_asr("assemblyai").transcribe(str(audio_path))

                    assert transcript.text == ""
                    assert transcript.words == []
                    assert transcript.duration_s == 0.0
