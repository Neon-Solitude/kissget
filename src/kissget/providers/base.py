"""Site-provider abstraction.

The download pipeline (``Downloader``, ``manifest``, ``models``) is
site-agnostic. Everything site-specific — URL shape, search, auth tokens,
stream/subtitle resolution — lives behind :class:`SiteProvider` so a new site
plugs in without touching the rest of the tool.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from kissget.models.search import Search
from kissget.models.sub import SubItem


@dataclass
class ParsedTarget:
    """What a site URL points at.

    ``episode_ids`` is set only when the URL targets a single episode; otherwise
    it is None and the caller resolves the range via ``get_episode_ids``.
    """

    drama_id: int
    drama_slug: str
    episode_ids: dict[float, int] | None = None


class SiteProvider(ABC):
    """Adapter for one streaming site's live API."""

    #: Short identifier, e.g. "kisskh".
    name: str = "site"

    def __init__(self, base_url: str | None = None, headed: bool = False, cdp_url: str | None = None) -> None:
        """Store the requested construction options; each site uses what applies."""
        self.base_url = base_url
        self.headed = headed
        self.cdp_url = cdp_url

    @property
    def referer(self) -> str:
        """Base site URL to send as the download Referer (defaults to the configured base)."""
        return self.base_url or ""

    @classmethod
    @abstractmethod
    def matches(cls, url: str) -> bool:
        """Return True if this provider handles the given URL (by host)."""

    @abstractmethod
    def parse_url(self, url: str) -> ParsedTarget:
        """Extract the drama id/slug (and a single episode, if the URL names one).

        Raises ``ValueError`` if the URL is not a valid target for this site.
        """

    @abstractmethod
    def search(self, query: str) -> Search:
        """Search the site for a title."""

    @abstractmethod
    def get_episode_ids(self, drama_id: int, start: int, stop: int, skip_recap: bool = False) -> dict[float, int]:
        """Map episode number → API id within the requested range."""

    @abstractmethod
    def generate_auth(self, drama_id: int, episode_id: int, episode_number: int, drama_title: str) -> dict[str, str]:
        """Return the auth tokens the site needs for stream/subtitle calls."""

    @abstractmethod
    def get_stream_url(self, episode_id: int, auth: dict[str, str]) -> str:
        """Resolve the video stream URL for an episode."""

    @abstractmethod
    def get_subtitles(self, episode_id: int, auth: dict[str, str], *languages: str) -> list[SubItem]:
        """Resolve subtitle tracks for an episode, filtered to ``languages``."""

    def cleanup(self) -> None:  # noqa: B027 - optional hook; providers holding resources override it
        """Release any browser/network resources. Default: no-op."""
