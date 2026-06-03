"""Tiny numeric helpers shared by the pure control and device modules."""

from __future__ import annotations


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp ``value`` to the closed interval ``[lo, hi]``.

    Callers guarantee ``lo <= hi``; if they ever cross, the lower bound wins —
    matching the ``max(lo, min(hi, value))`` idiom this replaces.
    """
    return max(lo, min(hi, value))
