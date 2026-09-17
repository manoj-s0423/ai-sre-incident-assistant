from pydantic import BaseModel


class AlertContext(BaseModel):
    alert_name: str
    service: str | None = None
    severity: str | None = None
    status: str | None = None
    description: str | None = None
    summary: str | None = None
    labels: dict = {}
    annotations: dict = {}


class AlertmanagerWebhook(BaseModel):
    status: str
    alerts: list[dict]


class IncidentRequest(BaseModel):
    alert_name: str
    service: str
    severity: str

    status: str | None = None
    summary: str | None = None
    description: str | None = None

    starts_at: str | None = None
    ends_at: str | None = None

    fingerprint: str | None = None

    labels: dict = {}
    annotations: dict = {}