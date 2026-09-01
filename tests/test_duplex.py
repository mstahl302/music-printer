"""Page-planning is pure — pin it to the spec tables exactly."""

import random

import pytest

from musicprinter.duplex import plan_passes, plan_set

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


# ---- plan_set: an ordered list of documents ----------------------

SET_CASES = {
    # effective lengths -> (padded, total, single_pass, sheets_per_pass)
    (1,): ((1,), 1, True, 1),
    (3,): ((3,), 3, False, 2),
    (4,): ((4,), 4, False, 2),
    (3, 4, 5): ((4, 4, 5), 13, False, 7),   # the spec §4 worked example
    (3, 3): ((4, 3), 7, False, 4),
    (6, 6): ((6, 6), 12, False, 6),
    (2, 2, 2): ((2, 2, 2), 6, False, 3),
}


@pytest.mark.parametrize("lens,expected", SET_CASES.items())
def test_plan_set(lens, expected):
    padded, total, single, sheets = expected
    layout = plan_set(list(lens))
    assert layout.padded_lengths == padded
    assert layout.total == total
    assert layout.single_pass is single
    assert layout.sheets_per_pass == sheets


def test_plan_set_of_one_matches_plan_passes():
    for n in range(1, 9):
        assert plan_set([n]).passes == plan_passes(n)


def test_plan_set_worked_example_refs():
    layout = plan_set([3, 4, 5])
    assert layout.even_refs() == [(0, 2), (0, None), (1, 2), (1, 4),
                                  (2, 2), (2, 4), (2, None)]
    assert layout.odd_refs() == [(0, 1), (0, 3), (1, 1), (1, 3),
                                 (2, 1), (2, 3), (2, 5)]


def test_plan_set_every_file_starts_on_a_front():
    for _ in range(20):
        lens = [random.randint(1, 9) for _ in range(random.randint(1, 6))]
        for start in plan_set(lens).starts:
            assert start % 2 == 1


def test_plan_set_rejects_empty():
    with pytest.raises(ValueError):
        plan_set([])
