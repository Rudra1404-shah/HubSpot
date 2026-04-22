import json
from enum import Enum
from typing import Union, Optional
import requests
from fastapi import FastAPI, HTTPException
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel

from CRM_Assistant.backend.ai_agent.run_agent_with_history import get_last_decision_trace
from CRM_Assistant.backend.routes.Ticket import router as ticket_router
from fastapi.routing import APIRoute
from CRM_Assistant.backend.ai_agent.agent import run_agent_with_history, is_continuation
from CRM_Assistant.backend.schemas.Ticket import AgentRequest

app = FastAPI(title="HubSpot Integration")
app.include_router(ticket_router)
@app.get("/")
def read_root():
    return {"Hello": "World"}
conversation_store = {}
from uuid import uuid4
@app.post("/agent")
def agent_endpoint(req: AgentRequest):
    conversation_id = req.conversation_id or str(uuid4())

    conversation = conversation_store.get(conversation_id, {
        "history": [],
        "after": None
    })
    continuation = (
            is_continuation(req.message)
            and conversation.get("after") is not None
    )

    if not continuation:
        conversation["after"] = None
    print("USER MESSAGE:", req.message)
    print("CONTINUATION:", continuation)
    print("CURSOR IN USE:", conversation["after"])

    history = conversation["history"]
    after = conversation["after"]
    # 🚫 Pagination exhausted guard
    if is_continuation(req.message) and conversation.get("after") is None:
        return {
            "conversation_id": conversation_id,
            "response": {
                "message": "No more tickets to show."
            }
        }

    # Append user message
    history.append(HumanMessage(content=req.message))

    # Run agent WITH cursor
    # Run agent
    response = run_agent_with_history(history, after , continuation)

    assistant_response = response["response"]
    print("ASSISTANT RESPONSE:", assistant_response)

    if isinstance(assistant_response, dict):
        next_after = (
            assistant_response.get("paging", {})
                .get("next", {})
                .get("after")
        )

        conversation["after"] = next_after

    # Store assistant message in memory (string only)
    assistant_content = assistant_response
    if isinstance(assistant_content, dict):
        assistant_content = json.dumps(assistant_content)

    history.append(AIMessage(content=assistant_content))

    conversation_store[conversation_id] = conversation

    return {
        "conversation_id": conversation_id,
        "response": assistant_response
    }

@app.get("/agent/last-decision")
def last_decision():
    trace = get_last_decision_trace()
    if not trace:
        return {"message": "No decision recorded yet"}
    return trace.to_dict()
if __name__ == '__main__':
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8008)