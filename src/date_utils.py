"""Format-rule requirement: 'Date format: ordinal day + month + year —
5th day of September 2026.' Case data supplies plain dates like
'5 September 2026'; this converts them to the required form."""
from __future__ import annotations
import re


def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def to_ordinal_date(date_str: str) -> str:
    """'5 September 2026' -> '5th day of September 2026'.
    Already-formatted strings ('5th day of September 2026') pass through unchanged."""
    if re.search(r"\d(st|nd|rd|th) day of", date_str):
        return date_str
    m = re.match(r"^\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s*$", date_str.strip())
    if not m:
        return date_str  # unrecognised format: leave as-is rather than guess
    day, month, year = int(m.group(1)), m.group(2), m.group(3)
    return f"{_ordinal(day)} day of {month} {year}"
