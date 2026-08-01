from __future__ import annotations

import subprocess
from pathlib import Path

from dependency_artifact_gate import build_target_command, run_resolution_gate
from m32_bridge.installer.support_matrix import target_by_id


def test_target_gate_command_is_binary_only_dry_run_and_exact_python(tmp_path):
    target = target_by_id("linux_x86_64_cp313")

    command = build_target_command(
        uv_bin="/absolute/uv",
        requirements=tmp_path / "runtime.txt",
        target_root=tmp_path / "target",
        target=target,
    )

    assert command[:3] == ["/absolute/uv", "pip", "sync"]
    assert command[command.index("--python-version") + 1] == "3.13"
    assert command[command.index("--python-platform") + 1] == "x86_64-manylinux_2_17"
    assert "--only-binary=:all:" in command
    assert "--dry-run" in command
    assert "--no-binary" not in command
    assert not any(token in command for token in ("cc", "gcc", "clang", "cargo", "maturin", "rustup"))


def test_gate_reports_each_target_count_and_missing_wheel_without_installing(tmp_path):
    calls: list[list[str]] = []

    def runner(argv, **kwargs):
        calls.append(list(argv))
        platform = argv[argv.index("--python-platform") + 1]
        if platform == "x86_64-apple-darwin":
            return subprocess.CompletedProcess(
                argv,
                1,
                stdout="",
                stderr="Because cryptography==49.0.0 has no usable wheels and building from source is disabled",
            )
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout="Would install 2 packages\n + one==1.0\n + two==2.0\n",
            stderr="",
        )

    targets = [
        target_by_id("linux_x86_64_cp313"),
        target_by_id("macos_x86_64_cp313"),
    ]
    results = run_resolution_gate(
        uv_bin="/absolute/uv",
        requirements=tmp_path / "runtime.txt",
        target_root=tmp_path / "targets",
        targets=targets,
        runner=runner,
    )

    assert results[0] == {
        "target_id": "linux_x86_64_cp313",
        "resolved_package_count": 2,
        "missing_wheel_packages": [],
        "result": True,
    }
    assert results[1] == {
        "target_id": "macos_x86_64_cp313",
        "resolved_package_count": 0,
        "missing_wheel_packages": ["cryptography==49.0.0"],
        "result": False,
    }
    assert len(calls) == 2
    assert all("--dry-run" in call for call in calls)
