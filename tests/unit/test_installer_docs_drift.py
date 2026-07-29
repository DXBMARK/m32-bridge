from __future__ import annotations

from pathlib import Path


FEATURE_DIR = Path(__file__).resolve().parents[2] / "specs" / "003-cross-platform-installers-and-first-run-setup"


def _doc(name: str) -> str:
    return (FEATURE_DIR / name).read_text(encoding="utf-8").lower()


def test_docs_remain_aligned_on_idempotency_and_lifecycle_scope():
    combined = "\n".join(_doc(name) for name in ("spec.md", "plan.md", "research.md", "data-model.md", "quickstart.md"))

    for state in ["fresh_install", "existing_install", "repair", "update", "already_current", "partial_failure", "failed"]:
        assert state in combined
    for action in ["update", "repair", "uninstall"]:
        assert action in combined
    assert "config retention" in combined or "retain saved config" in combined


def test_docs_remain_aligned_on_safe_command_ux_and_runtime_boundary():
    combined = "\n".join(
        [
            _doc("spec.md"),
            _doc("plan.md"),
            _doc("research.md"),
            _doc("quickstart.md"),
            (FEATURE_DIR / "contracts" / "installer-contract.md").read_text(encoding="utf-8").lower(),
        ]
    )

    assert "download-inspect-run" in combined
    assert "curl" in combined and "| sh" in combined
    assert "irm" in combined and "| iex" in combined
    assert "convenience" in combined
    assert "global `py`" in combined or "global py" in combined
    assert "uv" in combined
    assert "confirmation" in combined


def test_docs_remain_aligned_on_no_write_and_future_only_packaging():
    combined = "\n".join(_doc(name) for name in ("spec.md", "plan.md", "research.md", "quickstart.md"))

    assert "no `/set`" in combined or "no /set" in combined
    assert "osc_writes_sent=0" in combined
    assert "future-only" in combined
    for item in [".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", "appimage", ".mcpb", ".dxt", "github releases"]:
        assert item in combined
    assert "raw live install test is deferred until after commit/push" in combined
