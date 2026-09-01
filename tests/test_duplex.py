"""Page-planning is pure — pin it to the spec §7.2 table exactly."""

import pytest

from musicprinter.duplex import plan_passes

# N -> (even_pages, odd_pages, pad_blank, single_pass, sheets_per_pass)
CASES = {
    0: ((), (), False, True, 0),
    1: ((), (1,), False, True, 1),
    2: ((2,), (1,), False, False, 1),
    3: ((2,), (1, 3), True, False, 2),
    4: ((2, 4), (1, 3), False, False, 2),
    5: ((2, 4), (1, 3, 5), True, False, 3),
    6: ((2, 4, 6), (1, 3, 5), False, False, 3),
    7: ((2, 4, 6), (1, 3, 5, 7), True, False, 4),
    8: ((2, 4, 6, 8), (1, 3, 5, 7), False, False, 4),
}


@pytest.mark.parametrize("n,expected", CASES.items())
def test_plan_passes(n, expected):
    even, odd, pad, single, sheets = expected
    plan = plan_passes(n)
    assert plan.even_pages == even
    assert plan.odd_pages == odd
    assert plan.pad_blank is pad
    assert plan.single_pass is single
    assert plan.sheets_per_pass == sheets


def test_negative_rejected():
    with pytest.raises(ValueError):
        plan_passes(-1)


def test_odd_makes_pass_sheet_counts_equal():
    for n in (3, 5, 7, 9, 11):
        plan = plan_passes(n)
        assert len(plan.even_pages) + 1 == len(plan.odd_pages) == plan.sheets_per_pass
