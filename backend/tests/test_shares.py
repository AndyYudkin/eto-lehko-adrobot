import pytest

from app.shares import ShareItem, push_block_reason, recalc_shares


def _items(*specs):
    """specs: (offer_id, share, pinned); position = index in the list."""
    return [
        ShareItem(oid, share, pinned, i) for i, (oid, share, pinned) in enumerate(specs)
    ]


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([], {}),
        (_items((1, 0, False), (2, 0, False), (3, 0, False)), {1: 34, 2: 33, 3: 33}),
        (_items(*[(i, 0, False) for i in range(1, 5)]), {i: 25 for i in range(1, 5)}),
        (
            _items(*[(i, 0, False) for i in range(1, 8)]),
            dict(zip(range(1, 8), [15, 15, 14, 14, 14, 14, 14], strict=True)),
        ),
        (
            _items((1, 0, False), (2, 33, True), (3, 0, False), (4, 0, False)),
            {1: 23, 2: 33, 3: 22, 4: 22},
        ),
        (
            _items((1, 60, True), (2, 40, True), (3, 5, False)),
            {1: 60, 2: 40, 3: 0},
        ),
        (_items((1, 40, True)), {1: 40}),
        (
            [
                ShareItem(3, 0, False, 2),
                ShareItem(1, 0, False, 0),
                ShareItem(2, 0, False, 1),
            ],
            {1: 34, 2: 33, 3: 33},
        ),
    ],
)
def test_recalc(items, expected):
    assert recalc_shares(items) == expected


@pytest.mark.parametrize(
    ("shares", "expected"),
    [
        ([], "no_offers"),
        ([40], "sum_not_100"),
        ([50, 51], "sum_not_100"),
        ([50, 50], None),
        ([100, 0], None),
    ],
)
def test_push_block_reason(shares, expected):
    assert push_block_reason(shares) == expected
