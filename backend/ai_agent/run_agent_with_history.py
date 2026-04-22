from datetime import datetime
from typing import List, Dict, Any, Optional


class DecisionTrace:
    def __init__(self, user_message: str):
        self.user_message = user_message
        self.intent: Optional[str] = None
        self.rules_applied: List[str] = []
        self.tools_called: List[str] = []
        self.tool_args: List[Dict[str, Any]] = []
        self.outcome: Optional[str] = None
        self.timestamp = datetime.utcnow()

    def to_dict(self):
        return {
            "user_message": self.user_message,
            "intent": self.intent,
            "rules_applied": self.rules_applied,
            "tools_called": self.tools_called,
            "tool_args": self.tool_args,
            "outcome": self.outcome,
            "timestamp": self.timestamp.isoformat()
        }


LAST_DECISION_TRACE: Optional[DecisionTrace] = None


def save_decision_trace(trace: DecisionTrace):
    global LAST_DECISION_TRACE
    LAST_DECISION_TRACE = trace


def get_last_decision_trace():
    return LAST_DECISION_TRACE
