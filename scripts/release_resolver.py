#!/usr/bin/env python3
"""Resolve one unified installer selection to immutable source identity."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from m32_bridge.installer.release_selection import (
    ReleaseResolutionError,
    ReleaseResolver,
    ReleaseSelectionError,
    resolve_installation_selection,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve an X32-Bridge MCP installation source")
    parser.add_argument("--version")
    parser.add_argument("--channel", choices=("stable", "prerelease", "main"))
    parser.add_argument("--ref")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args(argv)
    try:
        selection = resolve_installation_selection(
            version=args.version,
            channel=args.channel,
            ref=args.ref,
            local=args.local or None,
            source_root=args.source_root,
        )
        resolution = ReleaseResolver().resolve(selection)
    except (ReleaseSelectionError, ReleaseResolutionError) as exc:
        print(json.dumps({"ok": False, "error_code": exc.code, "message": exc.message}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, "selection": asdict(selection), "resolution": asdict(resolution)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
