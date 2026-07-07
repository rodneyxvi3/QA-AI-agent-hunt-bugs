"""Simple calculator utilities for order processing."""


def sum_up_to(n: int) -> int:
    """Return the sum of all integers from 1 to n, inclusive.

    Example: sum_up_to(3) should return 1 + 2 + 3 = 6.
    """
    return sum(range(1, n))


def average(numbers: list) -> float:
    """Return the arithmetic mean of a non-empty list of numbers."""
    if not numbers:
        raise ValueError("average() requires at least one number")
    return sum(numbers) / len(numbers)


def percent_change(old: float, new: float) -> float:
    """Return the percentage change from old to new."""
    if old == 0:
        raise ValueError("old value must be non-zero")
    return (new - old) / old * 100
