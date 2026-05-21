"""
Utility functions for the FinanceFlow platform.
"""
import hashlib
from typing import Any
import json


def generate_cache_key(*args, **kwargs) -> str:
    """
    Generate a cache key from arguments.
    
    Args:
        *args: Positional arguments
        **kwargs: Keyword arguments
        
    Returns:
        Cache key
    """
    combined = str(args) + json.dumps(kwargs, sort_keys=True)
    return hashlib.md5(combined.encode()).hexdigest()


def format_currency(value: float) -> str:
    """Format value as currency."""
    return f"${value:,.2f}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """Format value as percentage."""
    return f"{value:.{decimals}f}%"


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to max length."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix
