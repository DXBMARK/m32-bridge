import json

from m32_bridge.audit.writer import AuditWriter


def test_audit_writer_appends_jsonl_and_redacts_secrets(tmp_path):
    path = tmp_path / "audit.jsonl"
    writer = AuditWriter(path)
    writer.append(
        {
            "audit_id": "audit_12345678",
            "approval": {"source": "mcp_host_confirmation", "reference": "ref"},
            "operations": [{"path": "/ch/01/mix/fader", "latency_ms": 10, "auth_token": "secret"}],
        }
    )
    row = json.loads(path.read_text().splitlines()[0])
    assert row["approval"]["source"] == "mcp_host_confirmation"
    assert row["operations"][0]["latency_ms"] == 10
    assert row["operations"][0]["auth_token"] == "[REDACTED]"

