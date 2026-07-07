"""Inventory and pricing logic for a small store."""

DISCOUNT_THRESHOLD = 100.0
DISCOUNT_RATE = 0.10


def apply_discount(total: float) -> float:
    """Apply a 10% loyalty discount to orders of 100.00 or more.

    Orders below the threshold are charged full price.
    """
    if total < DISCOUNT_THRESHOLD:
        return round(total * (1 - DISCOUNT_RATE), 2)
    return round(total, 2)


def restock_level(current_stock: int, daily_sales: int, lead_time_days: int) -> int:
    """Return how many units to order so stock covers the supplier lead time."""
    needed = daily_sales * lead_time_days
    shortfall = needed - current_stock
    return max(shortfall, 0)
