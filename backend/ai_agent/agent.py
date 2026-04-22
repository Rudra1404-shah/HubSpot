from __future__ import annotations

import json
import uuid
from typing import Optional

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from .intents import extract_create_ticket_fields, draft_complete, load_ticket_draft, merge_ticket_state, \
    save_ticket_draft, clear_ticket_draft, map_draft_to_create_ticket_input, is_create_intent_safe, \
    save_pagination_cursor, clear_pagination_cursor, load_pagination_cursor, load_update_draft, save_update_draft, \
    clear_update_draft, load_delete_draft, clear_delete_draft, save_delete_draft, extract_subject_from_update
from .run_agent_with_history import DecisionTrace, save_decision_trace

# from agent.prompt import SYSTEM_PROMPT
from CRM_Assistant.backend.ai_agent.tools import (
    get_tickets, search_tickets,
    Create_ticket,
     update_ticket,
    delete_ticket,
)
import os 
llm = ChatGroq(
    model="qwen/qwen3-32b",
    temperature=0,
    max_tokens=1200,
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    ,
    timeout = 60
)

llm_with_tools = llm.bind_tools([
    get_tickets,
    search_tickets,
    Create_ticket,
    update_ticket,
    delete_ticket
])


SYSTEM_PROMPT = """
                
You are a CRM assistant responsible for managing support tickets.

You have access to FOUR tools:
1. get_tickets      → fetch all tickets (no filters)
2. search_tickets   → search tickets using filters
3. Create_ticket    → create a new support ticket
4. update_ticket    → update an existing ticket (PATCH)
5. delete_ticket    → Deletes Ticket with ticket_id (DELETE)


--------------------------------------------------
INTENT CLASSIFICATION (MANDATORY)
--------------------------------------------------
You MUST first classify the user's intent into exactly ONE of:
- GET_TICKETS
- SEARCH_TICKETS
- CREATE_TICKET
- UPDATE_TICKET
- RESOLVE_AND_UPDATE
- DELETE_TICKET

--------------------------------------------------
GET_TICKETS RULES
--------------------------------------------------
- Use GET_TICKETS only when the user asks to see tickets WITHOUT any filters.
- If ANY filter is mentioned, DO NOT use get_tickets.

--------------------------------------------------
SEARCH_TICKETS RULES
--------------------------------------------------
- If the user mentions ANY filter → intent is SEARCH_TICKETS.
- Supported filters:
  - subject (text)
  - priority: LOW, MEDIUM, HIGH, URGENT
  - status: NEW, WAITING_ON_CONTACT, WAITING_ON_US, CLOSED
- Never invent filter values.
- Never fall back to get_tickets when filters exist.

--------------------------------------------------
CREATE_TICKET RULES
--------------------------------------------------
- If the user asks to create / raise / open a ticket → intent is CREATE_TICKET.
- Extract full TicketCreate schema:
  - subject (required)
  - content (required)
  - priority (default = MEDIUM)
  - status (default = NEW)

--------------------------------------------------
UPDATE_TICKET RULES
--------------------------------------------------
- If the user asks to update / change / modify / close a ticket → intent is UPDATE_TICKET.
When the user requests to update a ticket:

1. If ticket_id IS PROVIDED:
   → Call update_ticket immediately.

2. If ticket_id IS NOT PROVIDED:
   → Call search_tickets using subject keywords.

3. AFTER search_tickets:
   - If EXACTLY ONE ticket is found:
       → Automatically extract its ticket_id
       → IMMEDIATELY call update_ticket in the SAME RESPONSE.
       → And Then use the returned ticket_id to run a Search Query Which returns The Updated Ticket data as a Response.
   - If MORE THAN ONE ticket is found:
       → Ask the user which ticket to update.
   - If NO tickets are found:
       → Ask the user for clarification.

4. NEVER stop after search_tickets if exactly one ticket is found.
5. NEVER ask the user to repeat the update command.
6. The goal is ALWAYS to complete the update if certainty exists.

- Valid updates:
  - subject
  - content
  - priority: LOW | MEDIUM | HIGH | URGENT
  - status: NEW | WAITING_ON_CONTACT | WAITING_ON_US | CLOSED
- Do NOT overwrite unspecified fields.

--------------------------------------------------
DELETE_TICKET RULES
--------------------------------------------------
- If the user asks to delete / remove / cancel a ticket → intent is DELETE_TICKET.
- ticket_id is REQUIRED.
- If ticket_id is missing, ask for it.
- Call delete_ticket.



--------------------------------------------------
GENERAL RULES
--------------------------------------------------
- Call ONLY ONE tool.
- Never mix create/search/update in one response.
- Ask for clarification if ticket_id is missing.
- Never invent data.

When calling Create_ticket or update_ticket:
- Pass arguments as structured JSON (not stringified).
- Do NOT wrap payload in a "data" field.
--------------------------------------------------
CRITICAL RESPONSE CONSTRAINT
--------------------------------------------------
You are NOT a conversational chatbot.

You MUST NEVER:
- Explain your capabilities
- List available tools
- Provide help menus or summaries
- Say what you can or cannot do

You MUST ALWAYS do exactly of the following:
1. Call a tool
2. Ask a clarification question
3. Return a direct result of a tool call

If the user input does not clearly match an intent:
- Ask ONE clarification question
- Do NOT explain anything
        """
def detect_intent(text: str) -> str:
    """
    Lightweight intent detection for debugging & decision tracing.
    This is NOT used for execution logic, only for visibility.
    """
    if not text:
        return "unknown"

    t = text.lower()

    if "update" in t:
        return "update_ticket"
    if "create" in t:
        return "create_ticket"
    if "delete" in t:
        return "delete_ticket"
    if "search" in t or "find" in t:
        return "search_ticket"
    if "get" in t or "show" in t:
        return "get_tickets"

    return "unknown"
extractor  = """ 
You are a CRM update extractor.

Your task:
- Extract ONLY the fields the user explicitly wants to UPDATE.
- Output MUST be valid JSON.
- Output MUST contain ONLY the JSON object.
- DO NOT include explanations, reasoning, or text.

Allowed fields and values:
{
  "status": "NEW | WAITING_ON_CONTACT | WAITING_ON_US | CLOSED",
  "priority": "LOW | MEDIUM | HIGH | URGENT",
  "subject": string,
  "content": string
}

Rules:
- If a field is not explicitly mentioned, DO NOT include it.
- Never guess.
- If no fields should be updated, return {}.
- If the user says "change X to Y", treat Y as an explicit update.
- Output ONLY JSON.

"""
import json
import re
def extract_update_fields_llm(user_message: str) -> dict:
    extraction_prompt = [
        SystemMessage(content=extractor),
        HumanMessage(content=user_message),
    ]

    response = llm.invoke(extraction_prompt)

    raw = response.content
    match = re.search(r"\{[\s\S]*?\}", raw)
    if not match:
        print("❌ NO JSON FOUND IN LLM OUTPUT")
        print(raw)
        return {}

    json_str = match.group(0)

    try:
        return json.loads(json_str)
    except Exception as e:
        print("❌ JSON PARSE FAILED")
        print("RAW OUTPUT:", raw)
        print("EXTRACTED JSON:", json_str)
        print("ERROR:", e)
        return {}

import re

def extract_limit(user_message: str, default=8, max_limit=100):
    match = re.search(r"\b(\d+)\b", user_message)
    if not match:
        return default
    return min(int(match.group(1)), max_limit)
def is_continuation(user_message: str) -> bool:
    text = user_message.lower()
    return any(
        phrase in text
        for phrase in ["next", "another", "remaining", "continue", "more"]
    )
conversation_id = str(uuid.uuid4())
def run_agent_with_history(
    messages: list,
    after: Optional[str] | None,
    continuation: bool
):
    """
    messages: List[HumanMessage | AIMessage]
    """

    user_message = messages[-1].content if messages else ""
    limit = extract_limit(user_message, default=8)

    # -------------------------
    # CONTINUATION (pagination)
    # -------------------------
    if continuation:
        saved_cursor = load_pagination_cursor(conversation_id)

        if not saved_cursor:
            return {"response": "No more tickets to show."}

        tool_result = get_tickets.invoke({
            "limit": limit,
            "after": saved_cursor
        })

        # Save new cursor if exists
        next_after = (
            tool_result.get("paging", {})
                .get("next", {})
                .get("after")
        )

        if next_after:
            save_pagination_cursor(conversation_id, next_after)
        else:
            clear_pagination_cursor(conversation_id)

        return {"response": tool_result}

    full_messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        *messages
    ]

    trace = DecisionTrace(user_message)
    delete_draft = load_delete_draft(conversation_id)

    if delete_draft and delete_draft.get("awaiting_confirmation"):

        normalized = user_message.strip().lower()

        if normalized in {"yes", "confirm"}:
            result = delete_ticket.invoke({
                "ticket_id": delete_draft["ticket_id"]
            })

            clear_delete_draft(conversation_id)

            return {"response": result}

        if normalized in {"no", "cancel"}:
            clear_delete_draft(conversation_id)

            return {"response": "Ticket deletion cancelled."}

        return {"response": "Please reply with yes or no."}

    try:
        trace.intent = detect_intent(user_message)
    except Exception:
        trace.intent = "unknown"
    if trace.intent == "delete_ticket":

        subject = extract_subject_from_update(user_message)

        if not subject:
            return {"response": "Please specify the ticket subject you want to delete."}

        result = search_tickets.invoke({
            "subject": subject
        })

        tickets = result.get("tickets", [])

        if not tickets:
            return {"response": "No ticket found matching that subject."}

        if len(tickets) > 1:
            return {
                "response": "Multiple tickets found. Please be more specific."
            }

        ticket = tickets[0]

        save_delete_draft(conversation_id, {
            "ticket_id": ticket["id"],
            "awaiting_confirmation": True
        })

        return {
            "response": (
                f'Are you sure you want to delete:\n'
                f'"{ticket["subject"]}"?\n\n'
                "Type yes or no."
            )
        }

    response = llm_with_tools.invoke(full_messages)

    # -------------------------
    # CREATE TICKET (STATEFUL)
    # -------------------------

    draft = load_ticket_draft(conversation_id)

    # -------------------------
    # CONFIRMATION HANDLING
    # -------------------------
    if draft and draft_complete(draft):
        normalized = user_message.strip().lower()

        if normalized in {
            "create a new one",
            "create new",
            "create it",
            "yes",
            "go ahead",
            "proceed"
        }:
            tool_input = map_draft_to_create_ticket_input(draft)
            result = Create_ticket.invoke(tool_input)

            clear_ticket_draft(conversation_id)

            trace.rules_applied.append("create_confirmed")
            trace.outcome = "success"
            save_decision_trace(trace)

            return {"response": result}

        if normalized in {"no", "cancel", "don't create"}:
            clear_ticket_draft(conversation_id)

            trace.rules_applied.append("create_cancelled")
            trace.outcome = "cancelled"
            save_decision_trace(trace)

            return {
                "response": "Okay, I’ve cancelled the ticket creation."
            }

    if draft and user_message.strip().lower() in {"no", "cancel", "never mind", "don't create"}:
        clear_ticket_draft(conversation_id)

        trace.rules_applied.append("draft_cancelled")
        trace.outcome = "cancelled"
        save_decision_trace(trace)

        return {
            "response": "Okay, I’ve cancelled the ticket creation. Let me know if you need anything else."
        }
    if trace.intent == "create_ticket" or (draft and not draft_complete(draft)):

        # Initialize draft if first message
        if not draft:
            draft = {
                "title": None,
                # 🔑 SEED DESCRIPTION WITH ORIGINAL USER MESSAGE
                "description": user_message.strip(),
                "status": None,
                "priority": None
            }

        # Extract & merge fields
        extracted = extract_create_ticket_fields(user_message)
        draft = merge_ticket_state(draft, extracted)
        save_ticket_draft(conversation_id, draft)

        # Check missing fields
        missing = []
        if not draft.get("status"):
            missing.append("status")
        if not draft.get("priority"):
            missing.append("priority")

        if missing:
            clarification = (
                "I can create the ticket about the reported issue.\n"
                "Please specify:\n" +
                "\n".join(f"- {field}" for field in missing)
            )

            trace.rules_applied.append("missing_create_fields")
            trace.outcome = "clarification_requested"
            save_decision_trace(trace)

            return {"response": clarification}
        if draft_complete(draft):

            # 🔒 SAFETY CHECK (THIS IS THE ANSWER TO "WHERE")
            if not is_create_intent_safe(trace.intent, extracted):
                trace.rules_applied.append("unsafe_create_blocked")
                trace.outcome = "clarification_requested"
                save_decision_trace(trace)

                return {
                    "response": (
                        "I can update an existing ticket, or create a new one.\n"
                        "What would you like to do?"
                    )
                }
        # Draft complete → create ticket
            tool_input = map_draft_to_create_ticket_input(draft)
            result = Create_ticket.invoke(tool_input)

            clear_ticket_draft(conversation_id)

            trace.tools_called.append("create_ticket")
            trace.tool_args.append(draft)
            trace.outcome = "success"
            save_decision_trace(trace)

            return {"response": result}
    update_draft = load_update_draft(conversation_id)

    if update_draft:

        # Waiting for update fields
        if  update_draft and update_draft.get("awaiting_fields"):

            update_fields = extract_update_fields_llm(user_message)

            if not update_fields:
                return {
                    "response": "Please specify what you want to update (status, priority, or description)."
                }

            result = update_ticket.invoke({
                "ticket_id": update_draft["ticket_id"],
                **update_fields
            })

            clear_update_draft(conversation_id)

            return {"response": result}

    # -------------------------
    # TOOL EXECUTION
    # -------------------------
    if response.tool_calls:
        call = response.tool_calls[0]

        tool_name = call.get("name")
        tool_args = call.get("args", {})

        trace.tools_called.append(tool_name)
        trace.tool_args.append(tool_args)

        tool_map = {
            "get_tickets": get_tickets,
            "search_tickets": search_tickets,
            "create_ticket": Create_ticket,   # ✅ normalized
            "update_ticket": update_ticket,
            "delete_ticket": delete_ticket
        }

        try:
            tool = tool_map.get(tool_name)
            if not tool:
                trace.outcome = f"unknown_tool: {tool_name}"
                save_decision_trace(trace)
                raise ValueError(f"Tool '{tool_name}' not found")



            tool_result = tool.invoke(tool_args)
            if tool_name == "get_tickets"and isinstance(tool_result, dict):
                next_after = (
                    tool_result.get("paging", {})
                        .get("next", {})
                        .get("after")
                )

                if next_after:
                    save_pagination_cursor(conversation_id, next_after)
                else:
                    clear_pagination_cursor(conversation_id)
            if tool_name == "search_tickets":
                tickets = (
                    tool_result.get("tickets")
                    if isinstance(tool_result, dict)
                    else tool_result
                )
                if not tickets:
                    trace.rules_applied.append("no_results_found")
                    trace.outcome = "success"
                    save_decision_trace(trace)

                    return {"response": "No tickets found matching your criteria."}
                if tickets and len(tickets) > 1:
                    trace.rules_applied.append("multiple_tickets_returned")
                    trace.outcome = "success"
                    save_decision_trace(trace)

                    return {"response": tool_result}

                if tickets and len(tickets) == 1:
                    ticket = tickets[0]
                    if trace.intent == "update_ticket":
                    # Save ticket into update draft memory
                        save_update_draft(conversation_id, {
                            "ticket_id": ticket["id"],
                            "awaiting_fields": True
                        })

                        trace.rules_applied.append("ticket_selected_for_update")
                        trace.outcome = "clarification_requested"
                        save_decision_trace(trace)

                        return {
                            "response": (
                                f'I found the ticket:\n'
                                f'"{ticket["subject"]}"\n\n'
                                "What would you like to update?\n"
                                "- Status\n"
                                "- Priority\n"
                                "- Description"
                            )
                        }
                    # -------------------------
                    # DELETE INTENT (FIRST TURN)
                    # -------------------------
                    if trace.intent == "delete_ticket":

                        subject = extract_subject_from_update(user_message)

                        if not subject:
                            return {"response": "Please specify the ticket subject you want to delete."}

                        result = search_tickets.invoke({
                            "subject": subject
                        })

                        tickets = result.get("tickets", [])

                        if not tickets:
                            return {"response": "No ticket found matching that subject."}

                        if len(tickets) > 1:
                            return {
                                "response": "Multiple tickets found. Please be more specific."
                            }

                        ticket = tickets[0]

                        save_delete_draft(conversation_id, {
                            "ticket_id": ticket["id"],
                            "awaiting_confirmation": True
                        })

                        return {
                            "response": (
                                f'Are you sure you want to delete:\n'
                                f'"{ticket["subject"]}"?\n\n'
                                "Type yes or no."
                            )
                        }

                    trace.rules_applied.append("single_ticket_viewed")
                    trace.outcome = "success"
                    save_decision_trace(trace)
                    return {"response": tool_result}
            if tool_name == "get_tickets":
                trace.rules_applied.append("get_tickets_returned")
                trace.outcome = "success"
                save_decision_trace(trace)

                return {"response": tool_result}

        except Exception as e:
            trace.outcome = f"tool_error: {str(e)}"
            save_decision_trace(trace)
            raise

    # -------------------------
    # FINAL FALLBACK
    # -------------------------
    clarification = "Can you please clarify what you want to do with the tickets?"

    trace.rules_applied.append("no_tool_selected")
    trace.outcome = "clarification_requested"
    save_decision_trace(trace)

    return {"response": clarification}

