"""Clientes HTTP gerados para componentes com transporte HTTP."""
from __future__ import annotations

import httpx

from .logging_utils import get_logger

logger = get_logger(__name__)

BASE_URL_SCHEDULING_API = "http://scheduling-api:8000"

def create_appointment(payload: dict | None = None) -> dict:
    logger.info("Chamando create_appointment em scheduling_api")
    response = httpx.post(
        f"{BASE_URL_SCHEDULING_API}/invoke/create_appointment",
        json=payload or {},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()

BASE_URL_SCHEDULING_API = "http://scheduling-api:8000"

def get_appointment(payload: dict | None = None) -> dict:
    logger.info("Chamando get_appointment em scheduling_api")
    response = httpx.post(
        f"{BASE_URL_SCHEDULING_API}/invoke/get_appointment",
        json=payload or {},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()

BASE_URL_SCHEDULING_API = "http://scheduling-api:8000"

def list_appointments(payload: dict | None = None) -> dict:
    logger.info("Chamando list_appointments em scheduling_api")
    response = httpx.post(
        f"{BASE_URL_SCHEDULING_API}/invoke/list_appointments",
        json=payload or {},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
