from pathlib import Path


def test_external_emulator_is_opt_in_and_not_redistributed():
    root = Path.cwd()
    forbidden_binary_suffixes = {".exe", ".dll", ".dylib", ".so"}
    bundled = [
        path
        for path in root.rglob("*")
        if ".venv" not in path.parts
        and "specs" not in path.parts
        and path.is_file()
        and path.suffix.lower() in forbidden_binary_suffixes
        and "X32" in path.name.upper()
    ]
    assert bundled == []


def test_external_emulator_requires_explicit_public_read_only_reference_or_local_env():
    research = Path("specs/001-m32-mcp-bridge/research.md").read_text(encoding="utf-8")
    assert "https://github.com/pmaillot/X32-Behringer" in research
    assert "Do not redistribute emulator binary" in Path("README.md").read_text(encoding="utf-8")

