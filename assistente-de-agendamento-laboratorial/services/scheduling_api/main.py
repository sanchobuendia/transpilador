from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI, HTTPException

from logging_utils import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)
app = FastAPI(title="Scheduling Api", version="1.0.0")
ALLOWED_OPERATIONS = set(["create_appointment", "get_appointment", "list_appointments"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "component_id": "scheduling_api"}


@app.post("/invoke/{operation}")
def invoke(operation: str, payload: dict | None = None) -> dict:
    if operation not in ALLOWED_OPERATIONS:
        raise HTTPException(status_code=404, detail="Operation not found")
    body = payload or {}
    logger.info("Executando %s em scheduling_api", operation)
    return {
        "component_id": "scheduling_api",
        "operation": operation,
        "received": body,
        "status": "ok",
        "processed_at": datetime.utcnow().isoformat() + "Z",
    }
