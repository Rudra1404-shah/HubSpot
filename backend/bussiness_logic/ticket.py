from typing import Dict, Any, Optional

import requests
from fastapi import HTTPException
from CRM_Assistant.backend.bussiness_logic.Creds import HUBSPOT_TOKEN
BASE_URL = "https://api.hubapi.com"

HEADERS = {
    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
    "Content-Type": "application/json"
}
def create_ticket_sync(data: dict):
    print("🔵 HubSpot URL:", f"{BASE_URL}/crm/v3/objects/tickets")
    print("🟡 Sending to HubSpot:", data)
    r = requests.post(
        f"{BASE_URL}/crm/v3/objects/tickets",
        headers=HEADERS,
        json={
            "properties":data
        },
        timeout=60
    )

    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()

# ---------------- READ ALL ----------------
def get_tickets_sync(limit: int = 10, after: Optional[str]= None) -> dict:
    params = {"limit": limit}
    if after:
        params["after"] = after

    r = requests.get(
        f"{BASE_URL}/crm/v3/objects/tickets",
        headers=HEADERS,
        params=params,
        timeout=60
    )
    r.raise_for_status()

    data = r.json()
    print("RAW HUBSPOT RESPONSE:", data)
    return {
        "tickets": data.get("results", []),   # ✅ CORRECT KEY
        "paging": data.get("paging", {})       # ✅ CURSOR SOURCE
    }

def delete_ticket_sync(ticket_id: str):
    r = requests.delete(
        f"{BASE_URL}/crm/v3/objects/tickets/{ticket_id}",
        headers=HEADERS,
        timeout=60
    )

    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return {"deleted": True, "ticket_id": ticket_id}
def get_ticket_by_id_sync(ticket_id: str):
    r = requests.get(
        f"{BASE_URL}/crm/v3/objects/tickets/{ticket_id}",
        headers=HEADERS,
        params={
            "properties": [
                "subject",
                "hs_ticket_description",
                "hs_ticket_priority",
                "hs_pipeline_stage",
                "createdate",
                "hs_lastmodifieddate",
                "hs_is_closed",
                "closedate"
            ]
        }
    )

    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()


def update_ticket_sync(ticket_id: str, data: dict):
    existing = get_ticket_sync(ticket_id)

    properties = existing["properties"]

    payload = {
        "properties": {
            "hs_pipeline": properties["hs_pipeline"],
            "hs_pipeline_stage": properties["hs_pipeline_stage"],
            **data
        }
    }

    r = requests.patch(
        f"{BASE_URL}/crm/v3/objects/tickets/{ticket_id}",
        headers=HEADERS,
        json=payload,
        timeout=60
    )

    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()

def get_ticket_sync(ticket_id: str):
    r = requests.get(
        f"{BASE_URL}/crm/v3/objects/tickets/{ticket_id}",
        headers=HEADERS,
        timeout=60
    )

    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()
INVALID_PLACEHOLDERS = {
    "",
    "string",
    "any",
    "all",
    "everything",
    "none",
    "null",
    "undefined",
}

def is_valid_filter_value(value: str) -> bool:
    if not isinstance(value, str):
        return False

    v = value.strip().lower()

    if not v:
        return False

    if v in INVALID_PLACEHOLDERS:
        return False

    if len(v) < 2:   # avoids useless tokens like "a"
        return False

    return True

def search_tickets_sync( filters: Dict[str, Any],):
    hubspot_filters = []
    HUBSPOT_PROPERTY_MAP = {
        "subject": "subject",
        "status": "hs_pipeline_stage",
        "priority": "hs_ticket_priority",
    }
    HUBSPOT_STAGE_MAP = {
        "NEW": "1",
        "WAITING_ON_CONTACT": "2",
        "WAITING_ON_US": "3",
        "CLOSED": "4",
    }

    hubspot_filters = []

    for key, value in filters.items():
        if not is_valid_filter_value(value):
            continue  # 🔐 LLM-safe

        hubspot_property = HUBSPOT_PROPERTY_MAP.get(key)
        if not hubspot_property:
            continue

        # Default operator
        operator = "CONTAINS_TOKEN"

        # Enum handling
        if key == "status":
            operator = "EQ"
            value = HUBSPOT_STAGE_MAP.get(value.upper())
            if not value:
                continue

        if key == "priority":
            operator = "EQ"
            value = value.upper()

        hubspot_filters.append({
            "propertyName": hubspot_property,
            "operator": operator,
            "value": value
        })

    payload = {
        "filterGroups": [
            {
                "filters": hubspot_filters
            }
        ] if hubspot_filters else []
    }
    print("🔎 search_tickets_sync called")
    print("Filters received:", filters)

    r = requests.post(
        f"{BASE_URL}/crm/v3/objects/tickets/search",
        headers=HEADERS,
        json=payload,
        timeout=60
    )
    import json
    print("HubSpot search payload:")
    print(json.dumps(payload, indent=2))

    if r.status_code >= 400:
        print("HubSpot error response:", r.text)
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()


