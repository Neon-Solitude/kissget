import json

from kissget.manifest import ManifestReader


def _write(tmp_path, data):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_referer_defaults_to_none(tmp_path):
    p = _write(tmp_path, {"drama": "Show", "episodes": [{"number": 1, "stream_url": "http://x/i.m3u8"}]})
    manifest = ManifestReader.from_file(p)
    assert manifest.referer is None
    assert manifest.drama_name == "Show"
    assert manifest.episodes[0].number == 1


def test_site_hint_maps_to_referer(tmp_path):
    p = _write(tmp_path, {"drama": "Show", "site": "asiaflix", "episodes": []})
    manifest = ManifestReader.from_file(p)
    assert manifest.referer == "https://asiaflix.net/"


def test_explicit_referer_wins_over_site(tmp_path):
    p = _write(tmp_path, {"drama": "Show", "site": "asiaflix", "referer": "https://custom.example/", "episodes": []})
    manifest = ManifestReader.from_file(p)
    assert manifest.referer == "https://custom.example/"


def test_unknown_site_yields_no_referer(tmp_path):
    p = _write(tmp_path, {"drama": "Show", "site": "nope", "episodes": []})
    manifest = ManifestReader.from_file(p)
    assert manifest.referer is None
