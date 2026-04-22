import streamlit as st
import requests
import pandas as pd

# --------------------------------
# Config
# --------------------------------
API_URL = "http://localhost:8008/agent"

st.set_page_config(page_title="CRM Assistant", layout="centered")
st.title("💬 CRM Assistant")

# --------------------------------
# Mappings (KEEP CENTRALIZED)
# --------------------------------
STATUS_MAP = {
    "1": "NEW",
    "2": "WAITING_ON_CONTACT",
    "3": "WAITING_ON_US",
    "4": "CLOSED",
    "NEW": "NEW",
    "OPEN": "OPEN",
    "CLOSED": "CLOSED"
}

PRIORITY_MAP = {
    "LOW": "🟢 LOW",
    "MEDIUM": "🟡 MEDIUM",
    "HIGH": "🟠 HIGH",
    "URGENT": "🚨 URGENT"
}

# --------------------------------
# Normalization Helpers
# --------------------------------
def normalize_ticket(ticket: dict) -> dict:
    """Normalize raw ticket into display-safe format"""

    normalized = {
        "ID": ticket.get("id"),
        "Subject": ticket.get("subject"),
        "Status": STATUS_MAP.get(
            ticket.get("status"),
            ticket.get("status")
        ),
        "Priority": PRIORITY_MAP.get(
            ticket.get("priority"),
            "⚪ UNKNOWN"
        ),
        "Created At": ticket.get("created_at")
    }

    # Only include description if it exists and is not empty
    description = ticket.get("content")
    if description and description.strip():
        normalized["Description"] = description

    return normalized


def tickets_to_df(tickets: list) -> pd.DataFrame:
    rows = [normalize_ticket(t) for t in tickets]
    return pd.DataFrame(rows)


def single_ticket_to_df(ticket: dict) -> pd.DataFrame:
    normalized = normalize_ticket(ticket)
    return pd.DataFrame(
        list(normalized.items()),
        columns=["Field", "Value"]
    )

# --------------------------------
# Renderers (TABULAR ONLY)
# --------------------------------
def render_ticket_list(response: dict):
    tickets = response.get("tickets", [])

    if not tickets:
        st.info("No tickets to display")
        return

    df = tickets_to_df(tickets)

    st.markdown(f"### 🎫 Tickets ({len(df)})")
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_single_ticket(response: dict):
    ticket = response.get("ticket")

    if not ticket:
        st.error("Ticket data missing")
        return

    st.success(response.get("message", "Operation successful"))

    df = single_ticket_to_df(ticket)

    st.markdown("### 🎟 Ticket Details")
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_delete_response(response: dict):
    st.success(response.get("message", "Ticket deleted successfully"))

# --------------------------------
# Session State
# --------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None

# --------------------------------
# Display Chat History
# --------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        content = msg["content"]

        if isinstance(content, dict):
            if "tickets" in content:
                render_ticket_list(content)
            elif "ticket" in content:
                render_single_ticket(content)
            elif "message" in content:
                render_delete_response(content)
            else:
                st.json(content)
        else:
            st.markdown(content)

# --------------------------------
# User Input
# --------------------------------
user_input = st.chat_input("Type your message...")

if user_input:
    # User message
    st.session_state.messages.append({
        "role": "user",
        "content": user_input
    })

    with st.chat_message("user"):
        st.markdown(user_input)

    payload = {
        "message": user_input,
        "conversation_id": st.session_state.conversation_id
    }

    try:
        res = requests.post(API_URL, json=payload, timeout=30)
        res.raise_for_status()
        data = res.json()
    except requests.RequestException as e:
        assistant_reply = f"❌ Error contacting agent: {e}"
    else:
        st.session_state.conversation_id = data.get("conversation_id")
        assistant_reply = data.get("response", "No response from agent")

    # Save assistant message
    st.session_state.messages.append({
        "role": "assistant",
        "content": assistant_reply
    })

    # Render assistant response
    with st.chat_message("assistant"):
        if isinstance(assistant_reply, dict):
            if "tickets" in assistant_reply:
                render_ticket_list(assistant_reply)
            elif "ticket" in assistant_reply:
                render_single_ticket(assistant_reply)
            elif "message" in assistant_reply:
                render_delete_response(assistant_reply)
            else:
                st.json(assistant_reply)
        else:
            st.markdown(assistant_reply)
