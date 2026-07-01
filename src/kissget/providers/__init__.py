"""Provider registry: resolve which site a URL belongs to."""

from __future__ import annotations

from urllib.parse import urlparse

from kissget.providers.base import ParsedTarget, SiteProvider
from kissget.providers.kisskh import KisskhProvider

__all__ = ["KisskhProvider", "ParsedTarget", "SiteProvider", "get_provider"]

# Ordered registry; first match wins. Kisskh is also the default fallback
# (bare search queries and unrecognized URLs go to kisskh).
_PROVIDERS: list[type[SiteProvider]] = [KisskhProvider]


def _select_class(url: str | None) -> type[SiteProvider]:
    if url:
        for provider_cls in _PROVIDERS:
            if provider_cls.matches(url):
                return provider_cls
    return KisskhProvider


def get_provider(
    url: str | None = None,
    *,
    base_url: str | None = None,
    headed: bool = False,
    cdp_url: str | None = None,
) -> SiteProvider:
    """Return a provider for the given URL, or the default (kisskh) provider.

    When ``base_url`` is not supplied and ``url`` is a full site URL, the site's
    own scheme+host becomes the API base — so passing a kisskh.co URL targets
    kisskh.co with no extra config, while ``KISSKH_BASE_URL`` (passed in as
    ``base_url``) still wins when set.
    """
    provider_cls = _select_class(url)
    if base_url is None and url:
        parsed = urlparse(url)
        if parsed.scheme and parsed.hostname:
            base_url = f"{parsed.scheme}://{parsed.hostname}"
    return provider_cls(base_url=base_url, headed=headed, cdp_url=cdp_url)
