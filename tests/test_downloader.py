import requests

from kissget.downloader import Downloader, _video_select_args
from kissget.models.sub import SubItem


def test_top_tier_uses_auto_select():
    # Default/highest quality must stay byte-identical to the old behavior.
    assert _video_select_args("1080p") == ["--auto-select"]


def test_above_ladder_uses_auto_select():
    assert _video_select_args("2160p") == ["--auto-select"]


def test_invalid_quality_falls_back_to_auto_select():
    assert _video_select_args("best") == ["--auto-select"]


def test_mid_tier_selects_height_and_below_best():
    # 720p → match 720/540/480/360, pick the best of those, and still grab audio.
    assert _video_select_args("720p") == [
        "--select-video",
        'res="x(720|540|480|360)$":for=best',
        "--select-audio",
        "best",
    ]


def test_lowest_tier_matches_only_itself():
    assert _video_select_args("360p") == [
        "--select-video",
        'res="x(360)$":for=best',
        "--select-audio",
        "best",
    ]


class _FakeResponse:
    def __init__(self, content=b"", status_ok=True):
        self.content = content
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise requests.HTTPError("404 Not Found")


def test_failed_subtitle_is_skipped_not_written(monkeypatch, tmp_path):
    # A non-200 response must not produce a file, and must not raise.
    monkeypatch.setattr(
        "kissget.downloader.requests.get",
        lambda *a, **k: _FakeResponse(b"<html>blocked</html>", status_ok=False),
    )
    downloader = Downloader(referer="https://kisskh.nl")
    sub = SubItem(src="https://cdn.example/ep1.srt", label="English", land="en", default=False)
    base = tmp_path / "Show_E01"

    downloader.download_subtitles([sub], str(base))

    assert not (tmp_path / "Show_E01.en.srt").exists()


def test_successful_subtitle_is_written(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "kissget.downloader.requests.get",
        lambda *a, **k: _FakeResponse(b"1\n00:00:01,000 --> 00:00:02,000\nhi\n"),
    )
    downloader = Downloader(referer="https://kisskh.nl")
    sub = SubItem(src="https://cdn.example/ep1.srt", label="English", land="en", default=False)
    base = tmp_path / "Show_E01"

    downloader.download_subtitles([sub], str(base))

    written = tmp_path / "Show_E01.en.srt"
    assert written.exists()
    assert written.read_bytes().startswith(b"1\n")
