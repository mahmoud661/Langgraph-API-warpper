"""Model domain logic."""

from .model_binding import get_bound_model
from .output_handler import handle_model_output

__all__ = [
    "get_bound_model",
    "handle_model_output",
]
