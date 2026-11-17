"""The rule that decides whether a symbol may be treated as market data.

WHY THIS FILE EXISTS
--------------------
On 15/11/2026 the verification ledger turned out to hold 200 rows whose
symbols were ``TST0`` .. ``TST199``. Every one of them had the same
invented numbers - ``reference_close = 100.0``, ``predicted_close = 101.0``
- and every one of them was tagged ``source = "auto_eod_batch"``, the
tag that means "the system published this before the session opened".

    10|No symbol in the lakehouse was named ``TST0``. There was no model
    for it on disk, no Bronze partition, no Silver partition, no Gold
    partition. The rows had been written straight into MySQL, and they
    were indistinguishable from real published forecasts once they were
    in the table - the Dashboard's "verified" count included them.

This module turns "that symbol does not look like a test fixture" into an
explicit, testable rule, so the next occurrence is caught by a test
instead of by a human noticing a number that is too round.

WHAT COUNTS AS A FABRICATED SYMBOL
----------------------------------
A symbol whose name is a well-known test-fixture marker: ``TST``, ``TEST``,
``DEMO``, ``MOCK``, ``FAKE``, ``DUMMY``, ``SAMPLE``, ``PLACEHOLDER``,
``XXX``. The match is on the PREFIX, so ``TST0``, ``TEST-AAPL`` and
``MOCK_1`` are all caught.

    20|WHY A PREFIX AND NOT AN ALLOWLIST
------------------------------------
An allowlist of real tickers would have to be maintained forever and
would break the moment a new symbol is ingested. A prefix denylist only
needs to know what a test fixture looks like, which does not change.

The stronger check - "does this symbol exist in the Gold layer?" - is not
here on purpose. It needs a storage round-trip, and it belongs to the
verification pass (``scripts/purge_fake_predictions.py``) rather than to
the write path, which must stay cheap and must not depend on the storage
backend being up.

WHAT THIS IS NOT
-----------------
This is not a licence to write invented numbers under a REAL ticker. A
symbol that really trades is a symbol the platform can back with a
stored session. The denylist is a cheap first line of defence against the
obvious failure, not a substitute for real data.
"""

from __future__ import annotations

import re

#: Prefixes that mark a symbol as a test fixture rather than a ticker.
#:
#: Upper-cased and compared as a prefix, so the match is case-insensitive
#: and a real ticker is never caught by accident: no exchange uses one of
#: these words as the start of a listing code.
FABRICATED_SYMBOL_PREFIXES: tuple[str, ...] = (
    "TST",
    "TEST",
    "DEMO",
    "MOCK",
    "FAKE",
    "DUMMY",
    "SAMPLE",
    "PLACEHOLDER",
    "XXX",
)

#: The same rule as a regular expression, for a single-pass match.
_FABRICATED_PATTERN = re.compile(
    r"^(?:" + "|".join(re.escape(prefix) for prefix in FABRICATED_SYMBOL_PREFIXES) + r")",
    re.IGNORECASE,
)


def is_fabricated_symbol(symbol: str | None) -> bool:
    """True when the symbol is a test fixture rather than a market ticker."""
    if not symbol:
        return True
    return bool(_FABRICATED_PATTERN.match(str(symbol).strip()))


def describe_fabricated_symbol(symbol: str | None) -> str:
    """The reason a symbol was rejected, for a log or an error message."""
    return (
        f"{symbol!r} is not a market ticker: its name starts with one of the "
        f"test-fixture markers ({', '.join(FABRICATED_SYMBOL_PREFIXES)}). "
        "A forecast may only be stored for a symbol that exists in the "
        "lakehouse."
    )


# ── Physically impossible prices ────────────────────────────────────────────
#
# WHY THIS RULE EXISTS
# --------------------
# On 15/11/2026 the verification ledger was found to hold nineteen
# forecasts whose PREDICTED price was negative or absurdly far from the
# reference price:
#
#     LCID  reference  3.61   predicted  -4.09
#     SOXS  reference 45.72   predicted  -359,121,248
#     UVXY  reference 17.35   predicted  -33,570.79
#
# A negative price is not a "large error" - it is a value no exchange can
# print. It happens when a price-LEVEL model is trained on a history that
# mixes two price scales (see ``app/lakehouse/scale_repair.py``): the
# regression extrapolates off the end of the series and lands anywhere.
#
# WHY THE FORECAST IS REJECTED RATHER THAN CLAMPED
# ------------------------------------------------
# Clamping a negative price to zero would still be an invented number, and
# it would hide the real problem - that the model cannot be trusted for
# this symbol until its history is on one scale. Rejecting the forecast
# leaves an honest gap: the symbol produces no forecast for that session,
# and the report says so.
#
# WHY THE REFERENCE PRICE IS ALSO CHECKED
# ----------------------------------------
# A forecast whose reference is itself nonsensical (a negative or zero
# price) means the ANCHOR is broken, so the forecast is meaningless no
# matter what it says.

#: How far a predicted price may sit from its reference, as a multiple.
#:
#: WHY 100x AND NOT A TIGHTER BOUND: leveraged ETFs genuinely move by
#: several times their level in a session (SOXS and UVXY are designed to
#: do that), and a micro-cap that just announced a reverse split can move
#: 10x in a day - PARA itself traded 0.104 -> 0.164 -> 0.319 -> 2.72
#: inside three sessions in November 2026. A bound tighter than 100x
#: would reject those real moves. A bound of 100x still catches the
#: failures that matter, because a broken model is off by orders of
#: magnitude, not by a factor of three.
MAX_PREDICTION_REFERENCE_FACTOR = 100.0


def is_impossible_price(
    predicted_close: float | None,
    reference_close: float | None = None,
) -> bool:
    """True when a forecast's price cannot exist on an exchange.

    A price is impossible when it is negative, when it is not a finite
    number, when its reference price is not positive, or when it sits more
    than :data:`MAX_PREDICTION_REFERENCE_FACTOR` away from that reference.
    """
    if predicted_close is None:
        return True
    try:
        predicted = float(predicted_close)
    except (TypeError, ValueError):
        return True
    if predicted != predicted or predicted in (float("inf"), float("-inf")):
        return True
    if predicted <= 0:
        return True

    if reference_close is None:
        return False
    try:
        reference = float(reference_close)
    except (TypeError, ValueError):
        return True
    if reference <= 0:
        return True

    ratio = reference / predicted
    if ratio < 1.0:
        ratio = 1.0 / ratio
    return ratio > MAX_PREDICTION_REFERENCE_FACTOR


def describe_impossible_price(
    predicted_close: float | None,
    reference_close: float | None = None,
) -> str:
    """The reason a forecast was rejected, for a log or an error message."""
    return (
        f"The forecast price {predicted_close!r} is not a price an exchange "
        f"could print (reference {reference_close!r}). It is published by a "
        "model fitted on a history that mixes two price scales - see "
        "app/lakehouse/scale_repair.py. The forecast was rejected rather "
        "than clamped, because clamping would publish an invented price."
    )
