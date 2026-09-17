from app.main import AlertContext


def normalize_alert(alert: dict) -> AlertContext:
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})

    return AlertContext(
        alert_name=labels.get("alertname", "UnknownAlert"),
        service=labels.get("service"),
        severity=labels.get("severity"),
        status=alert.get("status"),
        description=annotations.get("description"),
        summary=annotations.get("summary"),
        labels=labels,
        annotations=annotations
    )