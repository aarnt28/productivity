from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)


class AddressServiceNotConfigured(Exception):
    """Raised when address autocomplete credentials are missing."""


def _ensure_configured() -> None:
    if not settings.GEOAPIFY_API_KEY:
        raise AddressServiceNotConfigured("Address autocomplete is not configured")


def _extract_coordinates(
    feature: Dict[str, Any], properties: Dict[str, Any]
) -> Tuple[Optional[float], Optional[float]]:
    lat = properties.get("lat")
    lon = properties.get("lon")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return float(lat), float(lon)

    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates")
    if isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
        lon_val, lat_val = coordinates[0], coordinates[1]
        try:
            return float(lat_val), float(lon_val)
        except (TypeError, ValueError):
            return None, None
    return None, None


def _map_suggestion(feature: Dict[str, Any]) -> Dict[str, Any]:
    properties = feature.get("properties") or {}
    lat, lon = _extract_coordinates(feature, properties)

    suggestion = {
        "street_line": properties.get("address_line1") or properties.get("street") or properties.get("formatted"),
        "secondary": properties.get("address_line2") or "",
        "city": properties.get("city"),
        "state": properties.get("state_code") or properties.get("state"),
        "postal_code": properties.get("postcode"),
        "country": properties.get("country"),
        "formatted": properties.get("formatted"),
        "place_id": properties.get("place_id"),
        "result_type": properties.get("result_type"),
        "confidence": (properties.get("rank") or {}).get("confidence"),
        "lat": lat,
        "lon": lon,
    }
    return suggestion


def _build_last_line(properties: Dict[str, Any]) -> str:
    city = properties.get("city")
    state = properties.get("state_code") or properties.get("state")
    postal_code = properties.get("postcode")

    parts: List[str] = []
    if city and state:
        parts.append(f"{city}, {state}")
    else:
        if city:
            parts.append(str(city))
        if state:
            parts.append(str(state))
    if postal_code:
        parts.append(str(postal_code))

    if parts:
        return " ".join(parts)
    return properties.get("formatted") or ""


def _map_verified_address(feature: Dict[str, Any]) -> Dict[str, Any]:
    properties = feature.get("properties") or {}
    lat, lon = _extract_coordinates(feature, properties)

    verified = {
        "delivery_line_1": properties.get("address_line1")
        or properties.get("street")
        or properties.get("formatted"),
        "delivery_line_2": properties.get("address_line2") or "",
        "last_line": _build_last_line(properties),
        "city": properties.get("city"),
        "state": properties.get("state_code") or properties.get("state"),
        "postal_code": properties.get("postcode"),
        "country": properties.get("country"),
        "county": properties.get("county"),
        "dpv_match_code": None,
        "footnotes": None,
        "latitude": lat,
        "longitude": lon,
        "place_id": properties.get("place_id"),
        "confidence": (properties.get("rank") or {}).get("confidence"),
    }
    return verified


def _raise_for_status(response: httpx.Response, context: str) -> None:
    if response.status_code in {401, 403}:
        logger.warning("Geoapify authentication failed for %s", context)
    elif response.status_code >= 500:
        logger.error("Geoapify service error %s during %s", response.status_code, context)
    elif response.status_code >= 400:
        logger.error("Geoapify request error %s during %s", response.status_code, context)
    response.raise_for_status()


async def fetch_autocomplete_suggestions(
    search: str,
    *,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    """Return address suggestions using the Geoapify autocomplete endpoint."""

    _ensure_configured()

    if not search or not search.strip():
        return []

    params: Dict[str, Any] = {
        "text": search.strip(),
        "apiKey": settings.GEOAPIFY_API_KEY,
        "limit": max_results,
        "type": "street",
    }

    filters: List[str] = []
    if city and city.strip():
        filters.append(f"city:{city.strip()}")
    if state and state.strip():
        cleaned_state = state.strip()
        if len(cleaned_state) == 2:
            filters.append(f"statecode:{cleaned_state}")
        else:
            filters.append(f"state:{cleaned_state}")
    if postal_code and postal_code.strip():
        filters.append(f"postcode:{postal_code.strip()}")
    if filters:
        params["filter"] = "|".join(filters)

    timeout = httpx.Timeout(6.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(settings.GEOAPIFY_AUTOCOMPLETE_URL, params=params)

    _raise_for_status(response, "address autocomplete")

    data = response.json()
    suggestions: List[Dict[str, Any]] = []
    for feature in data.get("features", []):
        suggestions.append(_map_suggestion(feature))

    return suggestions


async def verify_postal_address(
    *,
    street_line: str,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
    secondary: Optional[str] = None,
    place_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Verify a selected address via Geoapify geocoding APIs."""

    _ensure_configured()

    if not street_line or not street_line.strip():
        return None

    timeout = httpx.Timeout(6.0)
    base_params: Dict[str, Any] = {
        "apiKey": settings.GEOAPIFY_API_KEY,
        "limit": 1,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        if place_id:
            params = {**base_params, "place_id": place_id}
            response = await client.get(settings.GEOAPIFY_PLACE_URL, params=params)
            if response.status_code == 404:
                logger.info(
                    "Geoapify place %s not found during address verification", place_id
                )
                return None
        else:
            street_parts = [street_line.strip()]
            if secondary and secondary.strip():
                street_parts.append(secondary.strip())

            locality_parts = []
            if city and city.strip():
                locality_parts.append(city.strip())
            if state and state.strip():
                locality_parts.append(state.strip())
            if postal_code and postal_code.strip():
                locality_parts.append(postal_code.strip())

            text_query = ", ".join(
                part for part in [" ".join(street_parts).strip(), " ".join(locality_parts).strip()]
                if part
            )
            params = {**base_params, "text": text_query or street_line.strip()}
            response = await client.get(settings.GEOAPIFY_GEOCODE_URL, params=params)
            if response.status_code == 404:
                logger.info(
                    "Geoapify returned 404 for address verification query '%s'",
                    text_query,
                )
                return None

    _raise_for_status(response, "address verification")

    data = response.json()
    features = data.get("features") or []
    if not features:
        return None

    return _map_verified_address(features[0])
