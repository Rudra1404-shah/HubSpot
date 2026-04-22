from __future__ import annotations

from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain_groq import ChatGroq

from CRM_Assistant.backend.schemas.Ticket import PartialCreateTicket
import os
parser = PydanticOutputParser(pydantic_object=PartialCreateTicket)
llm = ChatGroq(
    model="qwen/qwen3-32b",
    temperature=0,
    max_tokens=1200,
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
)
prompt = PromptTemplate(
    template="""
You are extracting ticket creation fields.

Rules:
- Extract only what the user explicitly provides.
- Do NOT assume defaults.
- The full user message must be used as description.
- Title should be a concise summary.
- Description should never be null if user provides issue details.
- Normalize status and priority to enum values if possible.
-Use the full user message as description unless a shorter description is explicitly provided.
- Title should be a short summary.
- Do not leave description null if user provides context
{format_instructions}

User message:
{input}
""",
    input_variables=["input"],
    partial_variables={
        "format_instructions": parser.get_format_instructions()
    }
)
extraction = prompt | llm | parser


def extract_create_ticket_fields(user_message: str) -> dict:
    try:
        result = extraction.invoke({"input": user_message})
        return result.model_dump()
    except Exception:
        # If LLM parsing fails, return empty structure
        return {
            "title": None,
            "description": None,
            "status": None,
            "priority": None
        }


TICKET_DRAFT_STORE: dict[str, dict] = {}


def load_ticket_draft(conversation_id: str) -> dict | None:
    """
    Load the ticket draft for the given conversation.
    """
    return TICKET_DRAFT_STORE.get(conversation_id)


def save_ticket_draft(conversation_id: str, draft: dict) -> None:
    """
    Persist the ticket draft for the conversation.
    """
    TICKET_DRAFT_STORE[conversation_id] = draft


def clear_ticket_draft(conversation_id: str) -> None:
    """
    Remove the ticket draft after completion or cancellation.
    """
    TICKET_DRAFT_STORE.pop(conversation_id, None)


STATUS_VALUES = {
    "waiting on us": "WAITING_ON_US",
    "waiting on contact": "WAITING_ON_CONTACT",
    "new": "NEW"
}

PRIORITY_VALUES = {
    "low": "LOW",
    "medium": "MEDIUM",
    "high": "HIGH"
}


def normalize_slots(extracted: dict) -> dict:
    if extracted.get("priority") and extracted["priority"].lower() in STATUS_VALUES:
        extracted["status"] = STATUS_VALUES[extracted["priority"].lower()]
        extracted["priority"] = None

    return extracted


def merge_ticket_state(existing: dict, new: dict) -> dict:
    """
    Merge newly extracted fields into the existing draft.
    New values overwrite old ones only if not None.
    """
    merged = existing.copy()

    for key, value in new.items():
        if value is None:
            continue

        # 🔒 Protect description from being overwritten
        if key in {"title", "description"} and merged.get(key):
            continue

        merged[key] = value

    return merged


def draft_complete(draft: dict) -> bool:
    """
    Check whether the draft has all required fields.
    """
    required_fields = ["status", "priority"]

    return all(draft.get(field) for field in required_fields)


def map_draft_to_create_ticket_input(draft: dict) -> dict:
    raw_title = draft.get("title") or ""
    raw_description = draft.get("description") or ""

    # 🔑 Strip command language
    subject = strip_command_phrases(raw_title)
    description = strip_command_phrases(raw_description)

    # Safety fallback
    if not description:
        description = subject

    return {
        "subject": subject,
        "content": description,
        "status": draft["status"],
        "priority": draft["priority"]
    }


def is_create_intent_safe(intent: str, extracted: dict) -> bool:
    """
    Prevent creation from update-only messages.
    """
    if intent != "create_ticket":
        return False

    # If message only changes status/priority → not a real create
    has_problem_context = (
            extracted.get("title") or extracted.get("description")
    )

    return bool(has_problem_context)


import re

COMMAND_PATTERNS = [
    r"^create (a )?ticket( citing the issue of)?",
    r"^raise (a )?ticket( for)?",
    r"^log (a )?ticket( regarding)?",
    r"^open (a )?ticket( for)?"
]


def strip_command_phrases(text: str) -> str:
    cleaned = text.strip()

    for pattern in COMMAND_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

    # Capitalize nicely
    return cleaned[:1].upper() + cleaned[1:] if cleaned else cleaned


pagination_memory = {}


def save_pagination_cursor(conversation_id: str, cursor: str):
    pagination_memory[conversation_id] = cursor


def load_pagination_cursor(conversation_id: str):
    return pagination_memory.get(conversation_id)


def clear_pagination_cursor(conversation_id: str):
    pagination_memory.pop(conversation_id, None)


update_memory = {}


def save_update_draft(conversation_id: str, data: dict):
    update_memory[conversation_id] = data


def load_update_draft(conversation_id: str):
    return update_memory.get(conversation_id)


def clear_update_draft(conversation_id: str):
    update_memory.pop(conversation_id, None)


delete_memory = {}
def save_delete_draft(conversation_id: str, data: dict):
    """
    Save delete draft state for a conversation.
    """
    delete_memory[conversation_id] = data


def load_delete_draft(conversation_id: str):
    """
    Load delete draft state for a conversation.
    Returns None if no draft exists.
    """
    return delete_memory.get(conversation_id)


def clear_delete_draft(conversation_id: str):
    """
    Clear delete draft after completion or cancellation.
    """
    delete_memory.pop(conversation_id, None)
import re

import re

def extract_subject_from_update(user_message: str) -> str | None:
    """
    Extract subject from phrases like:
    - Delete Issue of site ticket
    - Delete ticket Issue of site
    - Update Issue of site ticket
    - I want to delete Issue of site
    """

    text = user_message.strip()

    match = re.search(
        r"(?:delete|update)(?:\s+ticket)?\s+(.*?)(?:\s+ticket)?$",
        text,
        re.IGNORECASE
    )

    if match:
        subject = match.group(1).strip()
        return subject if subject else None

    return None
