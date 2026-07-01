"""Provider-specific adapters that map payloads into canonical domain models."""

from .searchapi_mapper import (
    map_maps_response_to_discovered_places,
    map_reviews_response_to_review_histogram,
    map_reviews_response_to_review_records,
    map_sort_order_to_searchapi_value,
)
from .serpapi_mapper import (
    map_maps_response_to_discovered_places as map_serpapi_maps_response_to_discovered_places,
)
from .serpapi_mapper import (
    map_reviews_response_to_review_histogram as map_serpapi_reviews_response_to_review_histogram,
)
from .serpapi_mapper import (
    map_reviews_response_to_review_records as map_serpapi_reviews_response_to_review_records,
)
from .serpapi_mapper import map_sort_order_to_serpapi_value

__all__ = [
    "map_maps_response_to_discovered_places",
    "map_serpapi_maps_response_to_discovered_places",
    "map_reviews_response_to_review_histogram",
    "map_serpapi_reviews_response_to_review_histogram",
    "map_reviews_response_to_review_records",
    "map_serpapi_reviews_response_to_review_records",
    "map_sort_order_to_serpapi_value",
    "map_sort_order_to_searchapi_value",
]
