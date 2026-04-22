from enum import Enum

from pydantic import BaseModel, Field
from typing import Optional


class TicketPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class TicketStatus(str, Enum):
    NEW = "NEW"
    WAITING_ON_CONTACT = "WAITING_ON_CONTACT"
    WAITING_ON_US = "WAITING_ON_US"
    CLOSED = "CLOSED"


HUBSPOT_STAGE_MAP = {
    TicketStatus.NEW: "1",
    TicketStatus.WAITING_ON_CONTACT: "2",
    TicketStatus.WAITING_ON_US: "3",
    TicketStatus.CLOSED: "4",
}


class TicketCreate(BaseModel):
    subject: str = Field(recquired=True, description="Subject Of The Ticket")
    content: str = Field(recquired=True, description="Content Of The String")
    priority: TicketPriority = Field(recquired=True, description="Priority Should Be LOW , MEDIUM, HIGH , URGENT")
    status: TicketStatus = Field(recquired=True,
                                 description="Should Be Anyone From This NEW,WAITING_ON_CONTACT,WAITING_ON_US,CLOSED")


class TicketUpdate(BaseModel):
    subject: Optional[str] = None
    content: Optional[str] = None
    priority: Optional[TicketPriority] = None

    status: Optional[TicketStatus] = None

    class Config:
        extra = "forbid"


class TicketSearch(BaseModel):
    subject: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None


class AgentRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = Field(
        default=None,
        description="Conversation identifier (UUID)"
    )

class PartialCreateTicket(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None