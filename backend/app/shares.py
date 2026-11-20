from dataclasses import dataclass


@dataclass
class ShareItem:
    offer_id: int
    share: int
    pinned: bool
    position: int


def recalc_shares(items: list[ShareItem]) -> dict[int, int]:
    """New share per active offer: pinned keep theirs, the rest split the
    remainder evenly, the leftover going to the first ones by position."""
    result = {i.offer_id: i.share for i in items if i.pinned}
    free = sorted((i for i in items if not i.pinned), key=lambda i: i.position)
    if free:
        remainder = max(0, 100 - sum(result.values()))
        base, extra = divmod(remainder, len(free))
        for idx, item in enumerate(free):
            result[item.offer_id] = base + (1 if idx < extra else 0)
    return result


def push_block_reason(shares: list[int]) -> str | None:
    """Why a stream can't be pushed, given its active offers' shares."""
    if not shares:
        return "no_offers"
    if sum(shares) != 100:
        return "sum_not_100"
    return None
