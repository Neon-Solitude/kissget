"""kisskh provider — covers kisskh.nl, kisskh.co and other kisskh domains.

Wraps the existing :class:`KissKHApi` (and, lazily, ``KkeyProvider``) behind the
:class:`SiteProvider` interface. The API/kkey internals are unchanged; this is a
thin adapter that adds URL parsing and host matching.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from kissget.kisskh_api import KissKHApi
from kissget.models.search import Search
from kissget.models.sub import SubItem
from kissget.providers.base import ParsedTarget, SiteProvider


class KisskhProvider(SiteProvider):
    name = "kisskh"

    def __init__(
        self,
        base_url: str | None = None,
        headed: bool = False,
        cdp_url: str | None = None,
    ) -> None:
        super().__init__(base_url=base_url, headed=headed, cdp_url=cdp_url)
        self._api = KissKHApi(base_url=base_url, headed=headed, cdp_url=cdp_url)

    @property
    def referer(self) -> str:
        # The resolved kisskh domain (kisskh.nl, kisskh.co, …), used as CDN Referer.
        return self._api.site_domain

    @classmethod
    def matches(cls, url: str) -> bool:
        host = (urlparse(url).hostname or url).lower()
        return "kisskh" in host

    def parse_url(self, url: str) -> ParsedTarget:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        ids = query.get("id")
        if not ids:
            raise ValueError("URL must contain a ?id= parameter (e.g. .../Drama/Show?id=1234).")
        drama_id = int(ids[0])

        segments = parsed.path.split("/")
        drama_slug = segments[2] if len(segments) > 2 else ""

        # A URL like .../Drama/Show/Episode-3?id=..&ep=.. targets one episode.
        episode_ids: dict[float, int] | None = None
        episode_id = query.get("ep")
        episode_match = re.search(r"Episode-(\d+)", parsed.path)
        if episode_id and episode_match:
            episode_ids = {float(episode_match.group(1)): int(episode_id[0])}

        return ParsedTarget(drama_id=drama_id, drama_slug=drama_slug, episode_ids=episode_ids)

    def search(self, query: str) -> Search:
        return self._api.search_dramas_by_query(query)

    def get_episode_ids(self, drama_id: int, start: int, stop: int, skip_recap: bool = False) -> dict[float, int]:
        return self._api.get_episode_ids(drama_id=drama_id, start=start, stop=stop, skip_recap=skip_recap)

    def generate_auth(self, drama_id: int, episode_id: int, episode_number: int, drama_title: str) -> dict[str, str]:
        return self._api.generate_kkeys(
            drama_id=drama_id,
            episode_id=episode_id,
            episode_number=episode_number,
            drama_title=drama_title,
        )

    def get_stream_url(self, episode_id: int, auth: dict[str, str]) -> str:
        return self._api.get_stream_url(episode_id, auth.get("stream", ""))

    def get_subtitles(self, episode_id: int, auth: dict[str, str], *languages: str) -> list[SubItem]:
        return self._api.get_subtitles(episode_id, auth.get("sub", ""), *languages)

    def cleanup(self) -> None:
        self._api.cleanup()
