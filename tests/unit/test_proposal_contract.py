from jsonschema import Draft202012Validator

from m32_bridge.config.schemas import load_schema
from m32_bridge.mcp.write_tools import m32_propose_changes


def test_proposal_output_can_be_expanded_to_contract_shape():
    result = m32_propose_changes(
        intent="Set channel 1 fader",
        targets=[{"semantic_action": "fader_set", "target_path": "/ch/01/mix/fader", "before_value": -10.0, "requested_value": -8.0}],
    )
    op = result["operations"][0]
    proposal = {
        "schema_version": "1.0.0",
        "proposal_id": result["proposal_id"],
        "proposal_digest": result["proposal_digest"],
        "created_at": "2026-07-20T00:00:00Z",
        "expires_at": result["expires_at"],
        "created_by": "claude_desktop",
        "runtime_mode_at_creation": "SOUNDCHECK",
        "base_snapshot_id": "snap_12345678",
        "base_revisions": [{"path": "/ch/01/mix/fader", "revision": 1}],
        "operations": [
            {
                "operation_id": op["operation_id"],
                "semantic_action": op["semantic_action"],
                "target_path": op["target_path"],
                "target_kind": op["target_kind"],
                "risk_class": op["risk_class"],
                "before_value": op["before_value"],
                "requested_value": op["requested_value"],
                "rollback_value": op["rollback_value"],
                "bounds": op["bounds"],
                "requires_readback": op["requires_readback"],
                "affects_main": op["affects_main"],
                "reason": op["reason"],
            }
        ],
        "risk_summary": result["risk_summary"],
        "status": "PENDING_APPROVAL",
        "human_readable_summary": "Set channel 1 fader",
        "server_computed": True,
    }
    Draft202012Validator(load_schema("proposal.schema.json")).validate(proposal)

