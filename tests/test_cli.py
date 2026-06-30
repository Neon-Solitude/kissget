import click
import pytest

from kissget.cli import _select_drama
from kissget.models.search import DramaInfo, Search


def _drama(id_, title):
    return DramaInfo(episodesCount=1, label="", favoriteID=0, thumbnail="", id=id_, title=title)


def test_single_match_is_auto_selected(monkeypatch):
    # Even when stdin is not a TTY, a lone match needs no prompt.
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    dramas = Search.model_validate([_drama(1, "Only Show")])

    chosen = _select_drama(dramas, "only")

    assert chosen.id == 1


def test_multiple_matches_without_tty_raises(monkeypatch):
    # Must fail loudly instead of blocking on input().
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    dramas = Search.model_validate([_drama(1, "Show A"), _drama(2, "Show B")])

    with pytest.raises(click.UsageError):
        _select_drama(dramas, "show")


def test_multiple_matches_with_tty_prompts(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "2")
    dramas = Search.model_validate([_drama(1, "Show A"), _drama(2, "Show B")])

    chosen = _select_drama(dramas, "show")

    assert chosen.id == 2
