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
        "CLOSED": "4",
    }

def normalize_ticket(data: dict) -> dict:
    if "properties" not in data:
        raise ValueError(f"normalize_ticket received invalid data: {data}")

    props = data["properties"]

    HUBSPOT_STAGE_REVERSE_MAP = {
        "1": "NEW",
        "2": "WAITING_ON_CONTACT",
        "3": "WAITING_ON_US",
        "4": "CLOSED",
    }

    return {
        "id": data.get("id"),
        "subject": props.get("subject"),
        "description": props.get("content"),
        "status": HUBSPOT_STAGE_REVERSE_MAP.get(
            props.get("hs_pipeline_stage"),
            f"UNKNOWN({props.get('hs_pipeline_stage')})"
        ),

        "priority": props.get("hs_ticket_priority"),
        "created_at": props.get("createdate"),
        "updated_at": props.get("hs_lastmodifieddate"),
        "closed": props.get("hs_is_closed"),
    }
