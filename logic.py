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

def system_message(sid:str,  db: sqlite3.Connection, text: str):
    """
    Injects an automated system update into the chat history.
    
    System messages are used to inform the user of sate changes
    (e.g., 'A nurse has joined') and are styled differently in the UI.
    
    Args:
        s (ChatSession): The session to update .
        text (str) : The content of the system notification.
        db (sqlite3.Connection): Open database connection.
    """
    msg = Message(role="assistant", content=text,timestamp=datetime.now(),phase="system")
    db_save_message(db, sid, msg)

async def complete_intake(s: ChatSession, db: sqlite3.Connection):
    """
    Finalizes the intake phase, saves results to DB, and moves the session to the nurse's queue.
    
    This function triggers the AI summary generation, appends it to the history for nurse review,
    and updates the session state to WAITING_FOR_NURSE.
    
    Args:
        s (ChatSession): The session to finalize.
        db (sqlite3.Connection): Open database connection."""
    if s.state != ChatState.INTAKE: return
    
    # Generate the intake summary
    await generate_intake_summary(s)
    s.state = ChatState.WAITING_FOR_NURSE
    db_update_session(db, s.session_id, state=s.state, summary=s.summary)
    
    # Add it as a hidden message in the chat history
    if s.summary:
        sum_msg = Message(role="assistant", content=s.summary, timestamp=datetime.now(), phase="summary")
        db_save_message(db, s.session_id, sum_msg)
    
    sys_content = "Thank you. Your intake is complete. A nurse will review your case shortly."
    sys_msg = Message(role="assistant", content=sys_content, timestamp=datetime.now(), phase="system")
    db_save_message(db, s.session_id, sys_msg)

       
def urgent_bypass(s: ChatSession, db: sqlite3.Connection): 
    """
    Automatically escalates a case to URGENT status based on keyword detection.
    
    This bypasses the remaining intake questions to ensure immediate nurse notification when 
    critical symptoms are mentioned.
    
    Args:
        s (ChatSession): The session to escalate.
        db (sqlite3.Connection): Open database connection.
    """
    s.state = ChatState.URGENT
    db_update_session(db, s.session_id, state=s.state)
    system_message(s.session_id, db, "Your message suggests a potentially urgent condition. A nurse has been notified immediately.")

def manual_emergency_escalation(s: ChatSession, db: sqlite3.Connection):
    """
    Handles an explicit emergency request triggered by the beneficiary.
    
    Updates the session state to URGENT and adds a distinct system message identifying that the emergency
    button was used.
    
    Args:
        S (ChatSession): The session to escalate.
        db (sqlite3.Connection): Open database connection.
    """
    s.state = ChatState.URGENT
    db_update_session(db, s.session_id, state=s.state)
    system_message(s.session_id, db, "🚨 Emergency button pressed. A nurse has been notified immediately.")

def nurse_joins(s: ChatSession, db: sqlite3.Connection):
    """
    Transitions a session from a waiting or urgent state to an active nurse chat.
    
    Args:
        s (ChatSession): The session the nurse is entering.
        db (sqlite3.Connection): Open database connection.
        
    """
    if s.state not in (ChatState.WAITING_FOR_NURSE, ChatState.URGENT):
        return
    
    s.state = ChatState.NURSE_ACTIVE
    db_update_session(db, s.session_id, state=s.state)

    system_message(s.session_id, db, "A nurse has joined your case.")

# # temp - possible removal due to moving to database
# def get_session_or_404(sessions: Dict[str, ChatSession], sid: str) -> ChatSession:
#     """
#     Retrieve a chat session by ID or raise a 404 error.
    
#     Args:
#         sessions (dict[str, ChatSession]): In-memory session store.
#         sid (str) : Session ID.
        
#     Raises:
#         HTTPEXception: 404 if session does not exist.
        
#     Returns:
#         ChatSession: The requested chat session.
#     """
#     session = sessions.get(sid)
#     if session is None: 
#         raise HTTPException(404, "Session not found")
#     return session

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

def db_get_session(db: sqlite3.Connection, sid: str) -> ChatSession | None:
    """
    Retrieves a single session object by its ID.
    """
    row = db.execute("SELECT * FROM session WHERE id = ?", (sid,)).fetchone()
    return ChatSession.from_row(row) if row else None

def get_session_helper(db: sqlite3.Connection, sid: str) -> ChatSession:
    """
    Helper function to retrieve a session and its all messages in one go..
    """
    s = db_get_session(db, sid)
    if s:
        s.messages = db_get_messages(db, sid)
    return s

def db_get_messages(db: sqlite3.Connection, sid: str) -> list[Message]:
    """
    Retrieves all messages for a session, ordered chronologically.
    """
    rows = db.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp ASC", (sid,)).fetchall()
    return [Message.from_row(row) for row in rows]