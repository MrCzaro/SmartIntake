from dataclasses import asdict
import json, sqlite3
from datetime import datetime, timedelta
from models import ChatSession, ChatState, Message, INTAKE_SCHEMA
from config import *


def intake_finished(s: ChatSession) -> bool:
    """
    Checks if the beneficiary has answered all questions in the intake schema.
    
    Returns:
        bool: True if the current index matches or exceeds the schema length.
    """
    return s.intake.current_index >= len(INTAKE_SCHEMA)


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
    s.intake.completed = True
    intake_json = json.dumps(asdict(s.intake))
    db_update_session(db, s.session_id, state=s.state, summary=s.summary, intake_json=intake_json, is_read=False)
    
    # Add it as a hidden message in the chat history
    if s.summary:
        sum_msg = Message(role="assistant", content=s.summary, timestamp=datetime.now(), phase="summary")
        db_save_message(db, s.session_id, sum_msg)
    
    sys_content = "Thank you. Your intake is complete. A nurse will review your case shortly."
    sys_msg = Message(role="assistant", content=sys_content, timestamp=datetime.now(), phase="system")
    db_save_message(db, s.session_id, sys_msg)
    db.commit()

       
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
    db_update_session(db, s.session_id, state=s.state, was_urgent=1)
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
    db_update_session(db, s.session_id, state=s.state, was_urgent=1)
    system_message(s.session_id, db, "Emergency button pressed. A nurse has been notified immediately.")

def nurse_joins(s: ChatSession, db: sqlite3.Connection):
    """
    Transitions a session from a waiting or urgent state to an active nurse chat.
    
    Args:
        s (ChatSession): The session the nurse is entering.
        db (sqlite3.Connection): Open database connection.
        
    """
    if s.state not in (ChatState.WAITING_FOR_NURSE, ChatState.URGENT):
        return

    if s.state == ChatState.WAITING_FOR_NURSE:
        s.state = ChatState.NURSE_ACTIVE
        db_update_session(db, s.session_id, state=s.state, nurse_joined=1)
    else:
        db_update_session(db, s.session_id, nurse_joined=1)

    system_message(s.session_id, db, "A nurse has joined your case.")

async def generate_intake_summary(s: ChatSession):
    """
    Asynchronously generates a medical summary of the beneficiary's intake answers.
    
    This function complies all recorded intake responses and sends them to a Gemini generative model.
    It uses a tiered fallback system, attempting newer models first and falling back to older versions
    if an error occurs. The resulting summary is stored directly in the ChatSession object.
    
    Args:
        s (ChatSession): The session containing the intake answers to be summarized.
        
    Note: 
        Strict system instructions are provided to ensure the AI remains purely descriptive 
        and avoids providing any medical advice or diagnoses.
    """
    # Prepare the data string from intake answers
    question_map = {item["id"]: item["q"] for item in INTAKE_SCHEMA}

    summary_lines = []
    for q_id, answer in s.intake.answers.items():
        question_text = question_map.get(q_id, q_id)
        summary_lines.append(f"Question: {question_text}\nAnswer: {answer}")

    data = "\n".join(summary_lines)
    instructions = """You are a medical intake assistant. 
    Your only task is to summarize the patient's answers into a short, professional note for a nurse. 
    Describe the symptoms and current situation clearly. 
    Stricly forbidden: Do not provide medical advice, suggestion, diagnoses, or care plans."""
    
    models  = ["models/gemini-2.5-flash", "models/gemini-2.0-flash", "models/gemini-1.5-flash"]
    # Call the Gemini API
    for model in models:
        try:

            response = await client.aio.models.generate_content(
                model = model,
                contents=f"Please summarize these patient answers:\n\n{data}",
                config={"system_instruction" : instructions})
            
            if response and response.text:
                s.summary = response.text
                return 
        except Exception as e:
            print(f"Model {model} failed: {e}")
            continue # try next model from the models list
    if not s.summary:
        s.summary = "System Note: Automated summary could not be generated. Please review patient responses manually."


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
            intake_json = json.dumps(asdict(session.intake))
            now = datetime.utcnow().isoformat()
            db.execute("INSERT INTO sessions (id, user_email, state, intake_json, is_read, created_at, last_activity) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (session.session_id, session.user_email, session.state.value, intake_json, 0, now, now))
            
            # Save the First Message
            db.execute("INSERT INTO messages (session_id, role, content, timestamp, phase) VALUES (?, ?, ?, ?, ?)",
                       (session.session_id, first_message.role, first_message.content, first_message.timestamp.isoformat(), first_message.phase))
        
        return True
    except Exception as e:
        print(f"Database Error: {e}")
        return False
    
def db_save_message(db: sqlite3.Connection, session_id: str, message: Message):
    """
    Saves a chat message to the database and updates the session's last_activity timestamp.

    
    Args:
        db (sqlite3.Connection): Open database connection.
        session_id (str): The ID of the session the message belongs to.
        message (Message): The message to store.
    """
    now = datetime.utcnow().isoformat()

    # Save the message
    db.execute("INSERT INTO messages (session_id, role, content, timestamp, phase) VALUES (?, ?, ?, ?, ?)",
               (session_id, message.role, message.content, message.timestamp.isoformat(), message.phase))
    
    # Update last_activity timestamp
    db.execute("UPDATE sessions SET last_activity = ? WHERE id = ?", (now, session_id))
    
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
    db.commit()

def db_get_session(db: sqlite3.Connection, sid: str) -> ChatSession | None:
    """
    Retrieves a single session object by its ID.
    """
    row = db.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
    if not row:
        return None
    return ChatSession.from_row(row) if row else None

def db_get_user_sessions(db, user_email: str) -> list[ChatSession]:

    """
    Retrieves all chat sessions for a specific user, sorted by most recent.
    """
    rows = db.execute("SELECT * FROM sessions WHERE user_email = ? ORDER BY created_at DESC", (user_email,)).fetchall()

    # Map the rows to ChatSession object
    return [ChatSession.from_row(row) for row in rows]



def get_nurse_dashboard_data(db: sqlite3.Connection):
    """
    Returns sessions ready for nurse review and counts urgent cases..
    Excludes INTAKE (active) and CLOSED sessions.
    """
    # Run the cleanup first 
    db_cleanup_stale_sessions(db)

    # Get Urgent count 
    urgent_count = get_urgent_count(db)

    # Fetch actionable sessions
    excluded_states = [ChatState.CLOSED.value, ChatState.COMPLETED.value, ChatState.INTAKE.value]
    placeholders = ",".join(["?"] * len(excluded_states))
    query = f"SELECT * FROM sessions WHERE state NOT IN ({placeholders}) ORDER BY CASE WHEN state = ? THEN 0 ELSE 1 END, created_at DESC"
    params = excluded_states + [ChatState.URGENT.value]
    rows = db.execute(query, params).fetchall()
    sessions = [ChatSession.from_row(row) for row in rows]

    return sessions, urgent_count 

def close_session(s: ChatSession, db: sqlite3.Connection):
    """
    Marks a session as closed and saves the timestamp.
    """
    db.execute("UPDATE sessions SET state = ? WHERE id = ?", (ChatState.CLOSED.value, s.session_id))
    
    s.state = ChatState.CLOSED
    
    close_msg = Message(role="assistant", content="This session has been closed.", timestamp=datetime.now(), phase="system")
    db_save_message(db, s.session_id, close_msg)
    db.commit()

def complete_session(session_id: str, nurse_email: str, completion_note: str, db: sqlite3.Connection):
    """
    Formally closes a session with nurse documentation.
    
    This is used primarily for urgent cases where a nurse has attempted follow-up
    and is formally closing the case with notes.
    
    Args:
        session_id (str): The session to complete
        nurse_email (str): Email of the nurse completing the case
        completion_note (str): Required documentation of how case was resolved
        db (sqlite3.Connection): Open database connection

    Returns:
        bool: True if successful, False otherwise
    """
    # Validate minimum note length (20 characters)
    if len(completion_note.strip()) < 20:
        return False
    
    # Update session state to COMPLETED
    db.execute("UPDATE sessions SET state = ? WHERE id = ?", (ChatState.COMPLETED.value, session_id))
    completion_msg = Message(
        role="assistant",
        content=f"**Case Completed by Nurse {nurse_email}**\n\n{completion_note}",
        timestamp=datetime.now(),
        phase="completion"
    )    
    db_save_message(db, session_id, completion_msg)
    db.commit()
    return True

def get_session_helper(db: sqlite3.Connection, sid: str) -> ChatSession:
    """
    Helper function to retrieve a session and its all messages in one go..
    """
    s = db_get_session(db, sid)
    if not s:
        return None
    s.messages = db_get_messages(db, sid)
    
    return s

def db_get_messages(db: sqlite3.Connection, sid: str) -> list[Message]:
    """
    Retrieves all messages for a session, ordered chronologically.
    """
    rows = db.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp ASC", (sid,)).fetchall()
    return [Message.from_row(row) for row in rows]


def get_urgent_count(db: sqlite3.Connection) -> int:
    """
    Retrieves the current count of urgent chat sessions from the database.
    
    Args:
        db (sqlite3.Connection): Open database connection.
    """
    # Only count sessions in URGENT state
    result = db.execute("SELECT COUNT(*) FROM sessions WHERE state = ?",(ChatState.URGENT.value,)).fetchone()
    return result[0] if result else 0



def db_cleanup_stale_sessions(db: sqlite3.Connection):
    """
    Automatically manages session timeouts using a two-tier system:

    Tier 1 - Soft Timeout (20 minutes):
        - moves sessions to INACTIVE state
        - they can still semlessly resume if beneficiary returns
        - removes from active nurse queue to reduce clutter

    Tier 2 - Hard Timeout (80 minutes total = 20 + 60 grace period):
        - permanently closes INACTIVE sessions
        - beneficiary must make explicit choice to continue or start fresh

    IMPORTANT: URGENT sessions are never auto-timed out. They remain open
    until explicitly closed by a nurse with proper documentation.
    """
    now = datetime.now()
    # Tier 1: Soft timeout
    

    # Find sessions that should move to INACTIVE
    active_states = [ChatState.INTAKE.value, ChatState.WAITING_FOR_NURSE.value, ChatState.NURSE_ACTIVE.value]
    placeholders = ",".join(["?"] * len(active_states))

    query =f"SELECT id, state FROM sessions WHERE state IN ({placeholders}) AND state != ? AND datetime(last_activity) < datetime('now', '-20 minutes')"
    params = active_states + [ChatState.URGENT.value]
    
    stale_sessions = db.execute(query, params).fetchall()

    for session in stale_sessions:
        sid = session["id"]


        # Move to INACTIVE
        db.execute("UPDATE sessions SET state = ? WHERE id = ?", (ChatState.INACTIVE.value, sid))

        time_str = now.strftime('%I:%M %p')
        message_content = f"⏸️ This session became inactive at {time_str} due to inactivity. You have 1 hour to resume before it closes permanently."
        # Add system message documenting the timeout
        timeout_msg = Message(
            role="assistant", 
            content=message_content,#f"⏸️ This session became inactive at {time_str} due to inactivity. You have 1 hour to resume before it closes permanently.",
            timestamp=now, 
            phase="system"
        )
        db_save_message(db, sid, timeout_msg)
        
    # Tier 2: Hard timeout - permanently close INACTIVE sessions after grace period

    query = "SELECT id FROM sessions WHERE state = ? AND datetime(last_activity) < datetime('now', '-80 minutes')"
    
    expired_sessions = db.execute(query, (ChatState.INACTIVE.value,)).fetchall()

    for session in expired_sessions:
        sid = session["id"]

        # Permanently close
        db.execute("UPDATE sessions SET state = ? WHERE id=?", (ChatState.CLOSED.value, sid))

        time_str = now.strftime('%I:%M %p')
        message_content = f"⏸️ This session became inactive at {time_str} due to inactivity. You have 1 hour to resume before it closes permanently."
        print(f"[DEBUG] Message content: {message_content}")
        # Add system message documenting the permanent closure
        closure_msg = Message(
            role="assistant",
            content=message_content,#f"🔒 This session was permanently closed at {time_str} due to extended inactivity. You can view the history or start a new consultation.",
            timestamp=now,
            phase="system"
        )
        db_save_message(db,sid, closure_msg)
        print(f"[CLEANUP] Session {sid} permanently CLOSED after grace period")

    db.commit()


def reactivate_session(session_id: str, db: sqlite3.Connection) -> tuple[bool, str]:
    """
    Attempts to reactive an INACTIVE session when a patient sends a message.
    
    Returns:
        tuple[bool, str]: (success, message)
            - if within grace period: (True, "resumed")
            - if past grace period: (False, "expired")
            - if not inactive: (False, "not_inactive")
    """
    s = db_get_session(db, session_id)
    if not s: return (False, "not_found")

    # Only INACTIVE session can be reactivated
    if s.state != ChatState.INACTIVE:
        return (False, "not_found")
    
    # Check if still within grace period
    grace_period_end = s.last_activity + timedelta(minutes=80)
    now = datetime.utcnow()

    if now > grace_period_end:
        # Past grace period - cannot auto-reactivate
        return (False, "expired")
    
    if s.intake and s.intake.completed:
        new_state = ChatState.WAITING_FOR_NURSE
        db_update_session(db, session_id, state=new_state, is_read=False)
    else:
        new_state = ChatState.INTAKE
        db_update_session(db, session_id, state=new_state)

    # Add system message about reactivation
    reactivation_msg = Message(
        role="assistant",
        content=f"✅ Session resumed at {now.strftime('%I:%M %p')}. You may continue where you left off.",
        timestamp=now,
        phase="system"
    )
    db_save_message(db, session_id, reactivation_msg)
    db.commit()
    print(s.state)

    return (True, "resumed")
    
