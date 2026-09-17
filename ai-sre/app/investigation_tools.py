# This file contains only safe and read-only investigation operations.
# Claude wil not be allowed to execute arbitary shell commands.

from kubernetes import client, config

from app.observability import (
    get_service_observability,
)


config.load_kube_config()

v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()


NAMESPACE = "ai-sre"

# Why it is important to have tools?
# It would be dangerous. because it will run this arbitrary command --subprocess.run(...)
# Instead Claude can select only from our approved tools:

def get_pod_logs(pod_name: str):
    try:
        logs = v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=NAMESPACE,
            tail_lines=50
        )

        return {
            "tool": "get_pod_logs",
            "pod": pod_name,
            "logs": logs
        }

    except Exception as e:

        return {
            "tool": "get_pod_logs",
            "pod": pod_name,
            "error": str(e)
        }


def get_previous_logs(pod_name: str):
    try:
        logs = v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=NAMESPACE,
            previous=True,
            tail_lines=50
        )

        return {
            "tool": "get_previous_logs",
            "pod": pod_name,
            "logs": logs
        }

    except Exception as e:

        return {
            "tool": "get_previous_logs",
            "pod": pod_name,
            "error": str(e)
        }


def get_pod_details(pod_name: str):
    try:
        pod = v1.read_namespaced_pod(
            name=pod_name,
            namespace=NAMESPACE
        )

        container_states = []

        for container in pod.status.container_statuses or []:

            last_state = container.last_state

            termination = None

            if last_state and last_state.terminated:

                termination = {
                    "reason": last_state.terminated.reason,
                    "exit_code": last_state.terminated.exit_code,
                    "started_at": (
                        last_state.terminated.started_at.isoformat()
                        if last_state.terminated.started_at
                        else None
                    ),
                    "finished_at": (
                        last_state.terminated.finished_at.isoformat()
                        if last_state.terminated.finished_at
                        else None
                    )
                }

            container_states.append({
                "name": container.name,
                "restart_count": container.restart_count,
                "ready": container.ready,
                "last_termination": termination
            })

        return {
            "tool": "get_pod_details",
            "pod": pod_name,
            "phase": pod.status.phase,
            "containers": container_states
        }

    except Exception as e:

        return {
            "tool": "get_pod_details",
            "pod": pod_name,
            "error": str(e)
        }

def get_deployment_history(deployment_name: str):
    try:
        deployment = apps_v1.read_namespaced_deployment(
            name=deployment_name,
            namespace=NAMESPACE
        )

        # Current deployment state
        current_state = {
            "generation": deployment.metadata.generation,
            "observed_generation": deployment.status.observed_generation,
            "image": deployment.spec.template.spec.containers[0].image,
            "replicas": deployment.spec.replicas,
            "available_replicas": deployment.status.available_replicas or 0,
            "updated_replicas": deployment.status.updated_replicas or 0,
            "ready_replicas": deployment.status.ready_replicas or 0,
            "creation_timestamp": (
                deployment.metadata.creation_timestamp.isoformat()
                if deployment.metadata.creation_timestamp
                else None
            )
        }

        # ReplicaSets belonging to this deployment
        replica_sets = apps_v1.list_namespaced_replica_set(
            namespace=NAMESPACE,
            label_selector=f"app={deployment_name}"
        )

        replica_set_history = []

        for rs in replica_sets.items:

            replica_set_history.append({
                "name": rs.metadata.name,
                "revision": (
                    rs.metadata.annotations.get(
                        "deployment.kubernetes.io/revision"
                    )
                    if rs.metadata.annotations
                    else None
                ),
                "created_at": (
                    rs.metadata.creation_timestamp.isoformat()
                    if rs.metadata.creation_timestamp
                    else None
                ),
                "replicas": rs.spec.replicas or 0,
                "available_replicas": (
                    rs.status.available_replicas or 0
                ),
                "image": (
                    rs.spec.template.spec.containers[0].image
                    if rs.spec.template.spec.containers
                    else None
                )
            })

        # Sort oldest -> newest
        replica_set_history.sort(
            key=lambda x: x["created_at"] or ""
        )

        return {
            "tool": "get_deployment_history",
            "deployment": deployment_name,
            "current_state": current_state,
            "replica_set_history": replica_set_history
        }

    except Exception as e:
        return {
            "tool": "get_deployment_history",
            "deployment": deployment_name,
            "error": str(e)
        }

def get_kubernetes_events():
    try:

        events = v1.list_namespaced_event(
            namespace=NAMESPACE
        )

        event_data = []

        for event in events.items:

            event_data.append({
                "type": event.type,
                "reason": event.reason,
                "message": event.message,
                "object": (
                    event.involved_object.name
                    if event.involved_object
                    else None
                ),
                "timestamp": (
                    event.last_timestamp.isoformat()
                    if event.last_timestamp
                    else None
                )
            })

        return {
            "tool": "get_kubernetes_events",
            "events": event_data[-20:]
        }

    except Exception as e:

        return {
            "tool": "get_kubernetes_events",
            "error": str(e)
        }


def get_observability():
    try:

        return {
            "tool": "get_service_observability",
            "observability": get_service_observability()
        }

    except Exception as e:

        return {
            "tool": "get_service_observability",
            "error": str(e)
        }


def execute_investigation_tool(
    tool: str,
    target: str | None = None
):
    if tool == "get_pod_logs":

        if not target:
            return {
                "error": "pod name is required"
            }

        return get_pod_logs(target)

    if tool == "get_previous_logs":

        if not target:
            return {
                "error": "pod name is required"
            }

        return get_previous_logs(target)

    if tool == "get_pod_details":

        if not target:
            return {
                "error": "pod name is required"
            }

        return get_pod_details(target)

    if tool == "get_deployment_history":

        if not target:
            return {
                "error": "deployment name is required"
            }

        return get_deployment_history(target)

    if tool == "get_kubernetes_events":

        return get_kubernetes_events()

    if tool == "get_service_observability":

        return get_observability()

    return {
        "error": f"Unknown investigation tool: {tool}"
    }
