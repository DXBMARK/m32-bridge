#!/usr/bin/env python3
"""Build deterministic versionless Release manifest and checksum files."""

from __future__ import annotations

import argparse
from pathlib import Path

from m32_bridge.installer.release_manifest import (
    ASSET_NAMES,
    MANIFEST_FILENAME,
    build_release_manifest,
    build_sha256sums,
    write_release_manifest,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build X32-Bridge MCP Release metadata")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--published-at", required=True)
    parser.add_argument("--release-channel", choices=("stable", "prerelease"))
    args = parser.parse_args(argv)
    manifest = build_release_manifest(
        source_root=args.source_root,
        assets_dir=args.assets_dir,
        release_tag=args.release_tag,
        source_commit=args.source_commit,
        published_at=args.published_at,
        release_channel=args.release_channel,
    )
    manifest_path = write_release_manifest(manifest, args.assets_dir / MANIFEST_FILENAME)
    checksum_names = [*ASSET_NAMES.values(), manifest_path.name]
    (args.assets_dir / "SHA256SUMS").write_text(
        build_sha256sums(args.assets_dir, checksum_names),
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
