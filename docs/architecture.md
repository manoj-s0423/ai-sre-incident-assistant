# AI-SRE Incident Assistant — Architecture

## 1. Overview

The AI-SRE Incident Assistant is a cloud-native SRE platform designed to
automate incident detection, investigation, root cause analysis, and
controlled Kubernetes remediation.

The platform combines:

- FastAPI
- Docker
- Kubernetes
- Prometheus
- Alertmanager
- PagerDuty
- Claude AI
- SQLite
- Kubernetes API
- SRE Dashboard

The system follows an incident-response workflow where monitoring systems
detect an issue, Alertmanager routes the alert, the AI-SRE backend collects
real operational evidence, Claude investigates the incident, and the platform
presents the result to an engineer.

Potentially disruptive remediation actions require explicit human approval
before Kubernetes changes are executed.

---

# 2. High-Level Architecture

```text
                                ┌─────────────────────────┐
                                │     Kubernetes Cluster  │
                                │                         │
                                │     ai-sre namespace    │
                                │                         │
                                │  ┌───────────────────┐  │
                                │  │   order-service   │  │
                                │  │     FastAPI       │  │
                                │  │                   │  │
                                │  │ /health           │  │
                                │  │ /orders           │  │
                                │  │ /slow             │  │
                                │  │ /error            │  │
                                │  │ /metrics          │  │
                                │  └─────────┬─────────┘  │
                                │            │            │
                                └────────────┼────────────┘
                                             │
                                             │ Metrics
                                             ▼
                                ┌─────────────────────────┐
                                │       Prometheus        │
                                │                         │
                                │ Metrics Collection      │
                                │ Alert Evaluation        │
                                └────────────┬────────────┘
                                             │
                                             │ Alerts
                                             ▼
                                ┌─────────────────────────┐
                                │      Alertmanager       │
                                │                         │
                                │ Alert Routing           │
                                │ Grouping                │
                                │ Notification            │
                                └───────────┬─────────────┘
                                            │
                         ┌──────────────────┴──────────────────┐
                         │                                     │
                         ▼                                     ▼
              ┌─────────────────────┐              ┌──────────────────────┐
              │      PagerDuty      │              │      AI-SRE API      │
              │                     │              │       FastAPI        │
              │ Incident Management │              │                      │
              └─────────────────────┘              └──────────┬───────────┘
                                                               │
                                                               │
                                          ┌────────────────────┼──────────────────┐
                                          │                    │                  │
                                          ▼                    ▼                  ▼
                                ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
                                │   Prometheus     │ │    Kubernetes    │ │      SQLite      │
                                │                  │ │                  │ │                  │
                                │ CPU              │ │ Pods             │ │ Incidents        │
                                │ Memory           │ │ Logs             │ │ RCA              │
                                │ P95 Latency      │ │ Events           │ │ Evidence         │
                                │ Error Rate       │ │ Deployments      │ │ Investigation    │
                                │ Request Rate     │ │ ReplicaSets      │ │ History          │
                                └────────┬─────────┘ └────────┬─────────┘ └──────────────────┘
                                         │                    │
                                         └──────────┬─────────┘
                                                    │
                                                    │ Evidence
                                                    ▼
                                          ┌─────────────────────┐
                                          │      Claude AI      │
                                          │                     │
                                          │ Investigation       │
                                          │ Evidence Analysis   │
                                          │ Root Cause Analysis │
                                          │ Next Tool Selection │
                                          └──────────┬──────────┘
                                                     │
                                                     │ Investigation Result
                                                     ▼
                                          ┌─────────────────────┐
                                          │    SRE Dashboard    │
                                          │                     │
                                          │ Incident            │
                                          │ RCA                 │
                                          │ Investigation       │
                                          │ Observability       │
                                          │ Analytics           │
                                          │ Incident History    │
                                          │ Remediation         │
                                          └──────────┬──────────┘
                                                     │
                                                     │ Human Approval
                                                     ▼
                                          ┌─────────────────────┐
                                          │  Remediation Safety │
                                          │       Gate          │
                                          └──────────┬──────────┘
                                                     │
                                                     │ Approved Action
                                                     ▼
                                          ┌─────────────────────┐
                                          │   Kubernetes API    │
                                          │                     │
                                          │ Approved Remediation│
                                          └──────────┬──────────┘
                                                     │
                                                     ▼
                                          ┌─────────────────────┐
                                          │   order-service     │
                                          │    Deployment       │
                                          └─────────────────────┘