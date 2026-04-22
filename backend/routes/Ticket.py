from typing import Optional

from fastapi import APIRouter

from CRM_Assistant.backend.schemas.Ticket import (
    TicketCreate,
    TicketUpdate,
    TicketSearch, HUBSPOT_STAGE_MAP)

from CRM_Assistant.backend.bussiness_logic.ticket import (
     create_ticket_sync,
    get_tickets_sync, update_ticket_sync, delete_ticket_sync, search_tickets_sync)

router = APIRouter(
    prefix="/hubspot/tickets",
    tags=["HubSpot Tickets"]
)


@router.post("/")
def create_ticket_api(data: TicketCreate):
    # 1️⃣ Build HubSpot-compliant payload
    hubspot_payload = {
        "properties": {
            "subject": data.subject,
            "hs_pipeline": "0",

            "hs_pipeline_stage": HUBSPOT_STAGE_MAP[data.status],
        }
    }
    if data.content:
        hubspot_payload["properties"]["content"] = data.content
    if data.priority is not None:
        hubspot_payload["properties"]["hs_ticket_priority"] = data.priority.value

    print("🟡 Final payload:", hubspot_payload)
    result = create_ticket_sync(hubspot_payload)
    return result


@router.get("/")
def list_tickets(limit: int = 10,after: Optional[str] = None):
    return get_tickets_sync(limit=limit, after=after)


@router.patch("/{ticket_id}")
def update_ticket_api(ticket_id: str, data: TicketUpdate):
    print(f"🔥 PATCH /hubspot/tickets/{ticket_id}")
    print("🟢 Incoming update data:", data.dict(exclude_none=True))

    payload = {}

    if data.subject is not None:
        payload["subject"] = data.subject

    if data.content is not None:
        payload["content"] = data.content

    if data.priority is not None:
        payload["hs_ticket_priority"] = data.priority.value
    if data.status is not None:
        payload["hs_pipeline_stage"] =  HUBSPOT_STAGE_MAP[data.status]
    print("🟡 Update payload to HubSpot:", payload)
    result = update_ticket_sync(ticket_id, payload)
    return  result
@router.delete("/{ticket_id}")
def delete_ticket_api(ticket_id: str):
    delete_ticket_sync(ticket_id)
    return {"deleted": True}


# ---------------- SEARCH ----------------
@router.post("/search")
def search_ticket_api(data: TicketSearch):
    print("🔥 SEARCH API HIT")
    print("Incoming data:", data)
    return search_tickets_sync(filters=data.dict(exclude_none=True))


class TicketPaginationState:
    def __init__(self):
        self.after = None
        self.exhausted = False


PAGINATION_STORE = {}

@router.get("/agent/tickets/next")
async def get_next_tickets(session_id: str):
    state = PAGINATION_STORE.get(session_id) or TicketPaginationState()
    PAGINATION_STORE[session_id] = state

    if state.exhausted:
        return {
            "success": True,
            "status_code": 200,
            "response": {
                "tickets": [],
                "has_more": False,
                "message": "No more tickets available"
            }
        }

    result = await fetch_ticket_page_async(
        after=state.after,
        page_size=10
    )

    if not result["success"]:
        return result  # propagate safely

    tickets = result["response"]["results"]
    next_after = result["response"]["next_after"]

    state.after = next_after
    if not next_after:
        state.exhausted = True

    return {
        "success": True,
        "status_code": 200,
        "response": {
            "tickets": tickets,
            "has_more": not state.exhausted
        }
    }
