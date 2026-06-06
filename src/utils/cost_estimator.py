"""Cost estimator for ASR and LLM providers.

Per-provider price constants and cumulative cost tracking with budget enforcement.
"""

from src.utils.errors import BudgetError
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Per-minute ASR pricing (USD)
ASR_PRICES_PER_MINUTE = {
    "groq": 0.0004,       # Whisper large-v3-turbo
    "assemblyai": 0.0004,  # Basic transcription
    "openai": 0.006,       # Whisper-1
}

# Per-million-input-token LLM pricing (USD)
LLM_PRICES_PER_M_TOKENS = {
    "deepseek": 0.14,     # deepseek-chat/v4
    "groq": 0.0007,       # llama-3-70b (approx)
    "openai": 2.50,       # gpt-4o-mini
}


class CostEstimator:
    """Track cumulative pipeline costs and enforce budget limits."""

    def __init__(self):
        self.total_cost: float = 0.0

    def estimate_asr_cost(self, duration_s: float, provider: str) -> float:
        """Estimate ASR transcription cost based on audio duration.

        Args:
            duration_s: Audio duration in seconds.
            provider: ASR provider name (groq, assemblyai, openai).

        Returns:
            Estimated cost in USD.
        """
        price_per_min = ASR_PRICES_PER_MINUTE.get(provider, 0.001)
        duration_min = duration_s / 60.0
        return price_per_min * duration_min

    def estimate_llm_cost(self, tokens: int, provider: str) -> float:
        """Estimate LLM generation cost based on token count.

        Args:
            tokens: Number of input tokens.
            provider: LLM provider name (deepseek, groq, openai).

        Returns:
            Estimated cost in USD.
        """
        price_per_m = LLM_PRICES_PER_M_TOKENS.get(provider, 0.01)
        return (tokens / 1_000_000.0) * price_per_m

    def add_cost(self, amount: float) -> None:
        """Add an estimated cost to the cumulative total.

        Args:
            amount: Cost amount in USD.
        """
        self.total_cost += amount
        logger.debug("Added cost: $%.4f (total: $%.4f)", amount, self.total_cost)

    def check_budget(self, max_budget: float) -> bool:
        """Check if current cost is within budget.

        Args:
            max_budget: Maximum allowed budget in USD.

        Returns:
            True if within budget.

        Raises:
            BudgetError: If cost exceeds budget.
        """
        if self.total_cost > max_budget:
            raise BudgetError(current_cost=self.total_cost, max_budget=max_budget)
        return True
