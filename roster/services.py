from decimal import Decimal


def calculate_net_worth(total_value: Decimal, guaranteed_ratio: Decimal, years: int) -> Decimal:
    """
    Calculate player net worth based on contract terms.

    Formula: net_worth = total_value * guaranteed_ratio * years
    (equivalent to guaranteed_amount * years where guaranteed_amount = total_value * guaranteed_ratio)
    """
    guaranteed_amount = total_value * guaranteed_ratio
    return guaranteed_amount * years
