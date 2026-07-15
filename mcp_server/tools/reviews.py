"""MCP tool wrappers for CompanyReviewService.

All tools are thin pass-throughs - no HTTP, SQL, or business logic lives here.
The CompanyReviewService (injected via bootstrap) owns all of that.

## Tool selection guide

- To research a company: start with `get_company_overview` (one call, full picture).
- To target a specific location: use `search_company_places` to get data_ids, then
  `get_place_reviews` for each location you care about.
- Use `_raw` variants when downstream code needs structured JSON (e.g. for further
  processing or display). Use plain variants when producing a human-readable summary.

## When to use these tools

Google Maps reviews are meaningful for companies with customer-facing physical
locations - medical and dental practices, clinics, pharmacies, restaurants, retail
stores, gyms, hotels. Customers visit these places directly and their reviews
reflect the quality of that experience.

Do NOT use these tools to assess customer sentiment for companies whose Maps
listings are head offices, warehouses, or data centres - such as insurance
companies, software vendors, or online retailers. Reviews on those listings are
sparse, off-topic, or left by delivery drivers, and do not represent how
customers feel about the company's actual services.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastmcp import FastMCP
from google_reviews.services.bootstrap import create_review_service_from_settings
from google_reviews.services.company_review_service import CompanyReviewService
from pydantic import Field

logger = logging.getLogger(__name__)


def register(mcp: FastMCP) -> CompanyReviewService:
    """Register all google_reviews tools on the given FastMCP instance.

    Called once at server startup. Creates the CompanyReviewService eagerly so
    misconfigured env vars fail fast before any requests are accepted.

    Returns the service so the caller can register a shutdown hook.
    """
    service = create_review_service_from_settings()
    logger.info("CompanyReviewService initialised")

    @mcp.tool()
    def search_company_places(
        company_url: Annotated[
            str,
            Field(
                description=(
                    "The company's website URL or bare domain (e.g. 'acme.com', 'https://acme.com', "
                    "or 'www.acme.com'). The service normalises it, so any form works. "
                    "Used to match Google Maps listings by website domain."
                ),
                max_length=2048,
            ),
        ],
        company_name: Annotated[
            str | None,
            Field(
                description=(
                    "Optional display name of the company (e.g. 'Acme Corp'). "
                    "Provide this when the URL alone is unlikely to return results - "
                    "the service tries the domain first, then company_name, then the bare "
                    "domain prefix as fallback strategies."
                ),
                max_length=256,
            ),
        ] = None,
    ) -> str:
        """Discover Google Maps place listings for a company by its website URL.

        Returns a markdown list of matching locations, each with a place_id, data_id,
        name, address, rating, and review count. Results are cached - repeat calls for
        the same URL return instantly without hitting the API.

        **No pagination**: place discovery is a single API call. Matching locations from
        that provider response are returned; there is no way to page through more results.

        **Workflow**: Call this first to find data_id values. Pass those to
        get_place_reviews to fetch the actual reviews for a specific location.

        Use get_company_overview instead for a bounded multi-location sample in one call.

        **When to use**: Only useful for companies with customer-facing physical locations
        (medical practices, clinics, restaurants, retail stores, gyms, hotels) where
        Google Maps reviews reflect real customer experiences. Not appropriate for
        companies like insurers, software vendors, or online retailers - their Maps
        listings are typically offices, not places customers visit, and the reviews there
        do not represent sentiment about the company's services.

        If zero locations are returned, the most likely cause is that the Google Maps
        listings for this company do not have a matching website domain linked. Retry
        with company_name set to the business name as a fallback.
        """
        logger.info("tool=search_company_places company_url=%s", company_url)
        return service.search_company_places(company_url=company_url, company_name=company_name)

    @mcp.tool()
    def search_company_places_raw(
        company_url: Annotated[
            str,
            Field(
                description=(
                    "The company's website URL or bare domain (e.g. 'acme.com', 'https://acme.com', "
                    "or 'www.acme.com'). The service normalises it, so any form works. "
                    "Used to match Google Maps listings by website domain."
                ),
                max_length=2048,
            ),
        ],
        company_name: Annotated[
            str | None,
            Field(
                description=(
                    "Optional display name of the company (e.g. 'Acme Corp'). "
                    "Provide this when the URL alone is unlikely to return results - "
                    "the service tries the domain first, then company_name, then the bare "
                    "domain prefix as fallback strategies."
                ),
                max_length=256,
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Discover Google Maps place listings for a company by its website URL.

        Same as search_company_places but returns structured JSON containing the raw
        provider payload for each place, suitable for programmatic processing.

        Returns: `{ "places": [ <provider raw payload per place>, ... ] }`
        """
        logger.info("tool=search_company_places_raw company_url=%s", company_url)
        return service.search_company_places_raw(company_url=company_url, company_name=company_name)

    @mcp.tool()
    def get_place_reviews(
        data_id: Annotated[
            str,
            Field(
                description=(
                    "The data_id of the specific Google Maps location to fetch reviews for. "
                    "Obtain this from the output of search_company_places or get_company_overview. "
                    "Looks like '0x549e1dfebd5a1c2f:0x90bdad3bc8b0c500'."
                ),
                max_length=256,
            ),
        ],
        num_reviews: Annotated[
            int,
            Field(
                description=(
                    "Number of reviews to fetch. Default 20. "
                    "Reviews are assembled in pages: the first page contains 8 reviews, then "
                    "additional pages of 20 each. Efficient breakpoints are 8, 28, and 48 - "
                    "requesting 20 costs the same number of API calls as requesting 28 (both "
                    "require 2 calls: the initial 8 + one page of 20). "
                    "If enough reviews are already cached, returns instantly with no API call."
                ),
                ge=1,
            ),
        ] = 20,
        sort_order: Annotated[
            str | None,
            Field(
                description=(
                    "Order in which to retrieve reviews. "
                    "Options: 'most_relevant' (default), 'newest', 'best', 'worst'."
                )
            ),
        ] = None,
    ) -> str:
        """Fetch reviews for a single Google Maps location by its data_id.

        The place must have been discovered first via search_company_places or
        get_company_overview. Reviews are cached per sort order - repeat calls with the
        same arguments return instantly without an API call.

        Returns markdown with place metadata, the review list, and the rating
        histogram when the provider supplies one (often absent with SerpAPI).
        """
        logger.info("tool=get_place_reviews data_id=%s sort_order=%s num_reviews=%s", data_id, sort_order, num_reviews)
        return service.get_place_reviews(data_id=data_id, num_reviews=num_reviews, sort_order=sort_order)

    @mcp.tool()
    def get_place_reviews_raw(
        data_id: Annotated[
            str,
            Field(
                description=(
                    "The data_id of the specific Google Maps location to fetch reviews for. "
                    "Obtain this from the output of search_company_places or get_company_overview. "
                    "Looks like '0x549e1dfebd5a1c2f:0x90bdad3bc8b0c500'."
                ),
                max_length=256,
            ),
        ],
        num_reviews: Annotated[
            int,
            Field(
                description=(
                    "Number of reviews to fetch. Default 20. "
                    "Reviews are assembled in pages: the first page contains 8 reviews, then "
                    "additional pages of 20 each. Efficient breakpoints are 8, 28, and 48 - "
                    "requesting 20 costs the same number of API calls as requesting 28 (both "
                    "require 2 calls: the initial 8 + one page of 20). "
                    "If enough reviews are already cached, returns instantly with no API call."
                ),
                ge=1,
            ),
        ] = 20,
        sort_order: Annotated[
            str | None,
            Field(
                description=(
                    "Order in which to retrieve reviews. "
                    "Options: 'most_relevant' (default), 'newest', 'best', 'worst'."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Fetch reviews for a single Google Maps location by its data_id.

        Same as get_place_reviews but returns structured JSON with the full place
        metadata, review list, and histogram (if available).

        Returns: `{ "place": {...}, "reviews": [...], "histogram": {...} }`
        """
        logger.info(
            "tool=get_place_reviews_raw data_id=%s sort_order=%s num_reviews=%s", data_id, sort_order, num_reviews
        )
        return service.get_place_reviews_raw(data_id=data_id, num_reviews=num_reviews, sort_order=sort_order)

    @mcp.tool()
    def get_company_overview(
        company_url: Annotated[
            str,
            Field(
                description=(
                    "The company's website URL or bare domain (e.g. 'acme.com', 'https://acme.com', "
                    "or 'www.acme.com'). The service normalises it, so any form works."
                ),
                max_length=2048,
            ),
        ],
        company_name: Annotated[
            str | None,
            Field(
                description=(
                    "Optional display name of the company (e.g. 'Acme Corp'). "
                    "Provide this when the URL alone is unlikely to return results."
                ),
                max_length=256,
            ),
        ] = None,
        max_companies: Annotated[
            int,
            Field(
                description=(
                    "Maximum number of Google Maps locations to include in the overview. "
                    "Default 3. Useful when a brand has many locations and you only need a sample."
                ),
                ge=1,
            ),
        ] = 3,
        max_reviews_per_sort: Annotated[
            int,
            Field(
                description=(
                    "Maximum reviews to fetch per sort order (best, worst, newest, most_relevant) "
                    "per location. Default 20, capped at 48. "
                    "Reviews are assembled in pages: the first page contains 8 reviews, then pages "
                    "of 20 each. Efficient breakpoints are 8, 28, and 48 - requesting 20 costs the "
                    "same API calls as 28. A value of 27 is recommended for balanced coverage: "
                    "it fits within 2 API calls per sort order and gives good representation without "
                    "excessive cost. "
                    "For locations whose total review count is less than 4× this value, all reviews "
                    "are fetched in a single call instead of four separate sort-order calls."
                ),
                ge=1,
            ),
        ] = 20,
    ) -> str:
        """Google Maps review overview for a bounded number of company locations.

        Discovers matching Google Maps locations, then fetches reviews for up to
        max_companies locations across all sort orders (best, worst, newest,
        most_relevant) and the
        rating histogram when the provider supplies one (often absent with SerpAPI).
        For locations with few total reviews, all reviews are fetched
        in one call rather than repeating across sort orders. Locations beyond
        max_companies are listed at the end without reviews fetched.

        **Use this when you want a complete picture in one call.** For targeted fetching
        of a specific location, use search_company_places + get_place_reviews instead.

        **When to use**: Best suited for companies with multiple customer-facing physical
        locations (medical or dental groups, clinic chains, restaurant chains, retail
        stores) where aggregating reviews across locations gives a meaningful picture of
        service quality. Not appropriate for companies like insurers, software vendors,
        or online retailers - their Maps listings are offices or warehouses, and reviews
        there do not reflect customer sentiment about the company's actual services.

        If a company URL returns zero locations, the most likely cause is that the
        Google Maps listings for that company do not have a matching website domain linked.
        In that case, retry with the company_name parameter set to the business name.

        Returns markdown with one section per location.
        """
        logger.info("tool=get_company_overview company_url=%s", company_url)
        return service.get_company_overview(
            company_url=company_url,
            company_name=company_name,
            max_companies=max_companies,
            max_reviews_per_sort=max_reviews_per_sort,
        )

    @mcp.tool()
    def get_company_overview_raw(
        company_url: Annotated[
            str,
            Field(
                description=(
                    "The company's website URL or bare domain (e.g. 'acme.com', 'https://acme.com', "
                    "or 'www.acme.com'). The service normalises it, so any form works."
                ),
                max_length=2048,
            ),
        ],
        company_name: Annotated[
            str | None,
            Field(
                description=(
                    "Optional display name of the company (e.g. 'Acme Corp'). "
                    "Provide this when the URL alone is unlikely to return results."
                ),
                max_length=256,
            ),
        ] = None,
        max_companies: Annotated[
            int,
            Field(
                description=(
                    "Maximum number of Google Maps locations to include in the overview. "
                    "Default 3. Useful when a brand has many locations and you only need a sample."
                ),
                ge=1,
            ),
        ] = 3,
        max_reviews_per_sort: Annotated[
            int,
            Field(
                description=(
                    "Maximum reviews to fetch per sort order (best, worst, newest, most_relevant) "
                    "per location. Default 20, capped at 48. "
                    "Reviews are assembled in pages: the first page contains 8 reviews, then pages "
                    "of 20 each. Efficient breakpoints are 8, 28, and 48 - requesting 20 costs the "
                    "same API calls as 28. A value of 27 is recommended for balanced coverage: "
                    "it fits within 2 API calls per sort order and gives good representation without "
                    "excessive cost. "
                    "For locations whose total review count is less than 4× this value, all reviews "
                    "are fetched in a single call instead of four separate sort-order calls."
                ),
                ge=1,
            ),
        ] = 20,
    ) -> dict[str, Any]:
        """Full Google Maps review overview for a company across all its locations.

        Same as get_company_overview but returns structured JSON, suitable for
        programmatic processing or display pipelines.

        If a company URL returns zero locations, the most likely cause is that the
        Google Maps listings for that company do not have a matching website domain linked.
        In that case, retry with the company_name parameter set to the business name.

        Returns:
        ```
        {
          "company_website_url": "...",
          "normalized_website_domain": "...",
          "locations": [
            {
              "place": { <place metadata> },
              "reviews": { "all": [...] }          // few reviews: single bucket
                       or { "best": [...], ... }   // many reviews: per sort order
              "histogram": { <star counts> }        // if available
            }
          ],
          "additional_locations": [ <place raw_payload>, ... ]  // discovered but not fetched (beyond max_companies)
        }
        ```
        """
        logger.info("tool=get_company_overview_raw company_url=%s", company_url)
        return service.get_company_overview_raw(
            company_url=company_url,
            company_name=company_name,
            max_companies=max_companies,
            max_reviews_per_sort=max_reviews_per_sort,
        )

    return service
