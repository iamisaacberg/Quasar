"""Allowlisted archived NEXRAD mosaic tiles for the Okaloosa replay."""
from functools import lru_cache
import re
from urllib.error import URLError
from urllib.request import Request, urlopen


START = "202610090500"
END = "202610100500"
TILE_RE = re.compile(r"^(\d{12})/(\d{1,2})/(\d{1,5})/(\d{1,5})\.png$")
MAX_TILE_BYTES = 2_000_000
BASE_URL = "https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/ridge::USCOMP-N0Q-{at}/{z}/{x}/{y}.png"


def _validate(at, zoom, x, y):
    if not re.fullmatch(r"\d{12}", at) or not (START <= at <= END):
        raise ValueError("Radar time must be within the October 9 replay")
    minute = int(at[-2:])
    if minute % 5 or int(at[8:10]) > 23 or int(at[10:12]) > 55:
        raise ValueError("Radar time must be a five-minute UTC mosaic time")
    if not (4 <= zoom <= 12) or not (0 <= x < 2**zoom) or not (0 <= y < 2**zoom):
        raise ValueError("Radar tile coordinates are outside supported bounds")


@lru_cache(maxsize=64)
def _fetch(at, zoom, x, y):
    request = Request(BASE_URL.format(at=at, z=zoom, x=x, y=y), headers={
        "User-Agent": "Quasar historical radar viewer/1.0",
        "Accept": "image/png",
    })
    with urlopen(request, timeout=12) as response:
        if response.status != 200 or "image/png" not in response.headers.get("Content-Type", ""):
            raise URLError("Radar archive returned a non-image response")
        body = response.read(MAX_TILE_BYTES + 1)
    if len(body) > MAX_TILE_BYTES or not body.startswith(b"\x89PNG\r\n\x1a\n"):
        raise URLError("Radar archive returned an invalid image")
    return body


def fetch_tile(path):
    match = TILE_RE.fullmatch(path)
    if not match:
        raise ValueError("Invalid radar tile path")
    at, zoom, x, y = match.groups()
    values = tuple(map(int, (zoom, x, y)))
    _validate(at, *values)
    try:
        return _fetch(at, *values)
    except Exception as exc:
        raise RuntimeError("Archived NEXRAD tile is unavailable") from exc
