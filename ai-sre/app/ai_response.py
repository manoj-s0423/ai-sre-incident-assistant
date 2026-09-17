from typing import Literal

from pydantic import BaseModel


class InvestigationStep(BaseModel):
    step: int
    action: str
    reason: str
    command: str | None
    expected_result: str
    risk: Literal["Low", "Medium", "High"]
    requires_approval: bool

class InvestigationDecision(BaseModel):
    status: Literal[
        "continue",
        "resolved",
        "root_cause_identified",
        "insufficient_evidence"
    ]
    action: str | None

    reason: str

    tool: Literal[
        "get_pod_logs",
        "get_previous_logs",
        "get_pod_details",
        "get_deployment_history",
        "get_kubernetes_events",
        "get_service_observability"
    ] | None

    target: str | None

    expected_result: str | None

    risk: Literal["Low", "Medium", "High"]

    requires_approval: bool

class RCAResponse(BaseModel):
    incident_summary: str

    observations: list[str]

    root_cause: str

    evidence: list[str]

    affected_component: str

    impact: str

    confidence: Literal["High", "Medium", "Low"]

    investigation_steps: list[InvestigationStep]

    recommended_actions: list[str]

    additional_evidence_needed: list[str]

class RemediationAction(BaseModel):
    action: str
    reason: str
    risk: Literal["Low", "Medium", "High"]
    requires_approval: bool
    status: Literal[
        "pending",
        "approved",
        "rejected",
        "executed"
    ] = "pending"