import sqlite3
from datetime import datetime
from typing import Dict
from fasthtml.common import HTTPException
from models import ChatSession, ChatState, Message, INTAKE_SCHEMA
from components import *



def intake_finished(s: ChatSession) -> bool:
    """
    Checks if the beneficiary has answered all questions in the intake schema.
    
    Returns:
        bool: True if the current index matches or exceeds the schema length.
    """
    return s.intake.current_index >= len(INTAKE_SCHEMA)

def current_intake_question(s: ChatSession) -> str | None:
    """
    Retrieves the text of the next question the beneficairy needs to answer.
    
    Returns:
        str: The question text, or None if the intake is already finised.
    """
    if intake_finished(s): return None
    return INTAKE_SCHEMA[s.intake.current_index]["q"]

def system_message(s: ChatSession, text: str):
    """
    Injects an automated system update into the chat history.
    
    System messages are used to inform the user of sate changes
    (e.g., 'A nurse has joined') and are styled differently in the UI.
    
    Args:
        s (ChatSession): The session to update .
        text (str) : The content of the system notification.
    """
    s.messages.append(Message(role="assistant", content=text,timestamp=datetime.now(),phase="system"))

async def complete_intake(s: ChatSession):
    """
    Finalizes the intake phase and moves the session to the nurse's queue.
    
    This function triggers the AI summary generation, appends it to the history for nurse review,
    and updates the session state to WAITING_FOR_NURSE.
    
    Args:
        s (ChatSession): The session to finalize."""
    if s.state != ChatState.INTAKE: return
    
    # Generate the intake summary
    await generate_intake_summary(s)
    
    # Add it as a hidden message in the chat history
    if s.summary:
        s.messages.append(Message(role="assistant", content=s.summary, timestamp=datetime.now(), phase="summary"))

    s.state = ChatState.WAITING_FOR_NURSE
    system_message(s, "Thank you. Your intake is complete. A nurse will review your case shortly.")
       
def urgent_bypass(s: ChatSession): 
    """
    Automatically escalates a case to URGENT status based on keyword detection.
    
    This bypasses the remaining intake questions to ensure immediate nurse notification when 
    critical symptoms are mentioned.
    
    Args:
        s (ChatSession): The session to escalate.
    """
    s.state = ChatState.URGENT
    system_message(s,"Your message suggests a potentially urgent condition. A nurse has been notified immediately.")

def manual_emergency_escalation(s: ChatSession):
    """
    Handles an explicit emergency request triggered by the beneficiary.
    
    Updates the session state to URGENT and adds a distinct system message identifying that the emergency
    button was used.
    
    Args:
        S (ChatSession): The session to escalate.
    """
    s.state = ChatState.URGENT
    system_message(s, "🚨 Emergency button pressed. A nurse has been notified immediately.")

def nurse_joins(s: ChatSession):
    """
    Transitions a session from a waiting or urgent state to an active nurse chat.
    
    Args:
        s (ChatSession): The session the nurse is entering.
        
    """
    if s.state not in (ChatState.WAITING_FOR_NURSE, ChatState.URGENT):
        return
    
    s.state = ChatState.NURSE_ACTIVE
    system_message(s, "A nurse has joined your case.")

def get_session_or_404(sessions: Dict[str, ChatSession], sid: str) -> ChatSession:
    """
    Retrieve a chat session by ID or raise a 404 error.
    
    Args:
        sessions (dict[str, ChatSession]): In-memory session store.
        sid (str) : Session ID.
        
    Raises:
        HTTPEXception: 404 if session does not exist.
        
    Returns:
        ChatSession: The requested chat session.
    """
    session = sessions.get(sid)
    if session is None: 
        raise HTTPException(404, "Session not found")
    return session

def get_beneficiary_ui_updates(sid: str, s: ChatSession):
    """
    Generates and prepares out-of-band (OOB) UI components for the beneficiary views.
    
    This helper centralizes the logic for updating the persistent UI elements
    (Header, Message Form, and Status Controls) that need to stay in sync with the
    ChatSession state (e.g., transitioning from INTAKE or URGENT).
    
    Args:
        sid (str) : The unique session ID for the chat.
        s(ChatSession): The current chat session object containing state and history.
        
    Returns:
        tuple: A tuple containing (header, form, controls), each with 
        the 'hx-swap-obb' attribute set to 'true'.
    """
    # Generate the components
    header = emergency_header(s)
    form = beneficiary_form(sid, s)
    controls = beneficiary_controls(s)
    # Mark them all for OOB swapping
    for component in (header, form, controls):
        component.attrs["hx-swap-oob"] = "true"
    return header, form, controls

### NEW
def db_create_session(db: sqlite3.Connection, session: ChatSession, first_message: Message):
    """
    Atomically creates a new session and its initial message.
    Args:
        db (sqlite3.Connection): Open database connection.
        session (ChatSession): The session to store.
        first_message (Message): The initial message to store.
    """
    try:
        with db: # Start transaction
            db.execute("INSERT INTO sessions (id, user_email, state, summary) VALUES (?, ?, ?, ?)",
                       (session.session_id, session.user_email, session.state.value, session.summary))
            
            # Save the First Message
            db.execute("INSERT INTO messages (session_id, role, content, timestamp, phase) VALUES (?, ?, ?, ? ?)",
                       session.session_id, first_message.role, first_message.content, first_message.timestamp.isoformat(), first_message.phase)
        return True
    except Exception as e:
        print(f"Databae Error: {e}")
        return False
    
def db_save_message(db: sqlite3.Connection, session_id: str, message: Message):
    """
    Saves a chat message to the database.
    
    Args:
        db (sqlite3.Connection): Open database connection.
        session_id (str): The ID of the session the message belongs to.
        message (Message): The message to store.
    """
    db.execute("INSERT INTO messages (session_id, role, content, timestamp, phase) VALUES (?, ?, ?, ?, ?)",
               (session_id, message.role, message.content, message.timestamp.isoformat(), message.phase))
    
def db_update_session(db: sqlite3.Connection, session_id: str, **kwargs):
    """
    Updates specific fields in a session.
    Usage: db_update_session(db, sid, state=ChatState.COMPLETED, summary="...")
    """
    if not kwargs:
        return
    
    # Build dynamically the SET part of the SQL string e.g., "state =?, summary =?"
    keys = [f"{k} = ?" for k in kwargs.keys()]
    query = f"UPDATE sessions SET {', '.join(keys)} WHERE id = ?"

    # Extract values and handle Enums automatically
    values = [v.value if hasattr(v, 'value') else v for v in kwargs.values()]
    values.append(session_id)
    
    db.execute(query, values)


def db_get_nurse_archive(db: sqlite3.Connection) -> list[ChatSession]:
    """
    Fetches all sessions that are ready for review or completed.
    Sorted by the most recent activity first.
    """
    rows = db.execute("SELECT * FROM sessions WHERE state !-= 'intake' ORDER BY id DESC").fetchall()

    return [ChatSession.from_row(row) for row in rows]