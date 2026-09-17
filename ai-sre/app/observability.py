import requests
from kubernetes import client, config


PROMETHEUS_URL = "http://127.0.0.1:9091"

config.load_kube_config()  
v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()


def query_prometheus(query):
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

        results = data["data"]["result"]

        if not results:
            return None

        return results[0]["value"][1]

    except Exception as e:
        return f"Prometheus query failed: {e}"






def get_cpu_usage():
    query = """
    sum(
        rate(
            container_cpu_usage_seconds_total{
                namespace="ai-sre",
                pod=~"order-service-.*",
                container!="POD",
                container!=""
            }[5m]
        )
    )
    """

    return query_prometheus(query)


def get_memory_usage():
    query = """
    sum(
        container_memory_working_set_bytes{
            namespace="ai-sre",
            pod=~"order-service-.*",
            container!="POD",
            container!=""
        }
    )
    """

    return query_prometheus(query)


def get_pod_restarts():
    query = """
    sum(
        kube_pod_container_status_restarts_total{
            namespace="ai-sre",
            pod=~"order-service-.*"
        }
    )
    """

    return query_prometheus(query)


def get_p95_latency():
    query = """
    histogram_quantile(
        0.95,
        sum(
            rate(
                http_request_duration_seconds_bucket{
                    endpoint!="/metrics"
                }[5m]
            )
        ) by (le)
    )
    """

    return query_prometheus(query)


def get_error_rate():
    query = """
    (
        sum(
            rate(
                http_requests_total{
                    status=~"5.."
                }[5m]
            )
        )
        /
        sum(
            rate(
                http_requests_total[5m]
            )
        )
    ) * 100
    """

    return query_prometheus(query)

def get_request_rate():

    query = """
    sum(
        rate(
            http_requests_total[5m]
        )
    )
    """

    result = query_prometheus(query)

    if result is None:
        return None

    return result
def get_service_observability():

    cpu = get_cpu_usage()
    memory = get_memory_usage()
    restarts = get_pod_restarts()
    p95_latency = get_p95_latency()
    error_rate = get_error_rate()
    request_rate = get_request_rate()


    if cpu is not None:
        cpu = float(cpu)


    if memory is not None:
        memory = float(memory)


    if restarts is not None:
        restarts = int(float(restarts))


    if p95_latency is not None:
        p95_latency = float(p95_latency)


    if error_rate is not None:
        error_rate = float(error_rate)


    if request_rate is not None:
        request_rate = float(request_rate)


    return {

        "cpu_cores": cpu,

        "memory_bytes": memory,

        "pod_restarts": restarts,

        "p95_latency_seconds": p95_latency,

        "error_rate_percent": error_rate,

        "request_rate_per_second": request_rate,

    }

def get_pod_health():
    try:
        pods = v1.list_namespaced_pod(
            namespace="ai-sre",
            label_selector="app=order-service"
        )

        pod_details = []

        for pod in pods.items:
            ready_containers = 0
            total_containers = len(
                pod.spec.containers
            )

            if pod.status.container_statuses:
                for container in pod.status.container_statuses:
                    if container.ready:
                        ready_containers += 1

            pod_details.append({
                "name": pod.metadata.name,
                "phase": pod.status.phase,
                "ready_containers": ready_containers,
                "total_containers": total_containers,
                "restarts": sum(
                    container.restart_count
                    for container in (
                        pod.status.container_statuses or []
                    )
                )
            })

        return {
            "total_pods": len(pod_details),
            "pods": pod_details
        }

    except Exception as e:
        return {
            "error": f"Kubernetes query failed: {e}"
        }

def get_deployment_health():
    try:

        deployment = apps_v1.read_namespaced_deployment(
            name="order-service",
            namespace="ai-sre"
        )

        spec = deployment.spec
        status = deployment.status

        return {
            "name": deployment.metadata.name,
            "desired_replicas": spec.replicas or 0,
            "available_replicas": status.available_replicas or 0,
            "ready_replicas": status.ready_replicas or 0,
            "updated_replicas": status.updated_replicas or 0,
            "unavailable_replicas": (
                status.unavailable_replicas or 0
            )
        }

    except Exception as e:
        return {
            "error": f"Kubernetes deployment query failed: {e}"
        }

def get_resource_requests_limits():
    try:
        pods = v1.list_namespaced_pod(
            namespace="ai-sre",
            label_selector="app=order-service"
        )

        pod_resources = []

        for pod in pods.items:
            containers = []

            for container in pod.spec.containers:
                resources = container.resources

                requests = resources.requests or {}
                limits = resources.limits or {}

                containers.append({
                    "name": container.name,
                    "cpu_request": requests.get("cpu"),
                    "cpu_limit": limits.get("cpu"),
                    "memory_request": requests.get("memory"),
                    "memory_limit": limits.get("memory")
                })

            pod_resources.append({
                "pod": pod.metadata.name,
                "containers": containers
            })

        return {
            "pods": pod_resources
        }

    except Exception as e:
        return {
            "error": f"Kubernetes resource query failed: {e}"
        }

    
def get_kubernetes_health():
    return {
        "pods": get_pod_health(),
        "deployment": get_deployment_health(),
        "resources": get_resource_requests_limits()
    }