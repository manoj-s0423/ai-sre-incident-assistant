from fastapi import FastAPI, Request
from prometheus_client import Counter, Histogram, generate_latest
from fastapi.responses import Response, JSONResponse
import time

app = FastAPI(
    title="AI SRE Demo Application",
    description="Sample application for AI-powered SRE incident response",
    version="1.0.0"
)


# -----------------------------
# Prometheus Metrics
# -----------------------------

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status"]
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"]
)


# -----------------------------
# Middleware
# -----------------------------

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):

    start_time = time.time()

    try:
        response = await call_next(request)

        status_code = response.status_code

        return response

    except Exception:
        status_code = 500

        raise

    finally:
        duration = time.time() - start_time

        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=status_code
        ).inc()

        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)


# -----------------------------
# Application Endpoints
# -----------------------------

@app.get("/")
def root():
    return {
        "service": "order-service",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


@app.get("/orders")
def get_orders():
    return {
        "orders": [
            {
                "id": 101,
                "product": "Laptop",
                "status": "confirmed"
            },
            {
                "id": 102,
                "product": "Keyboard",
                "status": "shipped"
            }
        ]
    }


@app.get("/slow")
def slow_request():

    time.sleep(5)

    return {
        "message": "Slow response generated"
    }


@app.get("/error")
def generate_error():

    return JSONResponse(
        status_code=500,
        content={
            "error": "Simulated application failure"
        }
    )

# -----------------------------
# Prometheus Endpoint
# -----------------------------

@app.get("/metrics")
def metrics():

    return Response(
        content=generate_latest(),
        media_type="text/plain"
    )