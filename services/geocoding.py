import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


ZIP_API_URL = "https://api.zippopotam.us/us/{}"


class ZipLookupError(ValueError):
    pass


def lookup_us_zip(zip_code):
    normalized_zip = zip_code.strip()

    if not re.fullmatch(r"\d{5}", normalized_zip):
        raise ZipLookupError("Enter a valid 5-digit US ZIP code.")

    try:
        with urlopen(ZIP_API_URL.format(normalized_zip), timeout=15) as response:
            payload = json.load(response)
    except HTTPError as error:
        if error.code == 404:
            raise ZipLookupError("ZIP code was not found.") from error
        raise ZipLookupError("ZIP lookup service is unavailable.") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ZipLookupError("ZIP lookup service is unavailable.") from error

    try:
        place = payload["places"][0]
        return {
            "zip_code": payload["post code"],
            "place_name": place["place name"],
            "state": place["state"],
            "state_abbreviation": place["state abbreviation"],
            "latitude": float(place["latitude"]),
            "longitude": float(place["longitude"])
        }
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ZipLookupError("ZIP lookup returned an invalid response.") from error