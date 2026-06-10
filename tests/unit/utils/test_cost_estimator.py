"""Tests for CostEstimator in src.utils.cost_estimator."""

import pytest

from src.utils.cost_estimator import CostEstimator
from src.utils.errors import BudgetError


class TestCostEstimator:
    """Test ASR and LLM cost estimation."""

    def test_estimate_groq_asr_cost(self):
        """Groq Whisper pricing: $0.0004/min."""
        estimator = CostEstimator()
        # 60 seconds = 1 minute
        cost = estimator.estimate_asr_cost(duration_s=60.0, provider="groq")
        assert cost > 0
        # Groq: 0.0004 per minute → 60s = 0.0004
        assert abs(cost - 0.0004) < 0.0001

    def test_estimate_openai_asr_cost(self):
        """OpenAI Whisper pricing: $0.006/min."""
        estimator = CostEstimator()
        cost = estimator.estimate_asr_cost(duration_s=60.0, provider="openai")
        assert abs(cost - 0.006) < 0.001

    def test_estimate_assemblyai_asr_cost(self):
        """AssemblyAI pricing: $0.0004/min (basic)."""
        estimator = CostEstimator()
        cost = estimator.estimate_asr_cost(duration_s=60.0, provider="assemblyai")
        assert cost > 0

    def test_estimate_llm_cost_per_token(self):
        """LLM cost based on token count and provider."""
        estimator = CostEstimator()
        # DeepSeek: $0.14/M input tokens
        cost = estimator.estimate_llm_cost(tokens=10000, provider="deepseek")
        assert cost > 0
        # 10000 tokens = 0.01M → $0.0014
        assert abs(cost - 0.0014) < 0.0001

    def test_add_cost_cumulative(self):
        """add_cost accumulates across calls."""
        estimator = CostEstimator()
        estimator.add_cost(0.50)
        estimator.add_cost(0.30)
        assert abs(estimator.total_cost - 0.80) < 0.001

    def test_total_cost_starts_at_zero(self):
        estimator = CostEstimator()
        assert estimator.total_cost == 0.0

    def test_check_budget_within_limit(self):
        """check_budget returns True when within budget."""
        estimator = CostEstimator()
        estimator.add_cost(1.0)
        assert estimator.check_budget(max_budget=2.0) is True

    def test_check_budget_exceeds_raises(self):
        """check_budget raises BudgetError when exceeded."""
        estimator = CostEstimator()
        estimator.add_cost(3.0)
        with pytest.raises(BudgetError) as exc_info:
            estimator.check_budget(max_budget=2.0)
        assert exc_info.value.current_cost == 3.0
        assert exc_info.value.max_budget == 2.0

    def test_asr_cost_scales_with_duration(self):
        """Cost scales linearly with audio duration."""
        estimator = CostEstimator()
        cost_1min = estimator.estimate_asr_cost(duration_s=60.0, provider="openai")
        cost_5min = estimator.estimate_asr_cost(duration_s=300.0, provider="openai")
        assert abs(cost_5min - cost_1min * 5) < 0.001

    def test_llm_cost_scales_with_tokens(self):
        """LLM cost scales linearly with token count."""
        estimator = CostEstimator()
        cost_1k = estimator.estimate_llm_cost(tokens=1000, provider="deepseek")
        cost_10k = estimator.estimate_llm_cost(tokens=10000, provider="deepseek")
        assert abs(cost_10k - cost_1k * 10) < 0.001
