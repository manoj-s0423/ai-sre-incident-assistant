# AI-Powered SRE Incident Response & Root Cause Analysis Platform

An AI-powered Site Reliability Engineering platform that detects production incidents, collects Kubernetes and Prometheus evidence, performs interactive root cause analysis using Claude, persists incident history, visualizes investigations, and provides a human-approved remediation workflow.

---

## 🚀 Project Overview

Traditional incident response often requires an engineer to manually:

* Identify the affected service
* Check Prometheus metrics
* Inspect Kubernetes pods
* Review application logs
* Check Kubernetes events
* Review deployment history
* Determine the root cause
* Document the incident
* Decide whether remediation is safe

This project automates much of that workflow using AI while keeping **human approval in the loop for high-risk remediation actions**.

The system follows this lifecycle:

```text
Detect
   ↓
Collect Evidence
   ↓
AI Investigation
   ↓
Root Cause Analysis
   ↓
Persist Incident
   ↓
Dashboard
   ↓
Human Approval
   ↓
Safe Remediation
```

---

# 🏗️ Architecture

```text
                         ┌─────────────────────┐
                         │    order-service    │
                         │       FastAPI       │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │     Prometheus      │
                         │ Metrics + Alerting  │
                         └──────────┬──────────┘
                                    │
                              Alert fires
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │     Alertmanager    │
                         └───────┬─────┬───────┘
                                 │     │
                    ┌────────────┘     └────────────┐
                    ▼                               ▼
             ┌─────────────┐                ┌──────────────┐
             │  PagerDuty  │                │   AI-SRE API │
             └─────────────┘                └──────┬───────┘
                                                    │
                                                    ▼
                                           ┌─────────────────┐
                                           │ Evidence Engine │
                                           │                 │
                                           │ Prometheus      │
                                           │ Kubernetes      │
                                           │ Logs            │
                                           │ Events          │
                                           │ Deployments     │
                                           └────────┬────────┘
                                                    │
                                                    ▼
                                           ┌─────────────────┐
                                           │    Claude AI    │
                                           │                 │
                                           │ Investigate     │
                                           │ Select Tool     │
                                           │ Analyze         │
                                           │ Determine RCA   │
                                           └────────┬────────┘
                                                    │
                                                    ▼
                                           ┌─────────────────┐
                                           │    SQLite DB    │
                                           │ Incident History│
                                           └────────┬────────┘
                                                    │
                                                    ▼
                                           ┌─────────────────┐
                                           │  SRE Dashboard  │
                                           └────────┬────────┘
                                                    │
                                             Remediation
                                                    │
                                                    ▼
                                           ┌─────────────────┐
                                           │ Human Approval  │
                                           └────────┬────────┘
                                                    │
                                               Approved
                                                    │
                                                    ▼
                                           ┌─────────────────┐
                                           │ Kubernetes API  │
                                           │ Safe Executor   │
                                           └─────────────────┘
```

---

# 🔄 Incident Flow

```text
Application
     │
     ▼
Prometheus
     │
     ▼
Alert Rule
     │
     ▼
Alertmanager
     │
     ├──────────────► PagerDuty
     │
     ▼
AI-SRE Webhook
     │
     ▼
Create / Update Incident
     │
     ▼
Collect Evidence
     │
     ├── Prometheus metrics
     ├── Pod logs
     ├── Previous logs
     ├── Pod details
     ├── Kubernetes events
     └── Deployment history
     │
     ▼
Claude AI
     │
     ▼
Select Next Investigation Tool
     │
     ▼
Backend Executes Read-Only Tool
     │
     ▼
Evidence Returned
     │
     ▼
Claude Analysis
     │
     ├── Root Cause Identified
     ├── Incident Resolved
     └── Insufficient Evidence
     │
     ▼
SQLite
     │
     ▼
Dashboard
```

---

# 🤖 AI Investigation

The AI investigation engine uses a bounded tool-based investigation loop.

```text
Alert
  ↓
Collect evidence
  ↓
Claude selects investigation tool
  ↓
Backend executes safe read-only tool
  ↓
Real evidence returned
  ↓
Claude analyzes evidence
  ↓
Claude selects next tool
  ↓
...
  ↓
Final decision
```

The investigation is limited to a configured maximum number of steps.

## Investigation Tools

The platform currently supports:

```text
get_pod_logs
get_previous_logs
get_pod_details
get_kubernetes_events
get_service_observability
get_deployment_history
```

The AI cannot execute arbitrary shell commands.

Only explicitly allowed investigation tools can be executed.

---

# 🔍 Observability

The platform collects service-level and Kubernetes-level observability data.

## Application Metrics

```text
HTTP request rate
HTTP 5xx error rate
P95 latency
```

## Kubernetes Metrics

```text
CPU usage
Memory usage
Pod restarts
Pod health
Deployment health
Pod availability
Kubernetes events
```

---

# 📊 Prometheus

Prometheus monitors the `order-service` application through a Kubernetes `ServiceMonitor`.

The project includes alert rules for:

```text
HighOrderServiceP95Latency
HighOrderServiceCPU
HighOrderServiceMemory
OrderServicePodRestarts
OrderServicePodUnavailable
HighHTTP5xxErrorRate
```

Example alert:

```yaml
- alert: HighHTTP5xxErrorRate
  expr: |
    (
      sum(rate(http_requests_total{status=~"5.."}[5m]))
      /
      sum(rate(http_requests_total[5m]))
    ) * 100 > 5
  for: 2m
```

---

# 🚨 Alertmanager

Alertmanager receives alerts from Prometheus and routes them to:

```text
                 Alertmanager
                    /     \
                   /       \
                  ▼         ▼
            PagerDuty     AI-SRE
                           Webhook
```

Resolved alerts are also sent to the AI-SRE backend so that incidents can automatically transition to a resolved state.

---

# 📟 PagerDuty

PagerDuty is integrated into the alerting pipeline for incident notification.

The architecture is:

```text
Prometheus
    ↓
Alertmanager
    ↓
PagerDuty
```

At the same time, Alertmanager sends the incident to the AI-SRE webhook:

```text
Alertmanager
     ↓
AI-SRE
```

This allows the project to demonstrate both traditional incident management and AI-assisted incident investigation.

---

# 🧠 Root Cause Analysis

The platform does not rely only on the initial alert.

Claude receives evidence collected from multiple sources and determines the next investigation step.

For example:

```text
P95 latency increased
        ↓
Check service observability
        ↓
CPU normal
Memory normal
Error rate normal
        ↓
Check logs
        ↓
Repeated /slow requests
        ↓
Check deployment history
        ↓
Application-level latency identified
```

This provides an evidence-driven RCA workflow.

---

# 🧪 Example P95 Investigation

During testing, the platform detected a high P95 latency incident.

Observed evidence included:

```text
P95 latency ≈ 7.2 seconds
HTTP error rate = 0%
CPU usage = low
Memory usage = normal
Pods = 2/2 healthy
Repeated /slow requests = 200
No relevant Kubernetes events
```

The AI then inspected deployment history and identified the `/slow` endpoint as the application-level source of the latency.

This demonstrates how the platform correlates:

```text
Metrics
  +
Logs
  +
Kubernetes Health
  +
Deployment History
  =
AI-assisted RCA
```

---

# 💾 Incident Persistence

Incident data is stored in SQLite.

The database contains information such as:

```text
fingerprint
alert_name
service
severity
status
started_at
resolved_at
incident_summary
root_cause
affected_component
impact
confidence
evidence
recommended_actions
additional_evidence_needed
investigation
root_cause_identified
conclusion
```

Alert fingerprints are used to prevent duplicate incident records.

---

# 🖥️ SRE Dashboard

The dashboard provides a centralized view of the incident lifecycle.

## Incident Information

```text
Alert
Service
Severity
Status
```

## RCA

```text
Incident Summary
Root Cause
Affected Component
Observations
Evidence
Impact
Recommended Actions
Additional Evidence
AI Confidence
```

## AI Investigation Timeline

Each investigation step displays:

```text
Step
Status
Tool
Target
Risk
Approval
AI Action
Reason
Expected Result
Evidence Returned
```

## Live Observability

```text
CPU Usage
Memory Usage
P95 Latency
Error Rate
Request Rate
Pod Restarts
Pod Status
Deployment Health
Pod Health
```

## SRE Analytics

```text
Incident Trends
MTTR Trend
Severity Distribution
Incidents by Service
Resolution Rate
Recurring Incidents
Incident History
```

---

# 🛡️ Human Approval & Safe Remediation

A key design principle of the project is:

> **AI can recommend remediation, but high-risk infrastructure changes require human approval.**

The remediation workflow is:

```text
AI Recommendation
       ↓
Risk Classification
       ↓
High Risk
       ↓
Pending Approval
       ↓
Human Approval
       ↓
Safety Gate
       ↓
Kubernetes Executor
       ↓
Execution
```

## Risk Levels

```text
Low
Medium
High
```

High-risk actions include operations such as:

```text
Restart pod
Restart deployment
Rollback deployment
Scale deployment
Delete deployment
```

These actions require approval.

---

# 🔐 Safety Controls

The system implements several safety mechanisms.

## Investigation Safety

```text
Read-only tools
Tool whitelist
Maximum investigation steps
No arbitrary shell execution
```

## Remediation Safety

```text
Risk classification
Human approval
Approval state validation
Action whitelist
Kubernetes API execution
```

An unapproved remediation is blocked.

A rejected remediation cannot be executed.

An action outside the Kubernetes remediation whitelist is blocked.

---

# ☸️ Kubernetes Remediation

The current controlled Kubernetes executor supports restarting the `order-service` deployment.

The restart is performed by updating the Deployment pod template with a timestamp annotation.

Conceptually:

```text
Approved Remediation
        ↓
Kubernetes API
        ↓
Patch Deployment
        ↓
New Pod Template
        ↓
Rolling Restart
        ↓
New Pods
        ↓
2/2 Pods Healthy
```

Scaling is intentionally not enabled yet because it requires an explicit replica-count workflow.

---

# 🧰 Technology Stack

| Area                 | Technology               |
| -------------------- | ------------------------ |
| Programming Language | Python                   |
| Backend              | FastAPI                  |
| AI                   | Claude                   |
| Containerization     | Docker                   |
| Orchestration        | Kubernetes               |
| Local Kubernetes     | kind                     |
| Package Management   | Helm                     |
| Metrics              | Prometheus               |
| Visualization        | Grafana                  |
| Alerting             | Alertmanager             |
| Incident Management  | PagerDuty                |
| Database             | SQLite                   |
| Frontend             | HTML / CSS / JavaScript  |
| Kubernetes Client    | Python Kubernetes Client |
| Infrastructure       | Terraform                |
| Cloud                | AWS                      |
| Version Control      | Git / GitHub             |

---

# 📁 Project Structure

```text
ai-sre-incident-assistant/
│
├── application/
│
├── kubernetes/
│
├── monitoring/
│   ├── prometheus/
│   ├── grafana/
│   └── alertmanager/
│
├── ai-sre/
│   ├── app/
│   │   ├── main.py
│   │   ├── database.py
│   │   ├── observability.py
│   │   ├── ai_response.py
│   │   ├── investigation_tools.py
│   │   └── alert_parser.py
│   │
│   ├── templates/
│   │   └── dashboard.html
│   │
│   ├── incidents.db
│   └── requirements.txt
│
├── terraform/
├── incidents/
├── runbooks/
├── docs/
└── .github/
```

---

# 🚀 Local Setup

## Prerequisites

Install:

```text
Docker
kubectl
kind
Helm
Python 3
Git
```

Optional:

```text
Terraform
AWS CLI
```

---

## 1. Start Kubernetes

Create a kind cluster:

```bash
kind create cluster --name devops-lab
```

Verify:

```bash
kubectl get nodes
```

---

## 2. Create Namespace

```bash
kubectl create namespace ai-sre
```

---

## 3. Build Application

```bash
docker build -t order-service:1.2 ./application
```

Load the image into kind:

```bash
kind load docker-image order-service:1.2 --name devops-lab
```

Deploy:

```bash
kubectl apply -f kubernetes/
```

Verify:

```bash
kubectl get pods -n ai-sre
kubectl get deployment -n ai-sre
kubectl get svc -n ai-sre
```

---

# 📈 Install Monitoring

Add the Prometheus Community Helm repository:

```bash
helm repo add prometheus-community \
  https://prometheus-community.github.io/helm-charts

helm repo update
```

Install kube-prometheus-stack:

```bash
helm upgrade --install monitoring \
  prometheus-community/kube-prometheus-stack \
  -n monitoring \
  --create-namespace
```

Verify:

```bash
kubectl get pods -n monitoring
```

---

# 🐍 Start AI-SRE Backend

Move into the AI-SRE application:

```bash
cd ai-sre
```

Create a virtual environment:

```bash
python3 -m venv venv
```

Activate it:

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure the Claude API key:

```bash
export ANTHROPIC_API_KEY="YOUR_API_KEY"
```

Do not commit the API key to Git.

Start FastAPI:

```bash
uvicorn app.main:app \
  --reload \
  --host 0.0.0.0 \
  --port 8001
```

The AI-SRE backend will be available on:

```text
http://localhost:8001
```

---

# 🔭 Prometheus Access

For local Prometheus access:

```bash
kubectl port-forward \
  -n monitoring \
  svc/monitoring-kube-prometheus-prometheus \
  9091:9090
```

Prometheus:

```text
http://127.0.0.1:9091
```

---

# 🧪 Testing

## Test HTTP 500 Incident

Generate errors:

```bash
curl http://localhost:8000/error
```

Generate multiple errors:

```bash
for i in {1..50}; do
    curl -s http://localhost:8000/error > /dev/null
done
```

Then check:

```bash
kubectl get pods -n ai-sre
```

Prometheus should eventually trigger:

```text
HighHTTP5xxErrorRate
```

The alert is routed through:

```text
Prometheus
    ↓
Alertmanager
    ↓
PagerDuty
    ↓
AI-SRE Webhook
```

---

# 🐌 Test High Latency

Generate slow requests:

```bash
for i in {1..20}; do
    curl -s http://localhost:8000/slow > /dev/null
done
```

This can trigger:

```text
HighOrderServiceP95Latency
```

---

# 🔧 Test Remediation

Create a remediation:

```bash
curl -X POST \
"http://localhost:8001/api/remediation?action=Restart%20the%20order-service%20deployment&reason=Controlled%20remediation%20test&risk=Low"
```

The backend classifies the action based on the actual action rather than trusting the supplied risk value.

Expected result:

```json
{
  "risk": "High",
  "requires_approval": true,
  "status": "pending"
}
```

Approve it:

```bash
curl -X POST \
http://localhost:8001/api/remediation/YOUR_ID/approve
```

Execute it:

```bash
curl -X POST \
http://localhost:8001/api/remediation/YOUR_ID/execute
```

Watch the pods:

```bash
kubectl get pods -n ai-sre -w
```

The deployment should restart while maintaining the desired replica count.

---

# 🔌 API Endpoints

## Investigation

```text
POST /investigate
```

Starts a manual incident investigation.

---

## Latest Incident

```text
GET /api/latest-incident
```

Returns the latest incident and investigation state.

---

## Incident History

```text
GET /api/incidents
```

Returns persisted incidents.

---

## Incident Statistics

```text
GET /api/incident-stats
```

Returns:

```text
Total incidents
Active incidents
Resolved incidents
MTTR
```

---

## Analytics

```text
GET /api/analytics
```

Returns:

```text
Incident trends
MTTR trends
Severity distribution
Service distribution
Resolution rate
Recurring incidents
```

---

## Observability

```text
GET /api/observability-overview
```

Returns:

```text
CPU
Memory
Request rate
P95 latency
Error rate
Pod restarts
Pod health
Deployment health
```

---

## Alertmanager Webhook

```text
POST /webhook/alertmanager
```

Receives Alertmanager incidents.

---

## Remediation

```text
POST /api/remediation

GET /api/remediation

POST /api/remediation/{remediation_id}/approve

POST /api/remediation/{remediation_id}/reject

POST /api/remediation/{remediation_id}/execute
```

---

# 📚 Runbooks

Runbooks are stored under:

```text
runbooks/
```

Current runbooks include:

```text
high-latency.md
high-cpu.md
high-memory.md
pod-restarts.md
pod-availability.md
high-http-error-rate.md
```

Prometheus alerts reference the appropriate runbook through alert annotations.

---

# 📊 Incident Lifecycle

The complete incident lifecycle is:

```text
1. Application generates telemetry
                ↓
2. Prometheus collects metrics
                ↓
3. Prometheus evaluates alert rules
                ↓
4. Alertmanager receives alert
                ↓
5. PagerDuty receives notification
                ↓
6. AI-SRE receives webhook
                ↓
7. Incident created / deduplicated
                ↓
8. Evidence collected
                ↓
9. Claude selects investigation tools
                ↓
10. Kubernetes / Prometheus evidence returned
                ↓
11. Claude analyzes evidence
                ↓
12. RCA result generated
                ↓
13. Incident persisted
                ↓
14. Dashboard updated
                ↓
15. Remediation may be recommended
                ↓
16. High-risk remediation requires approval
                ↓
17. Safety gate validates action
                ↓
18. Kubernetes executor performs action
                ↓
19. Monitoring verifies service health
```

---

# 🔐 Security Considerations

The project follows a least-privilege approach for AI operations.

### AI Investigation

The AI receives access to controlled investigation capabilities rather than arbitrary shell execution.

### Remediation

Infrastructure changes require:

```text
Risk Classification
        ↓
Human Approval
        ↓
Safety Validation
        ↓
Whitelisted Kubernetes Action
```

### Secrets

API keys and integration secrets should be provided through environment variables or Kubernetes Secrets.

Never commit secrets to Git.

Example:

```bash
export ANTHROPIC_API_KEY="YOUR_API_KEY"
```

---

# 📈 SRE Concepts Demonstrated

This project demonstrates practical SRE concepts including:

```text
Incident Response
Root Cause Analysis
Monitoring
Observability
Alerting
MTTR
Incident History
Runbooks
Service Health
Error Rate
Latency
Resource Utilization
Human-in-the-Loop Remediation
Safe Automation
```

---

# ☸️ Kubernetes Concepts Demonstrated

```text
Pods
Deployments
Services
Namespaces
ReplicaSets
ServiceMonitor
PrometheusRule
Kubernetes Events
Kubernetes API
Deployment History
Rolling Restart
```

---

# 🛠️ DevOps Concepts Demonstrated

```text
Docker
Kubernetes
Helm
kind
Prometheus
Grafana
Alertmanager
PagerDuty
FastAPI
Terraform
AWS
Git
GitHub
```

---

# 🤖 AI Engineering Concepts Demonstrated

```text
LLM Integration
Claude API
Tool-based AI Investigation
Structured AI Responses
Evidence-driven RCA
Bounded Investigation
Investigation State
Human-in-the-Loop
AI Safety Controls
```

---

# 🔮 Future Improvements

Potential future improvements include:

* PostgreSQL instead of SQLite
* Redis for distributed incident state
* Authentication and RBAC
* Kubernetes RBAC for the remediation executor
* Slack / Microsoft Teams notifications
* Richer Grafana dashboards
* SLO and error-budget tracking
* Multi-service RCA
* Automated runbook retrieval
* Change/deployment correlation
* Remediation audit history
* Configurable remediation policies
* Explicit scaling workflows
* CI/CD pipeline
* Automated integration tests
* AWS production deployment

---

# ✅ Project Status

```text
Kubernetes Application             ✅
Prometheus                         ✅
Grafana                            ✅
Alertmanager                       ✅
PagerDuty Integration              ✅
AI-SRE Webhook                     ✅
Claude Integration                 ✅
Observability Engine               ✅
Investigation Tools                ✅
Interactive AI Investigation       ✅
SQLite Incident Persistence        ✅
Incident Dashboard                 ✅
Incident History                   ✅
SRE Analytics                      ✅
Incident Recovery                  ✅
Risk Classification                ✅
Human Approval                     ✅
Safety Gate                        ✅
Kubernetes Remediation Executor    ✅
Dashboard Remediation UI           ✅
```

---

# 👨‍💻 Project Focus

This project was designed to demonstrate practical experience in:

```text
Cloud-Native Engineering
DevOps
Site Reliability Engineering
Kubernetes
Observability
Incident Response
AI-assisted RCA
Production Troubleshooting
Infrastructure Automation
Safe Remediation
```
