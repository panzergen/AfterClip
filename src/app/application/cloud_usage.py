"""Approximate cloud cost estimation from recorded usage (Phase 3).

Pricing is a rough order of magnitude and may drift; treat every figure as an
estimate, never a quote. Detailed cost metering lives in a later phase.
"""

from app.domain.models import CloudUsage

# Approximate USD per 1M tokens: (input, output).
_PRICING_PER_MILLION = {
    "gemini-flash-latest": (0.30, 2.50),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
}

COST_NOTE = "Approximate estimate; provider pricing applies and may have changed."


def estimate_cost_usd(usage: CloudUsage) -> float | None:
    """Return an approximate USD cost, or None when the model is not priced."""
    rates = next(
        (value for name, value in _PRICING_PER_MILLION.items() if usage.model.startswith(name)),
        None,
    )
    if rates is None:
        return None
    input_rate, output_rate = rates
    cost = usage.input_tokens / 1_000_000 * input_rate
    cost += usage.output_tokens / 1_000_000 * output_rate
    return round(cost, 6)
