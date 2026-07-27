"""Natural (numeric-segment) sort for dotted NICE section numbers.

Mirrors the frontend's naturalSortCompare
(services/ui/src/app/admin/guidance/naturalSort.ts) test coverage so
both sides of the reviewer-facing sort fix (Phase C) are verified.
"""

from __future__ import annotations

import sys
from pathlib import Path

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.services.natural_sort import natural_sort_key


def test_orders_dotted_section_numbers_numerically_not_lexicographically() -> None:
    ids = ["1.11.1", "1.2.1", "1.2.10", "1.2.2"]
    assert sorted(ids, key=natural_sort_key) == ["1.2.1", "1.2.2", "1.2.10", "1.11.1"]


def test_puts_1_2_1_before_1_11_1() -> None:
    assert natural_sort_key("1.2.1") < natural_sort_key("1.11.1")


def test_puts_1_9_before_1_10() -> None:
    assert natural_sort_key("1.9") < natural_sort_key("1.10")


def test_equal_ids_compare_equal() -> None:
    assert natural_sort_key("1.2.1") == natural_sort_key("1.2.1")


def test_handles_none_and_empty_without_raising() -> None:
    assert natural_sort_key(None) is not None
    assert natural_sort_key("") is not None


def test_mixed_numeric_and_non_numeric_ids_do_not_raise() -> None:
    ids = ["1.2.1", "not-a-number", "2.1"]
    sorted(ids, key=natural_sort_key)  # must not raise TypeError
