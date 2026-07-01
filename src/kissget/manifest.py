"""Read a JSON manifest produced by the browser URL collector.

The manifest contains pre-captured stream URLs and subtitle URLs for
each episode, eliminating the need for kkey authentication at download time.

Expected format::

    {
      "drama": "Customized-Lover-(2026)",
      "episodes": [
        {
          "number": 1,
          "stream_url": "http://cdn.../index.m3u8?v=...",
          "subtitles": [
            { "lang": "en", "label": "English", "src": "https://..." }
          ]
        }
      ]
    }
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from kissget.models.sub import SubItem

logger = logging.getLogger(__name__)

# Known collector sites → the Referer the downloader should send for their CDN.
# A manifest may instead carry an explicit "referer"; that always wins.
_SITE_REFERERS = {
    "kisskh": "https://kisskh.nl/",
    "asiaflix": "https://asiaflix.net/",
}


def _referer_for_site(site: str | None) -> str | None:
    """Map an optional manifest "site" hint to a Referer, or None if unknown."""
    if not site:
        return None
    return _SITE_REFERERS.get(site.strip().lower())


class ManifestEpisode:
    """A single episode entry from the manifest."""

    __slots__ = ("number", "stream_url", "subtitles")

    def __init__(self, number: int | float, stream_url: str | None, subtitles: list[SubItem]) -> None:
        self.number = number
        self.stream_url = stream_url
        self.subtitles = subtitles


class ManifestReader:
    """Parse a collector manifest and provide episode data.

    Usage::

        manifest = ManifestReader.from_file("manifest.json")
        for ep in manifest.episodes:
            print(ep.number, ep.stream_url)
    """

    def __init__(
        self,
        drama_name: str,
        episodes: list[ManifestEpisode],
        referer: str | None = None,
    ) -> None:
        self.drama_name = drama_name
        self.episodes = episodes
        # Optional per-site Referer for the downloader (e.g. AsiaFlix CDN needs an
        # asiaflix Referer). None → caller falls back to the default base URL.
        self.referer = referer

    @classmethod
    def from_file(cls, path: str | Path) -> ManifestReader:
        """Load a manifest from a JSON file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Manifest file not found: {path}")

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        drama_name: str = data.get("drama", "Unknown")
        # Explicit "referer" wins; otherwise derive from an optional "site" hint.
        referer: str | None = data.get("referer") or _referer_for_site(data.get("site"))
        episodes: list[ManifestEpisode] = []

        for ep_data in data.get("episodes", []):
            subs = [
                SubItem(
                    src=s.get("src", ""),
                    label=s.get("label", ""),
                    land=s.get("lang", ""),
                    default=False,
                )
                for s in ep_data.get("subtitles", [])
            ]
            episodes.append(
                ManifestEpisode(
                    number=ep_data.get("number", 0),
                    stream_url=ep_data.get("stream_url"),
                    subtitles=subs,
                )
            )

        # Sort by episode number
        episodes.sort(key=lambda e: e.number)
        logger.info(
            "Loaded manifest: %s — %d episode(s), %d with streams, %d with subs",
            drama_name,
            len(episodes),
            sum(1 for e in episodes if e.stream_url),
            sum(1 for e in episodes if e.subtitles),
        )

        return cls(drama_name=drama_name, episodes=episodes, referer=referer)
