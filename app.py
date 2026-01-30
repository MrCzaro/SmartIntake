from fasthtml.common import *
from monsterui.all import *
from starlette.staticfiles import StaticFiles
from uuid import uuid4
from datetime import datetime
from starlette.middleware.sessions import SessionMiddleware
from dataclasses import asdict
import json
from components import * 
from logic import *
from models import * 
from auth import *
from database import *


# Initialize DB on startup
init_db()

# -- App setup ---
app = FastHTML(hdrs=hdrs, static_dir="static")
app.add_middleware(DatabaseMiddleware)
app.add_middleware(SessionMiddleware, secret_key="secret-session-key")
app.mount("/static", StaticFiles(directory="static"), name="static")
rt = app.route



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
def start(request):
    db = request.state.db
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
async def poll_chat(request, sid: str):
    db = request.state.db
    role = request.session.get("role")


    messages = db_get_messages(db, sid)
    return Div(*[chat_bubble(m, role) for m in messages],id="chat-messages")

@rt("/nurse/poll")
@login_required
def nurse_poll(request):
    db = request.state.db
    guard = require_role(request, "nurse")
    if guard: return guard

    active_sessions, urgent_count = get_nurse_dashboard_data(db)
   
    if not active_sessions:
        case = Div("No active cases.", cls="alert alert-info")
    else:
        case = Table(
            Thead(Tr(Th("Patient"), Th("Status"), Th("Last Symptom"), Th("Action"))),
            Tbody(*[session_row(s) for s in active_sessions]),
            cls="table w-full"
        )



    return case, urgent_counter(urgent_count)

@rt("/{role}/{sid}/close")
@login_required
async def post_close_chat(request, role: str, sid: str):
    db = request.state.db
    s = get_session_helper(db, sid)
    if not s: return layout(request, Card(H3("Session not found")), "Error")

    # Update Logic
    close_session(s, db)

    # Redirect or Update UI
    if role == "nurse":
        return Response(headers={"HX-Redirect": "/nurse"})
    
    return Div(
        Card(
            H3("Session Ended"),
            P("Thank you for using MedAIChat. Your transcript has been saved."),
            A("Return to Dashboard", href="/", cls="btn btn-primary"),
            cls="p-8 text-center"
        ),
        id="chat-container"
    )

### Beneficiary Part

@rt("/beneficiary/{sid}")
@login_required
def beneficiary_view(request, sid: str):
    db = request.state.db
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
async def beneficiary_send(request, sid: str):
    db = request.state.db
    guard = require_role(request, "beneficiary")
    if guard: return guard

    role = request.session.get("role")

    s = get_session_helper(db, sid)
    if not s: return layout(request, Card(H3("Session not found")), "Error")

    form = await request.form()
    message = form.get("message", "").strip()

    if not message: return await poll_chat(request, sid)
    
    new_msg = Message(role=role, content=message, timestamp=datetime.now(), phase = "intake" if s.state == ChatState.INTAKE else "chat")
    db_save_message(db, sid, new_msg)
    # Reset is_read 
    db_update_session(db, sid, is_read=False)


    
    if s.state == ChatState.INTAKE:
        red_flags = ["chest pain", "shortness of breath", "can't breathe", "severe bleeding", "unconscious", "stroke", "heart attack"]
        is_urgent = any(flag in message.lower() for flag in red_flags)
        
        if is_urgent:
            urgent_bypass(s, db)
        else:
            q_info = INTAKE_SCHEMA[s.intake.current_index]
            s.intake.answers[q_info["id"]] = message
            s.intake.current_index += 1

            db_update_session(db, sid, intake_json=json.dumps(asdict(s.intake)))

            if s.intake.current_index >= len(INTAKE_SCHEMA):
                s.intake.completed = True
                await complete_intake(s, db)
            else:
                # Save Assistant's next question
                next_q = INTAKE_SCHEMA[s.intake.current_index]["q"]
                next_msg = Message(role="assistant", content=next_q, timestamp=datetime.now(), phase="intake")
                db_save_message(db, sid, next_msg)
    db.commit()
    messages = db_get_messages(db, sid)
    return Div(*[chat_bubble(m, role) for m in messages], id="chat-messages")

@rt("/beneficiary/{sid}/emergency")
@login_required
def beneficiary_emergency(request, sid: str):
    db = request.state.db
    guard = require_role(request, "beneficiary")
    if guard: return guard

    s = get_session_helper(db, sid)
    if not s: return layout(request, Card(H3("Session not found")), "Error")
    
    manual_emergency_escalation(s, db)

    sos_msg = Message(role="assistant", content="Emergency escalation has been activated.", timestamp=datetime.now(), phase="system")
    db_save_message(db, sid, sos_msg)

    # Refresh messages for the UI
    s.messages = db_get_messages(db, sid)   
    role = request.session.get("role")
    chat = Div(*[chat_bubble(m, role) for m in s.messages], id="chat-messages")
    
    header = emergency_header(s)
    header.attrs["hx-swap-oob"] = "true"
    form = beneficiary_form(sid, s)
    form.attrs["hx-swap-oob"] = "true"
    controls = beneficiary_controls(s)
    controls.attrs["hx-swap-oob"] = "true"


    return chat, header, form, controls


###  Nurse Part 
@rt("/nurse")
@login_required
def nurse_dashboard(request):
    db = request.state.db
    guard = require_role(request, "nurse")
    if guard: return guard

    content = Titled( "Nurse Dashboard", Div("Urgent: 0", id="urgent-count", cls="badge badge-ghost"),
        Div(id="nurse-cases", hx_get="/nurse/poll", hx_trigger="load, every 3s", hx_swap="innerHTML"))
    
    return layout(request, content, page_title = "Nurse Dashboard - MedAIChat")


@rt("/nurse/{sid}")
@login_required
def nurse_view(request, sid: str):
    db = request.state.db
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
async def nurse_send(request, sid : str):
    db = request.state.db
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

@rt("/nurse/session/{sid}/close")
@login_required
async def post_close_session(request, sid: str):
    db = request.state.db
    guard = require_role(request, "nurse")
    if guard: return guard

    # Update state to CLOSED
    db.execute("UPDATE sessions SET state = ? WHERE session_id = ?", (ChatState.CLOSED.value, sid))

    # Add a final system message
    db_save_message(db, sid,
                    Message(role="assistant", content="Session closed by nurse.", timestamp=datetime.now(), phase="system"))
    db.commit()

    # Return empty string to remove the row from the dashboard
    return ""

@rt("/nurse/session/{sid}") # not used 
@login_required
def get_session_detail(request, sid: str):
    db = request.state.db
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
def post_finalize(request, sid: str, nurse_summary: str):
    db = request.state.db
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

@rt("/nurse/archive") # Not used
@login_required
def nurse_archive(request):
    db = request.state.db
    guard = require_role(request, "nurse")
    if guard: return guard

    # Fetch completed sessions
    rows = db.execute("SELECT * FROM sessions WHERE state = ? ORDER BY id DESC", (ChatState.COMPLETED.value,)).fetchall()

    archived_sessions = [ChatSession.from_row(row) for row in rows]

    content = Titled("Medical Archives", past_sessions_table(archived_sessions), A("Back to Dashboard", href="/nurse", cls="btn btn-outline mt-4"))

    return layout(request, content, page_title="Nurse Archive - MedAIChat")

serve()

