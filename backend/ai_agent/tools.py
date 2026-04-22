from typing import Optional, Literal, Dict

import requests
from fastapi import HTTPException

from CRM_Assistant.backend.ai_agent.hubspot_normalizer import normalize_ticket
from CRM_Assistant.backend.bussiness_logic.ticket import create_ticket_sync, update_ticket_sync, delete_ticket_sync, \
    search_tickets_sync, get_tickets_sync, get_ticket_by_id_sync
from langchain.tools import tool

from CRM_Assistant.backend.schemas.Ticket import TicketSearch


@tool
def get_tickets(limit: int = 10, after: Optional[str] = None) -> dict:
    """
    Fetch paginated support tickets from HubSpot CRM
"""
    try:
        data = get_tickets_sync(limit=limit, after=after)
    except requests.RequestException as e:
        return {
            "error": "Failed to fetch tickets",
            "details": str(e)
        }
    HUBSPOT_STAGE_REVERSE_MAP = {
        "1": "NEW",
        "2": "WAITING_ON_CONTACT",
        "3": "WAITING_ON_US",
        "4": "CLOSED",
    }
    tickets = []
    for item in data.get("tickets", []):
        props = item.get("properties", {})
        raw_stage = props.get("hs_pipeline_stage")

        status = HUBSPOT_STAGE_REVERSE_MAP.get(raw_stage, "unknown")
        tickets.append({
            "id": item.get("id"),
            "subject": props.get("subject"),
            "content": props.get("content"),
            "status": status,
            "priority": props.get("hs_ticket_priority"),
            "created_at": props.get("createdate")
        })

    return {
        "tickets": tickets,
        "paging": data.get("paging", {})
    }


@tool
def search_tickets(subject: Optional[str] = None,
                   status: Optional[str] = None,
                   priority: Optional[str] = None, ) -> dict:
    """
Search support tickets using optional filters.

This endpoint allows querying support tickets based on common attributes
such as subject, status, and priority. All filters are optional and can
be combined to refine the search results.

Optional Filters:
- subject (str): Text to search within the ticket subject
- status (str): Ticket status
    Allowed values: NEW, WAITING_ON_CONTACT, WAITING_ON_US, CLOSED
- priority (str): Ticket priority level
    Allowed values: LOW, MEDIUM, HIGH, URGENT
- limit (int): Maximum number of tickets to return

Returns:
- List[dict]: Raw ticket data returned from the backend service
"""
    try:
        data_search = search_tickets_sync({"subject": subject,
                                           "status": status,
                                           "priority": priority})
    except requests.RequestException as e:
        return {
            "error": "Search tickets failed",
            "details": str(e)
        }
    tickets = []
    HUBSPOT_STAGE_REVERSE_MAP = {
        "1": "NEW",
        "2": "WAITING_ON_CONTACT",
        "3": "WAITING_ON_US",
        "4": "CLOSED",
    }
    for item in data_search.get("results", []):
        props = item.get("properties", {})
        raw_stage = props.get("hs_pipeline_stage")

        tickets.append({
            "id": item.get("id"),
            "subject": props.get("subject"),
            "content": props.get("content"),
            "status": HUBSPOT_STAGE_REVERSE_MAP.get(raw_stage, "unknown"),
            "priority": props.get("hs_ticket_priority"),
            "created_at": props.get("createdate")
        })

    return {
        "count": len(tickets),
        "tickets": tickets
    }


class ClosedException(Exception):
    """ Ticket With Closed Status Cannot Be Created    """
    pass


@tool
def Create_ticket(subject: str,
                  content: str,
                  priority: Literal["LOW", "MEDIUM", "HIGH", "URGENT"] = "MEDIUM",
                  status: Literal["NEW", "WAITING_ON_CONTACT", "WAITING_ON_US"] = "NEW", ) -> dict:
    """
You are a backend ticket-creation assistant.

Your task is to create a support ticket .
You must extract or infer all required fields from the user input.

SCHEMA REQUIREMENTS (MANDATORY):
- subject: short, clear summary of the issue
- content: detailed description of the problem
- priority: one of [LOW, MEDIUM, HIGH, URGENT]
- status: one of [NEW, WAITING_ON_CONTACT, WAITING_ON_US]

RULES:
1. Output MUST be valid JSON.
2. Output MUST match the TicketCreate schema exactly.
3. Do NOT add extra fields.
4. Do NOT omit any fields.
5. Enum values MUST be uppercase and match exactly.
6. If the user does not specify priority or status ask For their Confirmation And when All are Provided then only Create a ticket
7. If the user input is vague, infer the most reasonable values.
8. Do NOT include explanations, markdown, or comments in the output.
9.
USER INPUT:
{{user_input}}

OUTPUT FORMAT (STRICT):
{
  "subject": "<string>",
  "content": "<string>",
  "priority": "<LOW | MEDIUM | HIGH | URGENT>",
  "status": "<NEW | WAITING_ON_CONTACT | WAITING_ON_US>"
}


    """
    payload = {}
    HUBSPOT_STAGE_REVERSE_MAP = {
        "1": "NEW",
        "2": "WAITING_ON_CONTACT",
        "3": "WAITING_ON_US",
        "4": "CLOSED",
    }
    HUBSPOT_STAGE_FORWARD_MAP = {
        "NEW": "1",
        "WAITING_ON_CONTACT": "2",
        "WAITING_ON_US": "3",
        "CLOSED": "4"
    }
    payload = {
        "subject": subject,
        "content": content,
        "hs_ticket_priority": priority,  # ✅ FIX
        "hs_pipeline_stage": HUBSPOT_STAGE_FORWARD_MAP[status],  # ✅ FIX
        # "hs_pipeline": "0",  # ⚠️ see note below
    }
    if payload['hs_pipeline_stage'] == HUBSPOT_STAGE_FORWARD_MAP["CLOSED"]:
        raise ClosedException
    try:
        data = create_ticket_sync(payload)
        ticket_id = data.get("id")
        fresh_ticket = get_ticket_by_id_sync(ticket_id)

    except HTTPException as e:
        return {
            "error": "Create ticket failed",
            "details": e.detail
        }
    except requests.RequestException as e:
        return {
            "error": "Create ticket failed",
            "details": str(e)
        }

    return {
        "message": "Ticket created successfully",
        "ticket": normalize_ticket(fresh_ticket)
    }


@tool
def delete_ticket(ticket_id: str) -> dict:
    """
    Delete an existing support ticket.

    Requirements:
    - ticket_id is REQUIRED
    - Performs a DELETE operation
    - This action is irreversible
    """

    if not ticket_id:
        return {
            "error": "ticket_id is required"
        }

    print(f"➡ Deleting ticket {ticket_id}")

    try:
        delete_ticket_sync(ticket_id)
    except requests.RequestException as e:
        return {
            "error": "Delete ticket failed",
            "details": str(e)
        }

    return {
        "message": "Ticket deleted successfully",
        "ticket_id": ticket_id
    }


def resolve_ticket_id(filters: dict) -> str:
    tickets = search_tickets_sync(filters)

    if not tickets:
        raise ValueError("No tickets found matching your request")

    if len(tickets) > 1:
        raise ValueError(
            f"Multiple tickets found ({len(tickets)}). Please specify further."
        )

    return tickets[0]["id"]


def update_ticket_with_search(
        filters: dict,
        update_payload: dict,
        ticket_id: Optional[str] = None
) -> dict:
    # Step 1: Resolve ticket_id
    if not ticket_id:
        ticket_id = resolve_ticket_id(filters)

    # Step 2: Update
    update_ticket_sync(ticket_id, update_payload)

    # Step 3: Fetch updated ticket
    updated_ticket = get_ticket_by_id_sync(ticket_id)

    # Step 4: Normalize
    return normalize_ticket(updated_ticket)


@tool
def update_ticket(
        ticket_id: str,
        subject: Optional[str] = None,
        content: Optional[str] = None,
        priority: Optional[Literal["LOW", "MEDIUM", "HIGH", "URGENT"]] = None,
        status: Optional[Literal["NEW", "WAITING_ON_CONTACT", "WAITING_ON_US", "CLOSED"]] = None,
) -> dict:
    """
    Update an existing support ticket using PATCH.

    - ticket_id is REQUIRED
    - Only fields explicitly provided will be updated
    - Fields not provided will NOT be modified
    """

    if not ticket_id:
        return {
            "error": "ticket_id is required"
        }

    HUBSPOT_STAGE_FORWARD_MAP = {
        "NEW": "1",
        "WAITING_ON_CONTACT": "2",
        "WAITING_ON_US": "3",
        "CLOSED": "4",
    }

    # Build PATCH payload dynamically
    payload: Dict[str, str] = {}

    if subject is not None:
        payload["subject"] = subject

    if content is not None:
        payload["hs_ticket_description"] = content

    if priority is not None:
        payload["hs_ticket_priority"] = priority

    if status is not None:
        payload["hs_pipeline_stage"] = HUBSPOT_STAGE_FORWARD_MAP[status]

    if not payload:
        return {
            "error": "No updates provided",
            "details": "At least one field must be updated"
        }

    try:
        # 1️⃣ Update ticket
        update_ticket_sync(ticket_id, payload)

        # 2️⃣ Fetch updated ticket
        updated_ticket = get_ticket_by_id_sync(ticket_id)
        print("RAW FETCHED TICKET:", updated_ticket)

    except requests.RequestException as e:
        return {
            "error": "Update ticket failed",
            "details": str(e)
        }

    # 3️⃣ Normalize and return
    return {
        "message": "Ticket updated successfully",
        "ticket": normalize_ticket(updated_ticket)
    }
