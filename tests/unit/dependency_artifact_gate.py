from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Sequence

from m32_bridge.installer.support_matrix import INSTALLER_TARGETS, InstallerTarget


Runner = Callable[..., subprocess.CompletedProcess[str]]


def build_target_command(
    *,
    uv_bin: str,
    requirements: Path,
    target_root: Path,
    target: InstallerTarget,
) -> list[str]:
    return [
        uv_bin,
        "pip",
        "sync",
        "--target",
        str(target_root / target.target_id),
        "--python-version",
        target.python_version,
        "--python-platform",
        target.uv_platform,
        "--only-binary=:all:",
        "--dry-run",
        str(requirements),
    ]


def run_resolution_gate(
    *,
    uv_bin: str,
    requirements: Path,
    target_root: Path,
    targets: Sequence[InstallerTarget] = INSTALLER_TARGETS,
    runner: Runner = subprocess.run,
) -> list[dict[str, object]]:
    target_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    env = {**os.environ, "UV_MANAGED_PYTHON": "1"}
    for target in targets:
        command = build_target_command(
            uv_bin=uv_bin,
            requirements=requirements,
            target_root=target_root,
            target=target,
        )
        completed = runner(command, check=False, capture_output=True, text=True, env=env)
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        results.append(
            {
                "target_id": target.target_id,
                "resolved_package_count": _resolved_package_count(output) if completed.returncode == 0 else 0,
                "missing_wheel_packages": _missing_wheel_packages(output),
                "result": completed.returncode == 0,
            }
        )
    return results


def _resolved_package_count(output: str) -> int:
    match = re.search(r"Would install (\d+) packages", output)
    if match:
        return int(match.group(1))
    return sum(1 for line in output.splitlines() if line.lstrip().startswith("+ "))


def _missing_wheel_packages(output: str) -> list[str]:
    matches = re.findall(r"Because\s+([A-Za-z0-9_.-]+==[^\s,]+)\s+has no usable wheels", output, re.IGNORECASE)
    return sorted(set(matches))


def _export_runtime_requirements(uv_bin: str, destination: Path) -> None:
    completed = subprocess.run(
        [
            uv_bin,
            "export",
            "--frozen",
            "--no-emit-project",
            "--format",
            "requirements.txt",
            "--output-file",
            str(destination),
            "--quiet",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "UV_MANAGED_PYTHON": "1"},
    )
    if completed.returncode != 0:
        raise RuntimeError("Frozen runtime dependency export failed.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate locked runtime dependencies with binary-only uv target dry-runs.")
    parser.add_argument("--uv-bin", default=shutil.which("uv"))
    args = parser.parse_args(argv)
    if not args.uv_bin or not Path(args.uv_bin).is_absolute():
        parser.error("an absolute uv executable is required")

    with tempfile.TemporaryDirectory(prefix="m32-artifact-gate-") as temporary:
        temporary_root = Path(temporary)
        requirements = temporary_root / "runtime-requirements.txt"
        _export_runtime_requirements(args.uv_bin, requirements)
        results = run_resolution_gate(
            uv_bin=args.uv_bin,
            requirements=requirements,
            target_root=temporary_root / "targets",
        )
    for result in results:
        print(json.dumps(result, sort_keys=True))
    return 0 if all(result["result"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
