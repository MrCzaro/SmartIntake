import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


INTAKE_SCHEMA = [
    {"id": "chief_complaint", "q": "What is your main issue today?"},
    {"id": "location", "q": "Where is the problem located?"},
    {"id": "onset", "q": "When did it start?"},
    {"id": "severity", "q": "How severe is it from 1 to 10?"},
    {"id": "relieving_factors", "q": "What makes it better?"},
    {"id": "aggravating_factors", "q": "What makes it worse?"},
    {"id": "fever", "q": "Have you had a fever?"},
    {"id": "medications", "q": "What medications are you currently taking?"},
    {"id": "conditions", "q": "Any chronic conditions?"},
    {"id": "prior_contact", "q": "Have you contacted us about this before?"}
]

@dataclass
class Message:
    """
    Represents a single entry in the chat history.
    
    Attributes:
        role (str): The sender's identity (beneficiary, nurse, or assistant).
        content(str): The actual text or summary data of the message.
        timestamp (datetime): When the message was created.
        phase (str): The context of the message, such as 'intake', 'system', 'chat', or 'summary'
    """
    role : str # beneficiary | nurse | assistant
    content : str
    timestamp :  datetime 
    phase : str # intake | system

    @property
    def display_time(self) -> str:
        """Returns the timestamp formatted for the UI  (e.g '2026-01-01 15:00")"""
        return self.timestamp.strftime("%Y-%m-%d %H:%M")
    @classmethod
    def from_row(cls, row):
        """Rehydrates a Message instance from a database row dictionary with a safety check on the timestamp."""
        try:
            ts = datetime.fromisoformat(row["timestamp"])
        except (ValueError, TypeError):
            ts = datetime.now()  # Fallback to current time if parsing fails
            print(f"Warning: Corrupt timestamp found in session {row.get('session_id')}")
        
        return cls(
            role=row["role"],
            content=row["content"],
            # Converting the string back to a Python datetime object
            timestamp=ts,
            phase=row["phase"]
        )

@dataclass
class IntakeState:
    """
    Tracks the progress and results of the initial medical intake workflow.
    
    Attributes:
        current_index (int): The index of the current question in the schema.
        answers dict[str, str]: Collection of all completed responses.
        completed (bool): Whether the user has finished all intake questions.
    """
    current_index : int = 0
    answers : dict[str, str] = field(default_factory=dict)
    completed : bool = False

class ChatState(str, Enum):
    """
    Represents the lifecycle stages of a beneficiary's interaction.
    
    States:
        - INTAKE: The AI is gathering initial medical information.
        - WAITING_FOR_NURSE: Intake is done. Session is in the nurse's queue.
        - NURSE_ACTIVE: A human nurse is currently chatting with the beneficiary.
        - URGENT: High-priority state triggered by red flags or manual SOS.
        - CLOSED: The interaction has been finished/closed.
        - COMPLETED: The session has been finalized and archived.
    """
    INTAKE = "intake"
    WAITING_FOR_NURSE = "waiting_for_nurse"
    NURSE_ACTIVE = "nurse_active"
    URGENT = "urgent"
    CLOSED = "closed"
    COMPLETED = "completed"

@dataclass
class ChatSession:
    """
    The central data container for a single patient interaction.
    
    This class tracks the entire history of the session, including the current 
    workflow state, all chat messages, and the structured answers provided during
    the intake phase.
    """
    session_id : str
    user_email : str
    state : ChatState = ChatState.INTAKE 
    created_at: datetime = field(default_factory=datetime.now)
    messages: list[Message] = field(default_factory=list)
    intake : IntakeState = field(default_factory=IntakeState)
    summary: str | None = None
    is_read : bool = False

    @property
    def id(self):
        return self.session_id

    @staticmethod
    def _coerce_state(raw) -> ChatState:
        """
        Converts DB value to ChatState safely.
        Defaults to INTAKE if anything wrong.
        """
        if isinstance(raw, ChatState):
            return raw
        if isinstance(raw, str):
            raw = raw.strip().upper()
            if raw in ChatState.__members__:
                return ChatState[raw]
            
        # Fallback - intake is the default
        return ChatState.INTAKE
    
    @classmethod
    def from_row(cls, row):
        """Creates a ChatSession from DB row dictionary."""
        # Handle the Intake JSON
        raw_json = row["intake_json"]
        try:
            intake_data = json.loads(raw_json) if raw_json else "{}"
        except Exception:
            intake_data = {}
     
        intake_state = IntakeState(
            current_index=intake_data.get("current_index", 0),
            answers=intake_data.get("answers", {}),
            completed=bool(intake_data.get("completed", False))
        )
        
        raw_date = row["created_at"]
        try:
            ca = datetime.fromisoformat(raw_date.replace(" ", "T")) if raw_date else datetime.now()
        except:
            ca = datetime.now()

        state = cls._coerce_state(row["state"])
        return cls(
            session_id=row["id"],
            user_email=row["user_email"],
            state=state,
            created_at=ca,
            summary=row["summary"],
            intake=intake_state,
            is_read=bool(row["is_read"]),
            messages=[]
        )