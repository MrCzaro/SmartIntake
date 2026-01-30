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
            db.execute("INSERT INTO sessions (id, user_email, state, intake_json, is_read) VALUES (?, ?, ?, ?, ?)",
                       (session.session_id, session.user_email, session.state.value, intake_json, 0))
            
            # Save the First Message
            db.execute("INSERT INTO messages (session_id, role, content, timestamp, phase) VALUES (?, ?, ?, ?, ?)",
                       (session.session_id, first_message.role, first_message.content, first_message.timestamp.isoformat(), first_message.phase))
        
        return True
    except Exception as e:
        print(f"Database Error: {e}")
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
    db.commit()

def db_get_session(db: sqlite3.Connection, sid: str) -> ChatSession | None:
    """
    Retrieves a single session object by its ID.
    """
    row = db.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
    return ChatSession.from_row(row) if row else None

def db_get_user_sessions(db, user_email: str) -> list[ChatSession]:
    """
    Retrieves all chat sessions for a specific user, sorted by most recent.
    """
    rows = db.execute("SELECT * FROM sessions WHERE user_email = ? ORDER BY created_at DESC", (user_email,)).fetchall()

    # Map the rows to ChatSession object
    return [ChatSession.from_row(row) for row in rows]

def db_get_nurse_archive(db: sqlite3.Connection) -> list[ChatSession]:
    """
    Fetches all sessions that are ready for review or completed.
    Sorted by the most recent activity first.
    """
    rows = db.execute("SELECT * FROM sessions WHERE state != 'intake' ORDER BY id DESC").fetchall()

    return [ChatSession.from_row(row) for row in rows]


def db_cleanup_stale_sessions(db: sqlite3.Connection):
    """
    Automatically closes sessions that have been inactive for > 20 minutes.
    """
    # Calculate the cutoff time (20 minutes ago)
    timeout_limit = (datetime.now() - timedelta(minutes=20)).isoformat()

    # Update sessions that are in INTAKE and have not been updated recently.
    db.execute("UPDATE sessions SET state = ? WHERE state = ? AND created_at < ?", (ChatState.CLOSED.value, ChatState.INTAKE.value, timeout_limit))
    db.commit()

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

    
    close_msg = Message(role="assistant", content="This session has been closed.", timestamp=datetime.now(), phase="system")
    db_save_message(db, s.id, close_msg)
    db.commit()

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


def get_urgent_count(db: sqlite3.Connection) -> int:
    """
    Retrieves the current count of urgent chat sessions from the database.
    
    Args:
        db (sqlite3.Connection): Open database connection.
    """
    # Only count sessions in URGENT state
    result = db.execute("SELECT COUNT(*) FROM sessions WHERE state = ?",(ChatState.URGENT.value,)).fetchone()
    return result[0] if result else 0


