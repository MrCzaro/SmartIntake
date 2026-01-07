from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

@dataclass
class Message:
    role : str # beneficiary | nurse | assistant
    content : str
    timestamp :  datetime 
    phase : str # intake | system

@dataclass
class IntakeAnswer:
    question_id : str
    question : str
    answer : str
    timestamp : datetime

@dataclass
class IntakeState:
    current_index : int = 0
    answers : list[IntakeAnswer] = field(default_factory=list)
    completed : bool = False

class ChatState(str, Enum):
    INTAKE = "intake"
    WAITING_FOR_NURSE = "waiting_for_nurse"
    NURSE_ACTIVE = "nurse_active"
    URGENT = "urgent"
    CLOSED = "closed"

@dataclass
class ChatSession:
    session_id : str
    state : ChatState = ChatState.INTAKE 
    messages: list[Message] = field(default_factory=list)
    intake : IntakeState = field(default_factory=IntakeState)
    summary: str | None = None