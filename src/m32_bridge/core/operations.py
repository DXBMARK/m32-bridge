"""Semantic operation construction and bounds enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from m32_bridge.core.models import Operation, RiskClass, RuntimeMode
from m32_bridge.core.policy import R3_ACTIONS, evaluate_policy, PolicyRequest
from m32_bridge.core.rate_limits import live_fader_delta_allowed
from m32_bridge.core.semantic_paths import is_semantic_write_allowed

ACTION_RISK = {
    "label_set": RiskClass.R1,
    "fader_set": RiskClass.R1,
    "mute_set": RiskClass.R1,
    "send_level_set": RiskClass.R2,
    "eq_adjust": RiskClass.R2,
    "dynamics_adjust": RiskClass.R2,
    "talkback_momentary": RiskClass.R2,
    "talkback_configure": RiskClass.R3,
    "headamp_set": RiskClass.R3,
    "routing_set": RiskClass.R3,
    "recall_scene": RiskClass.R3,
    "bulk_update": RiskClass.R3,
}


@dataclass(frozen=True)
class OperationIntent:
    semantic_action: str
    target_path: str
    target_kind: str
    before_value: Any
    requested_value: Any
    reason: str
    operation_id: str = "op_12345678"
    affects_main: bool = False


def operation_bounds(action: str, runtime_mode: RuntimeMode) -> dict[str, Any]:
    if action == "fader_set":
        return {"unit": "dB", "min": -90.0, "max": 10.0, "grid": 0.5, "max_delta": 3.0 if runtime_mode is RuntimeMode.LIVE else None, "live_max_delta_db": 3.0}
    if action == "headamp_set":
        return {"unit": "dB", "min": -12.0, "max": 60.0, "grid": 0.5, "max_delta": None}
    return {"unit": None, "min": None, "max": None, "grid": None, "max_delta": None}


def validate_operation_bounds(action: str, before_value: Any, requested_value: Any, runtime_mode: RuntimeMode) -> None:
    bounds = operation_bounds(action, runtime_mode)
    if bounds["min"] is None and bounds["max"] is None and bounds["grid"] is None:
        return
    try:
        requested = float(requested_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("requested value must be numeric") from exc
    if bounds["min"] is not None and requested < float(bounds["min"]):
        raise ValueError("requested value below minimum")
    if bounds["max"] is not None and requested > float(bounds["max"]):
        raise ValueError("requested value above maximum")
    if bounds["grid"] is not None:
        grid = float(bounds["grid"])
        origin = float(bounds["min"] or 0)
        steps = round((requested - origin) / grid)
        if abs((origin + steps * grid) - requested) > 1e-9:
            raise ValueError("requested value does not match grid")
    if runtime_mode is RuntimeMode.LIVE and action == "fader_set":
        if not live_fader_delta_allowed(float(before_value), requested):
            raise ValueError("LIVE fader delta exceeds policy")


def build_operation(intent: OperationIntent, runtime_mode: RuntimeMode, has_snapshot: bool = False) -> Operation:
    if intent.semantic_action not in ACTION_RISK:
        raise ValueError("unsupported semantic action")
    if "raw_osc" in intent.semantic_action or intent.target_path.startswith("/raw"):
        raise ValueError("raw OSC operations are prohibited")
    if not is_semantic_write_allowed(intent.semantic_action, intent.target_path):
        raise ValueError("target path is not allowlisted for semantic action")
    risk = ACTION_RISK[intent.semantic_action]
    affects_main = intent.affects_main or intent.target_path.startswith("/main/")
    validate_operation_bounds(intent.semantic_action, intent.before_value, intent.requested_value, runtime_mode)
    decision = evaluate_policy(
        PolicyRequest(
            runtime_mode=runtime_mode,
            risk_class=risk,
            semantic_action=intent.semantic_action,
            target_path=intent.target_path,
            affects_main=affects_main,
            has_snapshot=has_snapshot or intent.semantic_action not in R3_ACTIONS,
            live_delta_db=float(intent.requested_value) - float(intent.before_value)
            if intent.semantic_action == "fader_set"
            else None,
        )
    )
    if not decision.allowed:
        raise ValueError(",".join(decision.reasons))
    return Operation(
        operation_id=intent.operation_id,
        semantic_action=intent.semantic_action,
        target_path=intent.target_path,
        target_kind=intent.target_kind,
        before_value=intent.before_value,
        requested_value=intent.requested_value,
        rollback_value=intent.before_value,
        bounds=operation_bounds(intent.semantic_action, runtime_mode),
        risk_class=risk,
        affects_main=affects_main,
        reason=intent.reason,
    )
