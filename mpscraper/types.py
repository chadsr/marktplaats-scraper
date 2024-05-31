from dataclasses import dataclass


@dataclass
class ListingDetails:
    """Marktplaats Listing Details, scraped from the listing description."""

    description: str
    ad_type: str
    types: set[str]
    services: set[str]
    price_type: str
    price_cents: int
    view_count: int
    favorited_count: int
    listed_timestamp: str


@dataclass
class Listing:
    """Marktplaats Listing."""

    item_id: str
    seller_id: str
    parent_category_id: int
    child_category_id: int
    category_verticals: tuple[str, ...]
    ad_type: str
    title: str
    description: str
    price_type: str
    price_cents: int
    types: tuple[str, ...]
    services: tuple[str, ...]
    listing_url: str
    image_urls: tuple[str, ...]
    city_name: str
    country_code: str
    listed_timestamp: str
    crawled_timestamp: str
    view_count: int
    favorited_count: int
