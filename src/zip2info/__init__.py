from dataclasses import dataclass
from typing import Optional

from zip2info._data import TIMEZONES, ZIP_INFO


@dataclass(frozen=True, slots=True)
class ZipInfo:
    """Metadata for a US ZIP code."""

    zipcode: int
    timezone: str
    latitude: float
    longitude: float


def _normalize_zipcode(zipcode: str | int) -> Optional[int]:
    try:
        return int(zipcode)
    except (ValueError, TypeError):
        return None


def timezone(zipcode: str | int) -> Optional[str]:
    """
    Return the IANA timezone for a US ZIP code.

    Args:
        zipcode: ZIP code as a string or integer.

    Returns:
        Timezone string (for example, ``America/New_York``) or ``None``.
    """
    zip_int = _normalize_zipcode(zipcode)
    if zip_int is None:
        return None

    record = ZIP_INFO.get(zip_int)
    if record is None:
        return None
    tz_idx, _, _ = record
    return TIMEZONES[tz_idx]


def coordinates(zipcode: str | int) -> Optional[tuple[float, float]]:
    """
    Return centroid latitude and longitude for a US ZIP code.

    Coordinates come from the generated ZIP metadata dataset.

    Args:
        zipcode: ZIP code as a string or integer.

    Returns:
        ``(latitude, longitude)`` or ``None``.
    """
    zip_int = _normalize_zipcode(zipcode)
    if zip_int is None:
        return None

    record = ZIP_INFO.get(zip_int)
    if record is None:
        return None
    _, latitude, longitude = record
    return latitude, longitude


def info(zipcode: str | int) -> Optional[ZipInfo]:
    """
    Return timezone and coordinate metadata for a US ZIP code.

    Args:
        zipcode: ZIP code as a string or integer.

    Returns:
        ``ZipInfo`` when timezone data exists, otherwise ``None``.
    """
    zip_int = _normalize_zipcode(zipcode)
    if zip_int is None:
        return None

    record = ZIP_INFO.get(zip_int)
    if record is None:
        return None

    tz_idx, latitude, longitude = record
    return ZipInfo(
        zipcode=zip_int,
        timezone=TIMEZONES[tz_idx],
        latitude=latitude,
        longitude=longitude,
    )


__all__ = ["ZipInfo", "coordinates", "info", "timezone"]
