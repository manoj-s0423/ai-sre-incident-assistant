## Architecture

```text
                         ┌──────────────────────┐
                         │    order-service     │
                         │      FastAPI         │
                         └──────────┬───────────┘
                                    │
                         Metrics + Application
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │     Prometheus       │
                         │  Metrics & Alerts    │
                         └──────────┬───────────┘
                                    │
                              Alert Rules
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │    Alertmanager      │
                         └───────┬───────┬──────┘
                                 │       │
                    ┌────────────┘       └─────────────┐
                    ▼                                  ▼
          ┌─────────────────┐                ┌─────────────────┐
          │    PagerDuty    │                │    AI-SRE API   │
          │ Incident Alert  │                │    FastAPI      │
          └─────────────────┘                └────────┬────────┘
                                                       │
                                                Collect Evidence
                                                       │
                                                       ▼
                                             ┌──────────────────┐
                                             │    Kubernetes    │
                                             │ Logs / Events /  │
                                             │ Pods / Deploy.   │
                                             └────────┬─────────┘
                                                      │
                                                      ▼
                                             ┌──────────────────┐
                                             │   Claude AI      │
                                             │ Investigation +  │
                                             │      RCA         │
                                             └────────┬─────────┘
                                                      │
                                                      ▼
                                             ┌──────────────────┐
                                             │ SQLite Incident  │
                                             │     History      │
                                             └────────┬─────────┘
                                                      │
                                                      ▼
                                             ┌──────────────────┐
                                             │ SRE Dashboard    │
                                             │ RCA / Metrics /  │
                                             │ Timeline / Logs  │
                                             └────────┬─────────┘
                                                      │
                                                Human Approval
                                                      │
                                                      ▼
                                             ┌──────────────────┐
                                             │ Kubernetes       │
                                             │ Remediation      │
                                             └──────────────────┘