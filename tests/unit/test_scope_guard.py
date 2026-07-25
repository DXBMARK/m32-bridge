from __future__ import annotations

import ast
from pathlib import Path

from m32_bridge.__main__ import startup_verification
from m32_bridge.core.status import hardware_acceptance_readiness
from m32_bridge.mcp.server import ToolRegistry, register_mvp_tools


SRC_ROOT = Path("src/m32_bridge")
FORBIDDEN_IMPORTS = {
    "django",
    "fastapi",
    "flask",
    "gradio",
    "streamlit",
    "uvicorn",
    "sqlalchemy",
    "sqlite3",
    "psycopg",
    "mysql",
    "celery",
}
FORBIDDEN_PUBLIC_TOOL_TERMS = {
    "raw_osc",
    "arbitrary_path",
    "send_raw_osc",
    "set_any_path",
    "m32_edit",
}


def _python_files() -> list[Path]:
    return sorted(path for path in SRC_ROOT.rglob("*.py") if "__pycache__" not in path.parts)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_runtime_startup_declares_local_monolith_without_webui_database_or_microservices():
    result = startup_verification()

    assert result["local_process"] is True
    assert result["webui"] is False
    assert result["database"] is False
    assert result["microservices"] is False
    assert result["network_side_effects"] is False
    assert result["public_network_exposure"] is False
    assert result["production_live_ready"] is False


def test_source_tree_does_not_add_webui_ai_backend_database_or_microservice_dependencies():
    imports = set().union(*(_imports(path) for path in _python_files()))

    assert imports.isdisjoint(FORBIDDEN_IMPORTS)


def test_mcp_registry_has_no_raw_osc_public_tools_or_m32_edit_control():
    registry = ToolRegistry()
    register_mvp_tools(registry)
    exposed = " ".join(registry.names()).lower()

    for term in FORBIDDEN_PUBLIC_TOOL_TERMS:
        assert term not in exposed


def test_emulator_evidence_cannot_claim_production_or_live_readiness():
    for target_kind in ("fake_m32", "external_emulator", "emulator"):
        result = hardware_acceptance_readiness({"target_kind": target_kind, "artifact_id": "emulator-proof", "checks": {}})

        assert result["status"] == "not_available"
        assert result["hardware_verified"] is False
        assert result["production_live_ready"] is False
