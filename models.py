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

@dataclass
class IntakeAnswer:
    """
    Stores a specific response provided by a beneficiary during the intake process.
    
    Attributes:
        question_id (str): Unique identifier for the question from the schema.
        question (str): The text of the question asked.
        answer (str): The user's provided response.
        timestamp (datetime): When the answer was recorded.
    """
    question_id : str
    question : str
    answer : str
    timestamp : datetime

@dataclass
class IntakeState:
    """
    Tracks the progress and results of the initial medical intake workflow.
    
    Attributes:
        current_index (int): The index of the current question in the schema.
        answers (list[IntakeAnswer]): Collection of all completed responses.
        completed (bool): Whether the user has finished all intake questions.
    """
    current_index : int = 0
    answers : list[IntakeAnswer] = field(default_factory=list)
    completed : bool = False

class ChatState(str, Enum):
    """
    Represents the lifecycle stages of a beneficiary's interaction.
    
    States:
        - INTAKE: The AI is gathering initial medical information.
        - WAITING_FOR_NURSE: Intake is done. Session is in the nurse's queue.
        - NURSE_ACTIVE: A human nurse is currently chatting with the beneficiary.
        - URGENT: High-priority state triggered by red flags or manual SOS.
        - CLOSED: The interaction has concluded.
    """
    INTAKE = "intake"
    WAITING_FOR_NURSE = "waiting_for_nurse"
    NURSE_ACTIVE = "nurse_active"
    URGENT = "urgent"
    CLOSED = "closed"

@dataclass
class ChatSession:
    """
    The central data container for a single patient interaction.
    
    This class tracks the entire history of the session, including the current 
    workflow state, all chat messages, and the structured answers provided during
    the intake phase.
    """
    session_id : str
    state : ChatState = ChatState.INTAKE 
    messages: list[Message] = field(default_factory=list)
    intake : IntakeState = field(default_factory=IntakeState)
    summary: str | None = None