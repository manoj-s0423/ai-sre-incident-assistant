from fastapi import (
    FastAPI,
    BackgroundTasks,
    Request
)

from kubernetes import client, config

from datetime import datetime, timezone

import requests
import os
import json
import anthropic
import uuid

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.models import IncidentRequest

from app.ai_response import (
    RCAResponse,
    InvestigationDecision
)

from app.investigation_tools import (
    execute_investigation_tool
)

from app.database import (
    init_db,
    create_incident,
    update_incident,
    resolve_incident,
    get_incidents,
    get_incident_by_id,
    get_incident_stats,
    get_incidents_by_severity,
    get_incidents_by_service,
    get_incident_trends,
    get_resolution_rate,
    get_recurring_incidents,
    get_mttr_trends,
    get_incident_by_fingerprint
)

from app.observability import (
    get_service_observability,
    get_kubernetes_health
)


# ============================================================
# FastAPI Application
# ============================================================

app = FastAPI(
    title="AI SRE Incident Assistant",
    description="AI-powered incident investigation and root cause analysis",
    version="1.0.0"
)


# ============================================================
# Jinja2 Templates
# ============================================================

templates = Jinja2Templates(
    directory="templates"
)


# ============================================================
# Initialize Database
# ============================================================

init_db()


# ============================================================
# Configuration
# ============================================================

PROMETHEUS_URL = os.getenv(
    "PROMETHEUS_URL",
    "http://127.0.0.1:9091"
)


CLAUDE_MODEL = os.getenv(
    "CLAUDE_MODEL",
    "claude-sonnet-5"
)


# ============================================================
# Anthropic Configuration
# ============================================================

ANTHROPIC_API_KEY = os.getenv(
    "ANTHROPIC_API_KEY"
)

if not ANTHROPIC_API_KEY:
    raise RuntimeError(
        "ANTHROPIC_API_KEY environment variable is not configured"
    )


claude_client = anthropic.Anthropic(
    api_key=ANTHROPIC_API_KEY
)


# ============================================================
# Incident State
# ============================================================

latest_incident = {
    "status": "idle",
    "message": "No automated incident investigation yet."
}


processed_incidents = {}


# ============================================================
# Basic Endpoints
# ============================================================

@app.get("/")
def root():

    return {
        "service": "AI SRE Incident Assistant",
        "status": "running"
    }


@app.get("/health")
def health():

    return {
        "status": "healthy"
    }


# ============================================================
# Prometheus Helper
# ============================================================

def query_prometheus(query: str):
    """
    Execute a PromQL query against Prometheus.
    """

    try:

        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={
                "query": query
            },
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        if data.get("status") != "success":
            return None

        results = data.get(
            "data",
            {}
        ).get(
            "result",
            []
        )

        if not results:
            return None

        return results[0]["value"][1]

    except requests.RequestException as e:

        return f"Prometheus request failed: {e}"

    except Exception as e:

        return f"Prometheus query failed: {e}"


# ============================================================
# Kubernetes Log Filtering
# ============================================================

def filter_logs(logs: str):

    if not logs:
        return ""

    lines = logs.splitlines()

    filtered_lines = []

    for line in lines:

        if "/metrics" in line:
            continue

        filtered_lines.append(line)

    return "\n".join(
        filtered_lines[-30:]
    )


# ============================================================
# Alert Context Helper
# ============================================================

def build_alert_context(
    incident: IncidentRequest
):

    return {

        "alert": {

            "name": incident.alert_name,

            "service": incident.service,

            "severity": incident.severity,

            "status": incident.status,

            "summary": incident.summary,

            "description": incident.description,

            "starts_at": incident.starts_at,

            "ends_at": incident.ends_at,

            "fingerprint": incident.fingerprint

        },

        "labels": incident.labels,

        "annotations": incident.annotations

    }

# ============================================================
# Generic Alert Recovery Check
# ============================================================

def is_alert_currently_active(
    incident: IncidentRequest
):
    """
    Determine whether an alert should still be investigated.

    This function does not contain alert-specific logic.

    It uses the current Alertmanager state and the information
    supplied by Alertmanager.

    Returns:

        {
            "active": True/False,
            "reason": "..."
        }
    """

    # --------------------------------------------------------
    # Alertmanager explicitly says the alert is resolved
    # --------------------------------------------------------

    if incident.status == "resolved":

        return {
            "active": False,
            "reason": (
                "Alertmanager reports that the alert "
                "has already been resolved."
            )
        }


    # --------------------------------------------------------
    # Alertmanager says the alert is firing
    # --------------------------------------------------------

    if incident.status == "firing":

        return {
            "active": True,
            "reason": (
                "Alertmanager reports that the alert "
                "is currently firing."
            )
        }


    # --------------------------------------------------------
    # Unknown state
    # --------------------------------------------------------

    return {
        "active": True,
        "reason": (
            "The alert state is unknown. "
            "Investigation will continue because "
            "the system cannot safely assume recovery."
        )
    }


# ============================================================
# Collect Incident Evidence
# ============================================================

def collect_incident_context(
    incident: IncidentRequest
):
    """
    Collect Prometheus and Kubernetes evidence.

    This function does NOT call Claude.

    It is intentionally separated from the AI layer so
    interactive investigation does not accidentally perform
    an additional RCA call.
    """

    # ========================================================
    # 1. Load Kubernetes Configuration
    # ========================================================

    config.load_kube_config()

    v1 = client.CoreV1Api()

    apps_v1 = client.AppsV1Api()


    # ========================================================
    # 2. Query Prometheus
    # ========================================================

    # --------------------------------------------------------
    # HTTP 5xx Error Rate
    # --------------------------------------------------------

    error_rate_query = """
    (
        sum(rate(http_requests_total{status=~"5.."}[5m]))
        /
        sum(rate(http_requests_total[5m]))
    ) * 100
    """


    # --------------------------------------------------------
    # HTTP Request Rate
    # --------------------------------------------------------

    request_rate_query = """
    sum(rate(http_requests_total[5m]))
    """


    # --------------------------------------------------------
    # P95 HTTP Latency
    # --------------------------------------------------------

    latency_query = """
    histogram_quantile(
        0.95,
        sum(
            rate(http_request_duration_seconds_bucket[5m])
        ) by (le)
    )
    """


    error_rate = query_prometheus(
        error_rate_query
    )


    request_rate = query_prometheus(
        request_rate_query
    )


    latency_p95 = query_prometheus(
        latency_query
    )


    # ========================================================
    # 3. Get Kubernetes Deployments
    # ========================================================

    deployments = apps_v1.list_namespaced_deployment(
        namespace="ai-sre"
    )


    deployment_details = []


    for deployment in deployments.items:

        containers = []


        for container in deployment.spec.template.spec.containers:

            containers.append({

                "name": container.name,

                "image": container.image

            })


        deployment_details.append({

            "name": deployment.metadata.name,

            "desired_replicas":
                deployment.spec.replicas,

            "available_replicas":
                deployment.status.available_replicas or 0,

            "ready_replicas":
                deployment.status.ready_replicas or 0,

            "updated_replicas":
                deployment.status.updated_replicas or 0,

            "containers": containers

        })


    # ========================================================
    # 4. Get Kubernetes Events
    # ========================================================

    events = v1.list_namespaced_event(
        namespace="ai-sre"
    )


    event_details = []


    for event in events.items:

        event_details.append({

            "type": event.type,

            "reason": event.reason,

            "message": event.message,

            "object": (
                event.involved_object.name
                if event.involved_object
                else None
            ),

            "timestamp": str(
                event.last_timestamp
                or event.event_time
                or event.metadata.creation_timestamp
            )

        })


    # Keep only the most recent 20 events

    event_details = event_details[-20:]


    # ========================================================
    # 5. Get Kubernetes Pods
    # ========================================================

    pods = v1.list_namespaced_pod(
        namespace="ai-sre"
    )


    pod_details = []


    for pod in pods.items:

        # ----------------------------------------------------
        # Calculate restart count
        # ----------------------------------------------------

        restart_count = 0


        if pod.status.container_statuses:

            restart_count = sum(

                container.restart_count

                for container
                in pod.status.container_statuses

            )


        # ----------------------------------------------------
        # Get pod logs
        # ----------------------------------------------------

        logs = ""


        try:

            logs = v1.read_namespaced_pod_log(

                name=pod.metadata.name,

                namespace="ai-sre",

                tail_lines=50

            )


            logs = filter_logs(
                logs
            )


        except Exception as log_error:

            logs = (
                "Unable to retrieve logs: "
                f"{log_error}"
            )


        # ----------------------------------------------------
        # Store pod evidence
        # ----------------------------------------------------

        pod_details.append({

            "name": pod.metadata.name,

            "status": pod.status.phase,

            "node": pod.spec.node_name,

            "restart_count": restart_count,

            "logs": logs

        })


    # ========================================================
    # 6. Observability
    # ========================================================

    service_observability = (
        get_service_observability()
    )


    # ========================================================
    # 7. Kubernetes Health
    # ========================================================

    kubernetes_health = (
        get_kubernetes_health()
    )


    # ========================================================
    # 8. Build Incident Context
    # ========================================================

    incident_context = {

        "incident": build_alert_context(
            incident
        ),

        "evidence": {

            "prometheus": {

                "http_5xx_error_rate_percent": error_rate,

                "http_request_rate_per_second": request_rate,

                "http_latency_p95_seconds": latency_p95

            },

            "kubernetes": {

                "namespace": "ai-sre",

                "pods": pod_details,

                "events": event_details,

                "deployments": deployment_details

            },

            "observability": service_observability,

            "kubernetes_health": kubernetes_health

        }

    }


    return (
        incident_context,
    )


# ============================================================
# Claude RCA Engine
# ============================================================

def generate_root_cause_analysis(
    incident_context
):

    prompt = f"""
You are an expert Site Reliability Engineer (SRE) and
AI-powered incident response assistant.

Your job is to investigate a production incident using ONLY
the evidence provided below.

You must reason from the evidence and guide an SRE through
the incident.

There is NO predefined runbook.

You must dynamically determine what the SRE should
investigate based on the available evidence.

============================================================
INCIDENT
============================================================

{json.dumps(
    incident_context,
    indent=2
)}

============================================================
YOUR OBJECTIVE
============================================================

Analyze the incident and determine:

1. What happened?
2. Which service or component is affected?
3. What evidence supports the diagnosis?
4. What is the most likely root cause?
5. What is the current impact?
6. How confident are you?
7. What important evidence is missing?
8. What should the SRE investigate next?
9. What remediation options are available?
10. Which remediation actions require human approval?

============================================================
EVIDENCE-BASED REASONING RULES
============================================================

RULE 1:
Never invent evidence.

Only use information contained in the incident evidence.

RULE 2:
Clearly distinguish between:

- Observed facts
- Reasonable inference
- Hypothesis
- Confirmed root cause

RULE 3:
If the evidence is insufficient to determine the root cause,
DO NOT invent a root cause.

Instead state:

"Insufficient evidence to confirm the root cause."

Then explain what evidence is missing.

RULE 4:
Current healthy metrics do NOT prove that the incident never
happened.

The alert may represent a historical or transient problem.

RULE 5:
Do not recommend restarting pods, deleting resources, scaling
resources, rolling back deployments, or changing configuration
unless evidence supports that action.

RULE 6:
Never recommend destructive or potentially disruptive actions
without explicitly marking them as:

risk = "High"

and:

requires_approval = true

============================================================
SRE INVESTIGATION STRATEGY
============================================================

Determine which layer is most likely responsible.

Possible layers include:

- Application
- Kubernetes
- Container
- Deployment
- Resource capacity
- Network
- Dependency
- Configuration
- Infrastructure

Do NOT assume the layer.

Determine it from the evidence.

============================================================
DYNAMIC INVESTIGATION STEPS
============================================================

The "investigation_steps" field is MANDATORY.

Provide at least 3 investigation steps.

The steps must be specific to the incident.

Do NOT generate generic SRE advice.

Each step must help answer an actual unresolved question.

Every investigation step MUST contain:

- step
- action
- reason
- command
- expected_result
- risk
- requires_approval

============================================================
COMMAND RULES
============================================================

Commands should be realistic commands an SRE could execute.

Use commands such as:

kubectl get
kubectl describe
kubectl logs
kubectl logs --previous
kubectl get events
kubectl rollout history
kubectl rollout status
kubectl top
curl
Prometheus queries
Linux commands

Do NOT invent pod names that are not present in the evidence.

============================================================
REMEDIATION
============================================================

Separate investigation from remediation.

Recommended actions may include:

- code fix
- configuration correction
- deployment rollback
- resource adjustment
- dependency investigation
- alert tuning
- monitoring improvement
- logging improvement
- capacity adjustment

Remediation must be supported by evidence.

============================================================
ROOT CAUSE RULES
============================================================

High:
Evidence directly demonstrates the root cause.

Medium:
Evidence strongly suggests the root cause but confirmation
is still required.

Low:
Insufficient evidence and the root cause is only a hypothesis.

If confidence is Low:

Clearly state that the root cause is NOT confirmed.

============================================================
FINAL RESPONSE FORMAT
============================================================

Return ONLY valid JSON.

Do NOT return Markdown.

The response MUST follow exactly this structure:

{{
    "incident_summary": "string",
    "observations": [
        "string"
    ],
    "root_cause": "string",
    "evidence": [
        "string"
    ],
    "affected_component": "string",
    "impact": "string",
    "confidence": "High",
    "investigation_steps": [
        {{
            "step": 1,
            "action": "string",
            "reason": "string",
            "command": "string or null",
            "expected_result": "string",
            "risk": "Low",
            "requires_approval": false
        }}
    ],
    "recommended_actions": [
        "string"
    ],
    "additional_evidence_needed": [
        "string"
    ]
}}

IMPORTANT:

Do not return null for:

- action
- reason
- expected_result

High-risk actions MUST have:

"requires_approval": true

Return ONLY JSON.
"""

    try:

        response = claude_client.messages.create(

            model=CLAUDE_MODEL,

            max_tokens=4000,

            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]

        )


        response_text = ""


        for block in response.content:

            if block.type == "text":

                response_text += block.text


        if not response_text.strip():

            return {
                "error": (
                    "Claude did not return "
                    "a text response."
                )
            }


        response_text = response_text.strip()


        # ----------------------------------------------------
        # Remove Markdown JSON fences
        # ----------------------------------------------------

        if response_text.startswith(
            "```json"
        ):

            response_text = response_text[7:]


        elif response_text.startswith(
            "```"
        ):

            response_text = response_text[3:]


        if response_text.endswith(
            "```"
        ):

            response_text = response_text[:-3]


        response_text = response_text.strip()


        # ----------------------------------------------------
        # Parse JSON
        # ----------------------------------------------------

        rca_data = json.loads(
            response_text
        )


        # ----------------------------------------------------
        # Validate RCA
        # ----------------------------------------------------

        validated_rca = (
            RCAResponse.model_validate(
                rca_data
            )
        )


        return validated_rca.model_dump()


    except Exception as e:

        return {

            "error":
                "Failed to generate RCA",

            "details":
                str(e)

        }


# ============================================================
# Dynamic AI Investigation Decision
# ============================================================

def get_next_investigation_step(
    incident_context,
    investigation_history
):

    prompt = f"""
You are an AI-powered SRE investigation decision engine.

Your responsibility is to investigate production incidents
using real evidence provided by monitoring and Kubernetes
investigation tools.

The incident may be caused by:

- application errors
- latency problems
- resource exhaustion
- pod failures
- deployment changes
- networking problems
- infrastructure issues
- dependency failures
- configuration problems
- other operational conditions

You MUST NOT assume the incident type in advance.

============================================================
CURRENT INCIDENT
============================================================

{json.dumps(
    incident_context,
    indent=2
)}

============================================================
PREVIOUS INVESTIGATION RESULTS
============================================================

{json.dumps(
    investigation_history,
    indent=2
)}

You MUST inspect the previous investigation results before
selecting the next tool.

Do NOT repeat the same tool against the same target unless:

- previous execution failed
OR
- new evidence makes repeating it necessary.

Prefer investigations that provide NEW evidence.

============================================================
AVAILABLE INVESTIGATION TOOLS
============================================================

1. get_pod_logs

Purpose:
Inspect current application logs from a specific pod.

Target:
Pod name.

Risk:
Low.


2. get_previous_logs

Purpose:
Inspect logs from the previous terminated container.

Target:
Pod name.

Risk:
Low.


3. get_pod_details

Purpose:
Inspect pod state, readiness, restart count and container
termination information.

Target:
Pod name.

Risk:
Low.


4. get_deployment_history

Purpose:
Inspect current Deployment state and available ReplicaSet
history.

Target:
Deployment name.

Risk:
Low.

Do NOT claim a deployment caused the incident unless evidence
supports that conclusion.

If timing is insufficient, explicitly state that deployment
history is inconclusive.


5. get_kubernetes_events

Purpose:
Inspect Kubernetes events associated with the service
namespace.

Target:
None.

Risk:
Low.


6. get_service_observability

Purpose:
Inspect:

- CPU
- memory
- pod restarts
- latency
- HTTP error rate

Target:
Service name.

Risk:
Low.


============================================================
INVESTIGATION PRINCIPLES
============================================================

1. START FROM THE ALERT

Use:

- alert name
- service
- severity
- status
- summary
- description
- labels
- annotations

An alert represents a symptom or condition.

It does NOT automatically represent the root cause.


2. FOLLOW THE EVIDENCE

Distinguish:

OBSERVED FACT:
Directly supported by tool output.

HYPOTHESIS:
Possible explanation that is not confirmed.

ROOT CAUSE:
Explanation strongly supported by evidence.


3. INVESTIGATE THE MOST USEFUL NEXT QUESTION

Ask:

"What is the most valuable piece of evidence I can collect
next?"

Choose the tool that best answers that question.


4. ADAPT TO NEW EVIDENCE

If new evidence changes the likely cause, change direction.

Do not continue investigating an unrelated hypothesis.


5. DO NOT INVENT EVIDENCE

Never claim:

- deployment caused incident
- node failed
- database failed
- memory was exhausted
- network failed
- application crashed

unless evidence supports the claim.


6. CORRELATE TIMING

When possible compare:

- alert timing
- metric changes
- pod restarts
- termination times
- deployment changes
- ReplicaSet creation times
- Kubernetes events
- log timestamps


============================================================
STOP CONDITIONS
============================================================

Return:

"root_cause_identified"

when sufficient evidence supports a specific root cause.

Return:

"resolved"

when:

- incident condition is no longer active
- service is healthy
- no further immediate investigation is required

Return:

"insufficient_evidence"

when:

- available tools cannot establish the cause
- historical evidence is unavailable
- external systems are required
- no useful new evidence is available
- the same evidence has already been investigated

Return:

"continue"

ONLY when another tool can provide meaningful new evidence.

Normally aim for 3-8 steps.

Never exceed the configured safety limit.


============================================================
SAFETY
============================================================

All investigation tools are READ-ONLY.

Do not request:

- kubectl delete
- kubectl rollout restart
- kubectl scale
- kubectl patch
- arbitrary kubectl exec
- deployment modification
- configuration modification
- infrastructure modification

If remediation is required, provide it as a recommendation.

Do not execute remediation automatically.


============================================================
OUTPUT FORMAT
============================================================

Return ONLY valid JSON.

{{
    "status": "continue | resolved | root_cause_identified | insufficient_evidence",
    "action": "string",
    "reason": "string",
    "tool": "get_pod_logs | get_previous_logs | get_pod_details | get_deployment_history | get_kubernetes_events | get_service_observability | null",
    "target": "string | null",
    "expected_result": "string",
    "risk": "Low | Medium | High",
    "requires_approval": false
}}

IMPORTANT:

action MUST be a string.

reason MUST be a string.

expected_result MUST be a string.

NEVER return null for these fields.

For terminal states:

tool = null
target = null

For continue:

tool MUST be one of the available tools.

target MUST be supplied when required.

Return ONLY JSON.
"""


    response = claude_client.messages.create(

        model=CLAUDE_MODEL,

        max_tokens=3000,

        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]

    )


    response_text = ""


    for block in response.content:

        if block.type == "text":

            response_text += block.text


    if not response_text.strip():

        return {

            "status":
                "insufficient_evidence",

            "action":
                "Stop investigation",

            "reason": (
                "Claude returned no usable "
                "decision for the next "
                "investigation step."
            ),

            "tool":
                None,

            "target":
                None,

            "expected_result": (
                "No additional investigation "
                "decision was available."
            ),

            "risk":
                "Low",

            "requires_approval":
                False

        }


    response_text = response_text.strip()


    # --------------------------------------------------------
    # Remove Markdown JSON fences
    # --------------------------------------------------------

    if response_text.startswith(
        "```json"
    ):

        response_text = response_text[7:]


    elif response_text.startswith(
        "```"
    ):

        response_text = response_text[3:]


    if response_text.endswith(
        "```"
    ):

        response_text = response_text[:-3]


    response_text = response_text.strip()


    # --------------------------------------------------------
    # Parse and validate decision
    # --------------------------------------------------------

    decision_data = json.loads(
        response_text
    )


    decision = InvestigationDecision.model_validate(
        decision_data
    )


    return decision.model_dump()


# ============================================================
# Interactive Investigation
# ============================================================

def run_interactive_investigation(
    incident_context,
    max_steps=5
):

    investigation_history = []


    for step_number in range(
        1,
        max_steps + 1
    ):

        decision = get_next_investigation_step(

            incident_context,

            investigation_history

        )


        history_entry = {

            "step":
                step_number,

            "decision":
                decision

        }


        investigation_history.append(
            history_entry
        )


        # ----------------------------------------------------
        # Investigation finished
        # ----------------------------------------------------

        if decision["status"] in [

            "root_cause_identified",

            "insufficient_evidence",

            "resolved"

        ]:

            return {

                "status":
                    decision["status"],

                "steps":
                    investigation_history

            }


        # ----------------------------------------------------
        # AI requested another tool
        # ----------------------------------------------------

        tool = decision.get(
            "tool"
        )


        if not tool:

            return {

                "status":
                    "insufficient_evidence",

                "reason": (
                    "AI requested further "
                    "investigation but did "
                    "not select a tool."
                ),

                "steps":
                    investigation_history

            }


        target = decision.get(
            "target"
        )


        evidence = execute_investigation_tool(

            tool=tool,

            target=target

        )


        history_entry[
            "evidence"
        ] = evidence


    # --------------------------------------------------------
    # Safety fallback
    # --------------------------------------------------------

    return {

        "status":
            "investigation_limit_reached",

        "reason": (
            f"Safety limit of "
            f"{max_steps} investigation "
            f"steps reached."
        ),

        "steps":
            investigation_history

    }
# ============================================================
# Build Structured Investigation Result
# ============================================================
def build_investigation_result(
    investigation
):
    """
    Convert the raw interactive investigation into
    a structured incident result.

    No additional Claude API call is made here.
    """

    status = investigation.get(
        "status",
        "insufficient_evidence"
    )

    steps = investigation.get(
        "steps",
        []
    )

    root_cause = None
    root_cause_identified = False
    confidence = "Low"
    conclusion = None
    recommended_actions = []
    affected_component = None
    impact = None
    additional_evidence_needed = []

    final_decision = {}

    if steps:

        final_step = steps[-1]

        final_decision = final_step.get(
            "decision",
            {}
        )

    conclusion = final_decision.get(
        "reason"
    )

    if status == "root_cause_identified":

        root_cause_identified = True

        root_cause = final_decision.get(
            "reason"
        )

        confidence = "Medium"

        affected_component = (
            final_decision.get(
                "target"
            )
            or "order-service"
        )

        impact = (
            "The order-service alert condition "
            "has been identified and investigated."
        )

        action = final_decision.get(
            "action"
        )

        if action:
            recommended_actions.append(
                action
            )

    elif status == "resolved":

        root_cause_identified = False

        root_cause = None

        confidence = "Low"

        impact = (
            "The alert condition is no longer active."
        )

    elif status == "insufficient_evidence":

        root_cause_identified = False

        root_cause = None

        confidence = "Low"

        additional_evidence_needed = [
            "Additional investigation evidence is required to determine the exact root cause."
        ]

    evidence = []

    for step in steps:

        step_evidence = step.get(
            "evidence",
            {}
        )

        if step_evidence:

            tool = step_evidence.get(
                "tool",
                "unknown"
            )

            evidence.append(
                f"{tool}: "
                f"{json.dumps(step_evidence)}"
            )

    return {
        "status": status,

        "root_cause_identified":
            root_cause_identified,

        "root_cause":
            root_cause,

        "confidence":
            confidence,

        "affected_component":
            affected_component,

        "impact":
            impact,

        "conclusion":
            conclusion,

        "investigation_steps":
            steps,

        "recommended_actions":
            recommended_actions,

        "evidence":
            evidence,

        "additional_evidence_needed":
            additional_evidence_needed
    }


# ============================================================
# Incident Investigation API
# ============================================================

@app.post("/investigate")
def investigate(incident: IncidentRequest):

    try:

        # ========================================================
        # Generic Alert State Check
        # ========================================================

        alert_state = is_alert_currently_active(
            incident
        )    

        # ====================================================
        # Stop Immediately If Resolved
        # ====================================================
        
        if not alert_state["active"]:

            return {

                "status": "success",

                "incident_context": {

                    "incident":
                        build_alert_context(
                            incident
                        ),

                    "evidence":
                        {}

                },

                "root_cause_analysis": {

                    "status": "resolved",

                    "reason": alert_state["reason"],

                    "ai_investigation_skipped": True

                }

            }
        
        # ====================================================
        # Collect evidence
        # ====================================================

        incident_context = collect_incident_context(
            incident
        )

        # ====================================================
        # Generate RCA
        # ====================================================

        rca = generate_root_cause_analysis(
            incident_context
        )

        # ====================================================
        # Return
        # ====================================================

        return {

            "status": "success",

            "incident_context": incident_context,

            "root_cause_analysis": rca

        }


    except Exception as e:

        return {

            "status": "error",

            "message": str(e)

        }

# ============================================================
# Interactive Investigation API
# ============================================================

@app.post("/investigate-interactive")
def investigate_interactive(incident: IncidentRequest):

    try:
        # ====================================================
        # Generic Alert State Check
        # ====================================================

        alert_state = is_alert_currently_active(
            incident
        )

        # ====================================================
        # Alert Already Resolved
        # ====================================================

        if not alert_state["active"]:

            return {

                "status": "success",

                "incident_context": {

                    "incident": build_alert_context(
                            incident
                        ),

                    "evidence": {}

                },

                "investigation": {

                    "status": "resolved",

                    "steps": [],

                    "ai_investigation_skipped": True,

                    "reason": alert_state["reason"]

                }

            }

        # ====================================================
        # Collect Incident Evidence
        # ====================================================

        incident_context = collect_incident_context(
            incident
        )

        # ====================================================
        # Dynamic AI Investigation
        # ====================================================

        investigation = run_interactive_investigation(
            incident_context
        )

        return {

            "status": "success",

            "incident_context": incident_context,

            "investigation": investigation

        }


    except Exception as e:

        return {

            "status": "error",

            "message": str(e)

        }
    
# ============================================================
# Automated Dynamic AI Investigation
# ============================================================

def run_automated_investigation( incident, fingerprint):

    global latest_incident


    try:

        # ====================================================
        # 1. Check Alert State
        # ====================================================

        alert_state = is_alert_currently_active(
            incident
        )


        # ====================================================
        # 2. Stop If Alert Is Already Resolved
        # ====================================================

        if not alert_state["active"]:

            result = {

                "status": "resolved",

                "steps": [],

                "ai_investigation_skipped": True,

                "reason": alert_state["reason"]

            }


            update_incident(

                fingerprint=fingerprint,

                rca=result

            )


            latest_incident = {

                "status": "resolved",

                "fingerprint": fingerprint,

                "investigation": result

            }


            if fingerprint in processed_incidents:

                processed_incidents[
                    fingerprint
                ][
                    "status"
                ] = "resolved"


            return


        # ====================================================
        # 3. Collect Incident Evidence
        # ====================================================

        incident_context = (
            collect_incident_context(
                incident
            )
        )

        # ====================================================
        # 4. Run Dynamic AI Investigation
        # ====================================================

        investigation = (
            run_interactive_investigation(

                incident_context,

                max_steps=5

            )
        )

        # ========================================================
        # Build Structured Result
        # ========================================================

        investigation_result = (
            build_investigation_result(
                investigation
            )
        )


        # ====================================================
        # 5. Save Investigation Result
        # ====================================================

        update_incident(

            fingerprint=fingerprint,

            rca=investigation_result

        )


        # ====================================================
        # 6. Update Latest Incident
        # ====================================================

        latest_incident = {

            "status":
                investigation_result.get(
                    "status",
                    "unknown"
                ),

            "fingerprint":
                fingerprint,

            "incident_context":
                incident_context,

            "investigation":
                investigation,

            "investigation_result":
                investigation_result

        }


        # ====================================================
        # 7. Update Processing State
        # ====================================================

        if fingerprint in processed_incidents:

            processed_incidents[fingerprint][ "status" ] = "investigated"


    except Exception as e:

        # ====================================================
        # Investigation Failure
        # ====================================================

        latest_incident = {

            "status": "error",

            "fingerprint": fingerprint,

            "message": str(e)

        }


        if fingerprint in processed_incidents:

            processed_incidents[
                fingerprint
            ][
                "status"
            ] = "error"

# ============================================================
# Remediation Risk
# ============================================================

HIGH_RISK_ACTIONS = [
    "delete pod",
    "restart pod",
    "restart deployment",
    "restart the order-service deployment",
    "rollback deployment",
    "rollback the order-service deployment",
    "scale deployment",
    "scale the order-service deployment",
    "delete deployment",
    "delete the order-service deployment"
]


def classify_remediation_risk(
    action: str
):
    """
    Classify a remediation action based on
    its potential operational impact.
    """

    if not action:
        return {
            "risk": "Low",
            "requires_approval": False
        }

    action_lower = action.lower()

    for dangerous_action in HIGH_RISK_ACTIONS:

        if dangerous_action in action_lower:

            return {
                "risk": "High",
                "requires_approval": True
            }

    return {
        "risk": "Low",
        "requires_approval": False
    }


# ============================================================
# Remediation Approval Store
# ============================================================

pending_remediations = {}

# ============================================================
# Create Remediation Request
# ============================================================

@app.post("/api/remediation")
def create_remediation(
    action: str,
    reason: str,
    risk: str
):
    try:

        risk_result = classify_remediation_risk(
            action
        )

        remediation_id = str(
            uuid.uuid4()
        )

        remediation = {
            "id": remediation_id,
            "action": action,
            "reason": reason,
            "risk": risk_result["risk"],
            "requires_approval": risk_result[
                "requires_approval"
            ],
            "status": (
                "pending"
                if risk_result["requires_approval"]
                else "approved"
            )
        }

        pending_remediations[
            remediation_id
        ] = remediation

        return {
            "status": "success",
            "remediation": remediation
        }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }

    
# ============================================================
# Get Pending Remediations
# ============================================================

@app.get("/api/remediation")
def get_remediations():

    return {
        "status": "success",
        "remediations": list(
            pending_remediations.values()
        )
    }


# ============================================================
# Approve Remediation
# ============================================================

@app.post("/api/remediation/{remediation_id}/approve")
def approve_remediation(
    remediation_id: str
):

    remediation = pending_remediations.get(
        remediation_id
    )

    if not remediation:

        return {
            "status": "error",
            "message": "Remediation not found."
        }

    remediation["status"] = "approved"

    return {
        "status": "success",
        "message": "Remediation approved.",
        "remediation": remediation
    }


# ============================================================
# Reject Remediation
# ============================================================

@app.post("/api/remediation/{remediation_id}/reject")
def reject_remediation(
    remediation_id: str
):

    remediation = pending_remediations.get(
        remediation_id
    )

    if not remediation:

        return {
            "status": "error",
            "message": "Remediation not found."
        }

    remediation["status"] = "rejected"

    return {
        "status": "success",
        "message": "Remediation rejected.",
        "remediation": remediation
    }

# ============================================================
# Safe Remediation Executor
# ============================================================

def execute_remediation(remediation):
    """
    Execute only explicitly approved and
    whitelisted remediation actions.
    """

    if remediation.get("status") != "approved":
        return {
            "status": "blocked",
            "message": (
                "Remediation must be approved "
                "before execution."
            )
        }

    action = remediation.get("action", "").lower()

    if "restart" in action and "order-service" in action:

        return {
            "status": "ready",
            "action": "restart_order_service",
            "message": (
                "Restart action passed the safety "
                "checks and is ready for execution."
            )
        }

    if "scale" in action and "order-service" in action:

        return {
            "status": "ready",
            "action": "scale_order_service",
            "message": (
                "Scale action passed the safety "
                "checks and is ready for execution."
            )
        }

    return {
        "status": "blocked",
        "message": (
            "Action is not included in the "
            "approved remediation whitelist."
        )
    }

# ============================================================
# Execute Approved Remediation
# ============================================================

@app.post("/api/remediation/{remediation_id}/execute")
def execute_approved_remediation(remediation_id: str):

    remediation = pending_remediations.get(
        remediation_id
    )

    if not remediation:
        return {
            "status": "error",
            "message": "Remediation not found."
        }

    result = execute_kubernetes_remediation(
        remediation
    )

    if result["status"] == "executed":
        remediation["status"] = "executed"

    return {
        "status": "success",
        "result": result,
        "remediation": remediation
    }


# ============================================================
# Kubernetes Remediation Executor
# ============================================================

def execute_kubernetes_remediation(
    remediation
):
    """
    Execute an approved remediation action
    using the Kubernetes API.

    Only explicitly whitelisted actions are allowed.
    """

    if remediation.get("status") != "approved":
        return {
            "status": "blocked",
            "message": (
                "Remediation must be approved "
                "before Kubernetes execution."
            )
        }

    action = remediation.get(
        "action",
        ""
    ).lower()

    apps_v1 = client.AppsV1Api()

    namespace = "ai-sre"
    deployment = "order-service"

    if (
        "restart" in action
        and "order-service" in action
    ):

        patch = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "ai-sre/restarted-at": (
                                datetime.now(
                                    timezone.utc
                                ).isoformat()
                            )
                        }
                    }
                }
            }
        }

        apps_v1.patch_namespaced_deployment(
            name=deployment,
            namespace=namespace,
            body=patch
        )

        return {
            "status": "executed",
            "action": "restart_order_service",
            "message": (
                "order-service deployment restart "
                "was triggered."
            )
        }

    if (
        "scale" in action
        and "order-service" in action
    ):

        return {
            "status": "blocked",
            "message": (
                "Scaling requires an explicit target "
                "replica count and is not enabled yet."
            )
        }

    return {
        "status": "blocked",
        "message": (
            "Action is not included in the "
            "Kubernetes remediation whitelist."
        )
    }



# ============================================================
# Alertmanager Webhook
# ============================================================

@app.post("/webhook/alertmanager")
def alertmanager_webhook(
    payload: dict,
    background_tasks: BackgroundTasks
):

    global latest_incident


    alerts = payload.get(
        "alerts",
        []
    )


    if not alerts:

        return {

            "status":
                "ignored",

            "message":
                "No alerts received"

        }


    # ========================================================
    # Handle RESOLVED alerts
    # ========================================================

    if payload.get(
        "status"
    ) == "resolved":

        resolved_alert = alerts[0]


        labels = resolved_alert.get(
            "labels",
            {}
        )


        alert_name = labels.get(
            "alertname",
            "UnknownAlert"
        )


        service = labels.get(
            "service",
            "unknown-service"
        )


        severity = labels.get(
            "severity",
            "warning"
        )


        fingerprint = resolved_alert.get(
            "fingerprint"
        )


        if not fingerprint:

            fingerprint = (
                f"{alert_name}:"
                f"{service}:"
                f"{severity}"
            )


        # ----------------------------------------------------
        # Find existing incident
        # ----------------------------------------------------

        incident_record = (
            get_incident_by_fingerprint(
                fingerprint
            )
        )


        if not incident_record:

            return {

                "status":
                    "ignored",

                "message":
                    "No matching incident found",

                "fingerprint":
                    fingerprint

            }


        # ----------------------------------------------------
        # Resolution time
        # ----------------------------------------------------

        resolved_at = resolved_alert.get(
            "endsAt"
        )


        if not resolved_at:

            resolved_at = datetime.now(
                timezone.utc
            ).isoformat()


        # ----------------------------------------------------
        # Mark incident resolved
        # ----------------------------------------------------

        resolve_incident(

            fingerprint,

            resolved_at

        )


        # ----------------------------------------------------
        # Update in-memory incident
        # ----------------------------------------------------

        latest_incident = {

            "status":
                "resolved",

            "incident": {

                "alert_name":
                    alert_name,

                "service":
                    service,

                "severity":
                    severity

            },

            "alert_status":
                "resolved",

            "resolved_at":
                resolved_at,

            "fingerprint":
                fingerprint

        }


        # ----------------------------------------------------
        # Update deduplication state
        # ----------------------------------------------------

        if fingerprint in processed_incidents:

            processed_incidents[
                fingerprint
            ][
                "status"
            ] = "resolved"


        return {

            "status":
                "resolved",

            "message":
                "Incident resolved",

            "alert_name":
                alert_name,

            "service":
                service,

            "severity":
                severity,

            "fingerprint":
                fingerprint,

            "resolved_at":
                resolved_at

        }


    # ========================================================
    # Find FIRING alert
    # ========================================================

    selected_alert = None


    for alert in alerts:

        if alert.get(
            "status"
        ) == "firing":

            selected_alert = alert

            break


    if selected_alert is None:

        return {

            "status":
                "ignored",

            "message":
                "No firing alerts in webhook payload"

        }


    # ========================================================
    # Extract alert information
    # ========================================================

    labels = selected_alert.get(
        "labels",
        {}
    )


    annotations = selected_alert.get(
        "annotations",
        {}
    )


    alert_name = labels.get(
        "alertname",
        "UnknownAlert"
    )


    service = labels.get(
        "service",
        "unknown-service"
    )


    severity = labels.get(
        "severity",
        "warning"
    )


    # ========================================================
    # Fingerprint
    # ========================================================

    fingerprint = selected_alert.get(
        "fingerprint"
    )


    if not fingerprint:

        fingerprint = (
            f"{alert_name}:"
            f"{service}:"
            f"{severity}"
        )


    # ========================================================
    # Deduplication
    # ========================================================

    if fingerprint in processed_incidents:

        return {

            "status":
                "ignored",

            "message":
                "Incident already processed",

            "fingerprint":
                fingerprint

        }


    # ========================================================
    # Mark as processing
    # ========================================================

    processed_incidents[
        fingerprint
    ] = {

        "status":
            "processing",

        "alert_name":
            alert_name,

        "service":
            service,

        "severity":
            severity

    }


    # ========================================================
    # Create IncidentRequest
    # ========================================================

    incident = IncidentRequest(

        alert_name=
            alert_name,

        service=
            service,

        severity=
            severity,

        status=
            selected_alert.get(
                "status"
            ),

        summary=
            annotations.get(
                "summary"
            ),

        description=
            annotations.get(
                "description"
            ),

        starts_at=
            selected_alert.get(
                "startsAt"
            ),

        ends_at=
            selected_alert.get(
                "endsAt"
            ),

        fingerprint=
            fingerprint,

        labels=
            labels,

        annotations=
            annotations

    )


    # ========================================================
    # Save incident
    # ========================================================

    create_incident(

        fingerprint=
            fingerprint,

        alert_name=
            alert_name,

        service=
            service,

        severity=
            severity,

        started_at=
            selected_alert.get(
                "startsAt"
            )

    )


    # ========================================================
    # Update latest incident
    # ========================================================

    latest_incident = {

        "status":
            "investigating",

        "incident": {

            "alert_name":
                alert_name,

            "service":
                service,

            "severity":
                severity

        },

        "annotations":
            annotations,

        "alert_status":
            selected_alert.get(
                "status"
            ),

        "starts_at":
            selected_alert.get(
                "startsAt"
            ),

        "fingerprint":
            fingerprint

    }


    # ========================================================
    # Start background investigation
    # ========================================================

    background_tasks.add_task(

        run_automated_investigation,

        incident,

        fingerprint

    )


    # ========================================================
    # Response
    # ========================================================

    return {

        "status":
            "accepted",

        "message":
            "Incident investigation started",

        "alert_name":
            alert_name,

        "service":
            service,

        "severity":
            severity,

        "fingerprint":
            fingerprint

    }


# ============================================================
# Latest Incident
# ============================================================

@app.get("/api/latest-incident")
def get_latest_incident():

    global latest_incident

    try:

        # If an automated investigation exists
        # in memory, return it.
        if (
            latest_incident
            and latest_incident.get("status") != "idle"
        ):
            return latest_incident


        # Otherwise restore the latest incident
        # from SQLite.
        incidents = get_incidents()

        if not incidents:

            return {
                "status": "idle",
                "message": (
                    "No automated incident investigation yet."
                )
            }


        latest = incidents[0]


        investigation = latest.get(
            "investigation"
        )


        if not investigation:

            return {
                "status": "idle",
                "message": (
                    "No automated incident investigation yet."
                )
            }


        # SQLite stores investigation as JSON text.
        if isinstance(
            investigation,
            str
        ):

            investigation = json.loads(
                investigation
            )


        latest_incident = {

            "status": latest.get(
                "status",
                "unknown"
            ),

            "fingerprint": latest.get(
                "fingerprint"
            ),

            "incident": {

                "id": latest.get("id"),

                "alert_name": latest.get(
                    "alert_name"
                ),

                "service": latest.get(
                    "service"
                ),

                "severity": latest.get(
                    "severity"
                ),

                "status": latest.get(
                    "status"
                )

            },

            "investigation": {

                "status": latest.get(
                    "status",
                    "unknown"
                ),

                "steps": investigation

            }

        }


        return latest_incident


    except Exception as e:

        return {

            "status": "error",

            "message": str(e)

        }

# ============================================================
# Incident History API
# ============================================================

@app.get("/api/incidents")
def incident_history():

    return {

        "status":
            "success",

        "incidents":
            get_incidents()

    }


# ============================================================
# Incident Details API
# ============================================================

@app.get(
    "/api/incidents/{incident_id}"
)
def incident_details(
    incident_id: int
):

    incident = get_incident_by_id(
        incident_id
    )


    if not incident:

        return {

            "status":
                "error",

            "message":
                "Incident not found"

        }


    return {

        "status":
            "success",

        "incident":
            incident

    }


# ============================================================
# Incident Statistics API
# ============================================================

@app.get(
    "/api/incident-stats"
)
def incident_stats():

    stats = get_incident_stats()


    return {

        "status":
            "success",

        "statistics":
            stats

    }


# ============================================================
# Resolve Incident API
# ============================================================

@app.post(
    "/api/incidents/{incident_id}/resolve"
)
def resolve_incident_api(
    incident_id: int
):

    incident = get_incident_by_id(
        incident_id
    )


    if not incident:

        return {

            "status":
                "error",

            "message":
                "Incident not found"

        }


    if incident["status"] == "resolved":

        return {

            "status":
                "success",

            "message":
                "Incident already resolved"

        }


    resolved_at = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )


    resolve_incident(

        incident["fingerprint"],

        resolved_at

    )


    return {

        "status":
            "success",

        "message":
            "Incident resolved",

        "incident_id":
            incident_id,

        "resolved_at":
            resolved_at

    }


# ============================================================
# Analytics API
# ============================================================

@app.get("/api/analytics")
def analytics():

    return {

        "status": "success",

        "analytics": {

            "incident_trends": get_incident_trends(),

            "severity_distribution": get_incidents_by_severity(),

            "service_distribution": get_incidents_by_service(),

            "resolution_rate": get_resolution_rate(),

            "recurring_incidents": get_recurring_incidents(),

            "mttr_trends": get_mttr_trends()

        }

    }


# ============================================================
# Observability API
# ============================================================

@app.get("/api/observability")
def observability():

    return {

        "status": "success",

        "service": "order-service",

        "observability": get_service_observability()

    }


# ============================================================
# Kubernetes Health API
# ============================================================

@app.get("/api/kubernetes-health")
def kubernetes_health():

    return {

        "status": "success",

        "service": "order-service",

        "kubernetes": get_kubernetes_health()

    }


# ============================================================
# Observability Overview API
# ============================================================

@app.get("/api/observability-overview")
def observability_overview():

    return {

        "status": "success",

        "service": "order-service",

        "service_observability": get_service_observability(),

        "kubernetes_health": get_kubernetes_health()

    }


# ============================================================
# Dashboard Endpoint
# ============================================================

@app.get("/dashboard",response_class=HTMLResponse)
def dashboard(request: Request):

    return templates.TemplateResponse(

        request=request,

        name="dashboard.html"

    )