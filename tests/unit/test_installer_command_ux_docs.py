from __future__ import annotations

from pathlib import Path


QUICKSTART = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "003-cross-platform-installers-and-first-run-setup"
    / "quickstart.md"
)


def test_download_inspect_run_is_recommended_over_pipe_one_liners():
    text = QUICKSTART.read_text(encoding="utf-8").lower()
    section = text.split("installer command ux and release guidance:", 1)[1]

    assert "download-inspect-run" in section
    assert "recommended" in section
    assert "curl" in section
    assert "| sh" in section
    assert "irm" in section
    assert "| iex" in section
    assert "convenience" in section
    assert section.index("download-inspect-run") < section.index("convenience")


def test_release_guidance_keeps_github_raw_live_test_deferred_until_push():
    text = QUICKSTART.read_text(encoding="utf-8").lower()

    assert "github public repo" in text
    assert "after push" in text
    assert "version/tag" in text
    assert "raw live install test" in text
    assert "deferred" in text
    assert "commit/push" in text
