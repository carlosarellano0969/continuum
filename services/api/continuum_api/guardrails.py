"""Output guardrail: customer-facing answers must not state invented financial or product terms.

The active policy says "never invent rates, payments, or discounts"; a prompt alone does
not stop the model from doing it, so Continuum checks the answer and regenerates once.
"""

from __future__ import annotations

import re

# Specific numbers a customer could hold the business to: percentages, prices, APR,
# and durations or counts attached to payments, installments, warranties or months.
_INVENTED_TERMS = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:%|percent)"
    r"|\$\s?\d"
    r"|\bAPR\b"
    r"|\b\d+[\s-]*(?:months?|years?|days?|weeks?|installments?|payments?)\b)",
    re.IGNORECASE,
)

RETRY_NOTE = (
    "\n\nGuardrail: your previous answer stated specific numbers (rates, percentages, prices or durations). "
    "Answer again without any numbers; offer to confirm verified terms instead."
)


def invented_terms(text: str) -> str | None:
    """Return the first invented-looking term in ``text``, or None."""
    match = _INVENTED_TERMS.search(text or "")
    return match.group(0) if match else None


def is_unsafe(text: str) -> bool:
    return invented_terms(text) is not None
