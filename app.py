from fasthtml.common import *
from monsterui.all import *
from starlette.staticfiles import StaticFiles
from uuid import uuid4
from datetime import datetime
from starlette.middleware.sessions import SessionMiddleware
from dataclasses import asdict

from components import * 
from logic import *
from models import * 
from auth import *
from database import *


# Initialize DB on startup
init_db()

# -- App setup ---
app = FastHTML(hdrs=hdrs, static_dir="static")
app.add_middleware(SessionMiddleware, secret_key="secret-session-key")
app.mount("/static", StaticFiles(directory="static"), name="static")
rt = app.route
sessions : dict[str, ChatSession] = {}


# --- Routes ---
@rt("/favicon.ico")
def favicon(request):
    """
    Redirects the browser to the static file.
    """
    return Redirect("/static/favicon.ico")

### Registration/Login/Logout
@rt("/signup")
async def signup_user(request):
    page_title="Signup - MedAIChat"
    if request.method == "GET":
        return layout(request, signup_card(), page_title)
    elif request.method == "POST":
        form = await request.form()

        email = form.get("email", "").strip().lower()
        password = form.get("password", "")
        repeat = form.get("repeat_password", "")
        role = form.get("role", "")

        if not email or not password or not role:
            return layout(request , signup_card("All fields are required.", email), page_title)
        
        if password != repeat:
            return layout(request, signup_card("Password do not match.", email), page_title)
        
        db = get_db()
        cur = db.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cur.fetchone():
            db.close()
            return layout(request, signup_card("User already exists.", email), page_title)
        
        db.execute("INSERT INTO users (email, password_hash, role) VALUES (?, ?, ?)",(email, hash_password(password), role))
        db.commit()
        db.close()

        request.session["user"] = email
        request.session["role"] = role

        return Redirect("/")

@rt("/login")
async def login(request):
    page_title = "Login - MedAIChat"
    if request.method == "GET":
        return layout(request, login_card(), page_title)
    elif request.method == "POST":
        form = await request.form()
        email = form.get("email", "").strip().lower()
        password = form.get("password", "").strip()

        if not email or not password:
            return layout(request, login_card("All fields are required.", email), page_title)
        
        db = get_db()
        cur = db.execute("SELECT email, password_hash, role FROM users WHERE email = ?",(email,))
        user = cur.fetchone()
        db.close()

        if not user or not verify_password(password, user["password_hash"]):
            return layout(request, login_card("Invalid credentials.", email), page_title)
        
        request.session["user"] = user["email"]
        request.session["role"] = user["role"]
        return Redirect("/")

@rt("/logout")
@login_required
def logout(request):
    request.session.clear()
    return Redirect("/login")

### Home Route
@rt("/")
@login_required
def index(request):
    role = request.session.get("role")

    if role == "beneficiary":
        return Redirect("/start")
    
    if role == "nurse":
        return Redirect("/nurse")
    
    # Fallback (future roles)
    return Redirect("/login")


# Start Session
@rt("/start")
@login_required
def start(request, db: sqlite3.Connection):
    sid = str(uuid4())
    email = request.session.get("user")

    # Create new session
    s = ChatSession(session_id=sid, user_email=email)

    # Create first message
    first_question = INTAKE_SCHEMA[0]["q"]
    msg = Message(role="assistant", content=first_question, timestamp=datetime.now(), phase="intake")

    # Commit to DB
    success = db_create_session(db, s, msg)
    if not success:
        return layout(request, Div("Sorry, we could not start your session.", cls="alert alert-error"), "Error - MedAIChat")

    return Redirect(f"/beneficiary/{sid}")

### Chat Route
@rt("/chat/{sid}/poll")
@login_required
def poll_chat(request, sid: str, db: sqlite3.Connection):
    role = request.session.get("role")


    messages = db_get_messages(db, sid)
    return Div(*[chat_bubble(m, role) for m in messages],id="chat-messages")

@rt("/nurse/poll")
@login_required
def nurse_poll(request, db: sqlite3.Connection):
    guard = require_role(request, "nurse")
    if guard: return guard

    # Fetch sessions that are not finished
    rows = db.execute("""
                      SELECT * FROM sessions
                      WHERE state NOT IN (?, ?)
                      ORDER BY CASE WHEN state =? THEN 0 ELSE 1 END, id DESC
                      """, (ChatState.CLOSED.vale, ChatState.COMPLETED.value, ChatState.URGENT.value)).fetchall()

    
    active_sessions = [ChatSession.from_row(row) for row in rows]

    # Get the specific count for the badge
    urgent_count = get_urgent_count(db)

    if not active_sessions:
        case = Div("No active cases.", cls="alert alert-info")
    else:
        case = Table(
            Thead(Tr(Th("Patient"), Th("Status"), Th("Last Symptom"), Th("Action"))),
            Tbody(*[session_row(s) for s in active_sessions]),
            cls="table w-full"
        )



    return case, urgent_counter(urgent_count)



### Beneficiary Part

@rt("/beneficiary/{sid}")
@login_required
def beneficiary_view(request, sid: str, db: sqlite3.Connection):
    guard = require_role(request, "beneficiary")
    if guard: return guard

    role = request.session.get("role")
    s = get_session_helper(db, sid)
    if not s: return layout(request, Card(H3("Session not found")), "Error")



    content = Div(
        emergency_header(s),
        Div(beneficiary_chat_fragment(sid,s, role), cls="container mx-auto p-4"),cls="min-h-screen bg-base-100") 

    return layout(request, content, page_title = "Beneficiary Chat - MedAIChat")


@rt("/beneficiary/{sid}/send")
@login_required
async def beneficiary_send(request, sid: str, db:sqlite3.Connection):
    guard = require_role(request, "beneficiary")
    if guard: return guard

    role = request.session.get("role")

    s = get_session_helper(db, sid)
    if not s: return layout(request, Card(H3("Session not found")), "Error")

    form = await request.form()
    message = form.get("message", "").strip()

    red_flags = ["chest pain", "shortness of breath", "can't breathe", "severe bleeding", "unconscious", "stroke", "heart attack"]
    
    if not message: return poll_chat(request, sid, db)
    new_msg = Message(role=role, content=message, timestamp=datetime.now(), phase = "intake" if s.state == ChatState.INTAKE else "chat")
    db_save_message(db, sid, new_msg)
    # Reset is_read 
    db_update_session(db, sid, is_read=False)


    
    if s.state == ChatState.INTAKE:
        is_urgent = any(flag in message.lower() for flag in red_flags)
        if is_urgent:
            urgent_bypass(db, s)
        else:
            # Get the current question details from the schema
            q_info = INTAKE_SCHEMA[s.intake.current_index]

            # Save the answer 
            s.intake.answers[q_info["id"]] = message
            s.intake.current_index += 1

            # Sync the progress to DB
            db_update_session(db, sid, intake_json=json.dumps(asdict(s.intake)))

            if s.intake.current_index >= len(INTAKE_SCHEMA):
                s.intake.completed = True
                await complete_intake(s, db)
            else:
                # Ask the next question
                next_q = INTAKE_SCHEMA[s.intake.current_index]["q"]
                next_msg = Message(role="assistant", content=next_q, timestamp=datetime.now(), phase="intake")
                db_save_message(db, sid, next_msg)

    return poll_chat(request, sid, db)


@rt("/beneficiary/{sid}/emergency")
@login_required
def beneficiary_emergency(request, sid: str, db: sqlite3.Connection):
    guard = require_role(request, "beneficiary")
    if guard: return guard

    s = get_session_helper(db, sid)
    if not s: return layout(request, Card(H3("Session not found")), "Error")
    
    manual_emergency_escalation(s)

    sos_msg = Message(role="assistant", content="Emergency escalation has been activated.", timestamp=datetime.now(), phase="system")
    db_save_message(db, sid, sos_msg)

    # Refresh messages for the UI
    s.messages = db_get_messages(db, sid)   
    role = request.session.get("role")
    chat = Div(*[chat_bubble(m, role) for m in s.messages], id="chat-messages")
    ui_bundle = get_beneficiary_ui_updates(sid, s)

    return chat, *ui_bundle


###  Nurse Part 
@rt("/nurse")
@login_required
def nurse_dashboard(request):
    guard = require_role(request, "nurse")
    if guard: return guard
    content = Titled( "Nurse Dashboard", Div("Urgent: 0", id="urgent-count", cls="badge badge-ghost"),
        Div(id="nurse-cases", hx_get="/nurse/poll", hx_trigger="load, every 3s", hx_swap="innerHTML"))
    
    return layout(request, content, page_title = "Nurse Dashboard - MedAIChat")


@rt("/nurse/{sid}")
@login_required
def nurse_view(request, sid: str, db: sqlite3.Connection):
    guard = require_role(request, "nurse")
    if guard: return guard

    role = request.session.get("role")

    s = get_session_helper(db, sid)
    if not s: return layout(request, Card(H3("Session not found")), "Error")
    nurse_joins(s, db)

    # Mark as read
    db_update_session(db, sid, is_read=True)

    content = Titled(f"Nurse Review - {s.user_email}",nurse_chat_fragment(sid, s, role))
    return layout(request, content, page_title  = "Nurse Review - MedAIChat")


@rt("/nurse/{sid}/send")
@login_required
async def nurse_send(request, sid : str, db : sqlite3.Connection):
    guard = require_role(request, "nurse")
    if guard: return guard
    role = request.session.get("role")

    s = db_get_session(db, sid)
    if not s: raise HTTPException(status_code=404, detail=f"Session {sid} not found.")

    form = await request.form()
    message = form.get("message", "").strip()

    if not message:
        return Div(*[chat_bubble(m, role) for m in s.messages], id="chat-messages")
    
    s.messages.append(Message(role="nurse", content=message, timestamp=datetime.now(), phase="chat"))
    nurse_joins(s)
    return Div(*[chat_bubble(m, role) for m in s.messages],id="chat-messages")


# New
@rt("/nurse/session/{sid}")
@login_required
def get_session_detail(request, sid: str, db : sqlite3.Connection):
    guard = require_role(request, "nurse")
    if guard: return guard
    
    s = get_session_helper(db, sid)
    if not s: 
        return layout(request, Card(H3("Session not found")), "Error")
    
    # Mark as read
    db_update_session(db, sid, is_read=True) 

    return render_nurse_review(s, s.messages)
    

rt("/nurse/session/{sid}/finalize")
@login_required
def post_finalize(request, sid: str, nurse_summary: str, db: sqlite3.Connection):
    guard = require_role(request, "nurse")
    if guard: return guard


    # Validation Check
    if not nurse_summary.strip():
        return Redirect(f"/nurse/{sid}?error=Summary+required")
    
    # Save the Nurse summary as a message 
    final_note = Message(role="assistant", content=f"NURSE SUMMARY: {nurse_summary}", timestamp=datetime.now(), phase="summary")
    db_save_message(db, sid, final_note)
    
    # Update DB
    db_update_session(db, sid, state=ChatState.COMPLETED, summary=nurse_summary, is_read=True)
    return Redirect("/nurse")

@rt("/nurse/archive")
@login_required
def nurse_archive(request, db: sqlite3.Connection):
    guard = require_role(request, "nurse")
    if guard: return guard

    # Fetch completed sessions
    rows = db.execute("SELECT * FROM sessions WHERE state = ? ORDER BY id DESC", (ChatState.COMPLETED.value,)).fetchall()

    archived_sessions = [ChatSession.from_row(row) for row in rows]

    content = Titled("Medical Archives", past_sessions_table(archived_sessions), A("Back to Dashboard", href="/nurse", cls="btn btn-outline mt-4"))

    return layout(request, content, page_title="Nurse Archive - MedAIChat")

serve()

# we left at The Nurse's Sidebar Notification