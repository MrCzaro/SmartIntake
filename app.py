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
        return Redirect("/beneficiary")
    
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
    s.state = ChatState.INTAKE

    # Create first message
    first_question = INTAKE_SCHEMA[0]["q"]
    msg = Message(role="assistant", content=first_question, timestamp=datetime.now(), phase="intake")

    # Commit to DB
    success = db_create_session(db, s, msg)
    if not success:
        return layout(request, Div("Sorry, we could not start your session.", cls="alert alert-error"), "Error - MedAIChat")

    db_update_session(db, sid, state=ChatState.INTAKE)
    return Redirect(f"/beneficiary/{sid}")

### Chat Route
@rt("/chat/{sid}/poll")
@login_required
async def poll_chat(request, sid: str):
    db = request.state.db
    role = request.session.get("role")

    s = get_session_helper(db, sid)
    if not s: return layout(request, Card(H3("Session not found")), "Error")
    
    messages = Div(*[chat_bubble(m, role) for m in s.messages])

    if s.state == ChatState.CLOSED:       
        if role == "beneficiary":
            form = beneficiary_form(s.session_id, s)
        if role == "nurse":
            form = nurse_form(s.session_id, s)
        return messages, form
      
    return messages

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

### Beneficiary Part
@rt("/beneficiary")
@login_required
def beneficiary_dashboard(request):
    db = request.state.db
    guard = require_role(request, "beneficiary")
    if guard: return guard

    user_email = request.session.get("user")

    sessions = db_get_user_sessions(db, user_email)

    content = Titled(
        "My Consultations",
        Div(
            A("Start New Consultation", href="/start", cls="btn btn-primary mb-4"),
            Table(
                Thead(
                    Tr(
                        Th("Date"),
                        Th("Status"),
                        Th("Action")
                    )
                ),
                Tbody(
                    *[Tr(Td(s.created_at.strftime("%Y-%m-%d %H:%M")), Td(s.state.value),
                    Td(A("Open", href=f"/beneficiary/{s.id}", cls="btn btn-sm btn-outline"))) for s in sessions]
                ),
                cls="table w-full"
                )
            )
        )
    return layout(request, content, page_title="My Consultation")



@rt("/beneficiary/{sid}")
@login_required
def beneficiary_view(request, sid: str):
    db = request.state.db
    guard = require_role(request, "beneficiary")
    if guard: return guard

    role = request.session.get("role")
    s = get_session_helper(db, sid)
    if not s: return layout(request, Card(H3("Session not found")), "Error")

    # content = Div(
    #     emergency_header(s),
    #     Div(render_chat_view(s, role), cls="container mx-auto p-4"),cls="min-h-screen bg-base-100") 
    content = Titled(f"Beneficiary Chat", render_chat_view(s, role))
    return layout(request, content, page_title = "Beneficiary Chat - MedAIChat")


@rt("/beneficiary/{sid}/send")
@login_required
async def beneficiary_send(request, sid: str):
    db = request.state.db
    role = request.session.get("role")
    guard = require_role(request, "beneficiary")
    if guard: return guard

    s = get_session_helper(db, sid)
    if not s: return Response(status_code=404)

    form = await request.form()
    message = form.get("message", "").strip()
    if not message: return "" 
    
    
    user_msg  = Message(role=role, content=message, timestamp=datetime.now(), phase = "intake" if s.state == ChatState.INTAKE else "chat")
    
    db_save_message(db, sid, user_msg)
    db_update_session(db, sid, is_read=False)
    
    out = [chat_bubble(user_msg, role)] 

    if s.state == ChatState.INTAKE and s.intake and not s.intake.completed:
        intake = s.intake
        
        red_flags = ["chest pain", "shortness of breath", "can't breathe", "severe bleeding", "unconscious", "stroke", "heart attack"]
        if any(flag in message.lower() for flag in red_flags):
            urgent_bypass(s, db)
            db.commit()
            return Div(*out)
        
        if intake.current_index < len(INTAKE_SCHEMA):
            q_info = INTAKE_SCHEMA[intake.current_index]
            intake.answers[q_info["id"]] = message
            intake.current_index += 1
            db_update_session(db, sid, intake_json=json.dumps(asdict(intake)))

        if intake.current_index >= len(INTAKE_SCHEMA):
            intake.completed = True
            db_update_session(db, sid, intake_json=json.dumps(asdict(intake)))
            await complete_intake(s, db)
            db.commit()
            return Div(*out)

        else:
            next_q = INTAKE_SCHEMA[intake.current_index]["q"]
            next_msg = Message(role="assistant", content=next_q, timestamp=datetime.now(), phase="intake")
            db_save_message(db, sid, next_msg)
            out.append(chat_bubble(next_msg, "assistant"))
        
    
    db.commit()
    
    return Div(*out)


@rt("/beneficiary/{sid}/emergency")
@login_required
def beneficiary_emergency(request, sid: str):
    db = request.state.db
    guard = require_role(request, "beneficiary")
    if guard: return guard

    s = get_session_helper(db, sid)
    if not s: return Response(status_code=404)
    
    manual_emergency_escalation(s, db)

    sos_msg = Message(role="assistant", content="Emergency escalation has been activated.", timestamp=datetime.now(), phase="system")
    db_save_message(db, sid, sos_msg)
    db.commit()
    s = get_session_helper(db, sid)
    return emergency_header(s)

@rt("/beneficiary/{sid}/close")
@login_required
async def beneficiary_close(request, sid: str):
    db = request.state.db
    s = get_session_helper(db, sid)
    if not s: return Response(status_code=404)

    guard = require_role(request, "beneficiary")
    if guard: return guard

    close_session(s, db)
    db_save_message(db, sid, Message(role="assistant", content="Session closed by beneficiary", timestamp=datetime.now(), phase="system"))
    db.commit()

    s = get_session_helper(db, sid)

    if request.headers.get("HX-Request") == "true":
        return render_chat_view(s, "beneficiary")

    content = Div(
        Card(
            H3("Session Ended"),
            P("Thank you for using MedAIChat. Your session has been saved."),
            A("Return to Home", href="/", cls="btn btn-primary"),
            cls="p-8 text-center"
        ),
        id="chat-container"
    )

    return layout(request, content, page_title="End Chat - MedAIChat")

    

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

    content = Titled(f"Nurse Review - {s.user_email}", render_chat_view(s, role))
    return layout(request, content, page_title  = "Nurse Review - MedAIChat")


@rt("/nurse/{sid}/send")
@login_required
async def nurse_send(request, sid : str):
    db = request.state.db
    guard = require_role(request, "nurse")
    if guard: return guard

    s = get_session_helper(db, sid)
    if not s: return Response(status_code=404)

    form = await request.form()
    message = form.get("message", "").strip()
    if not message: return ""
    
    nurse_msg = Message(role="nurse", content=message, timestamp=datetime.now(), phase="chat")
    db_save_message(db, sid, nurse_msg)
    db_update_session(db, sid, is_read=False)
    db.commit()

    return chat_bubble(nurse_msg, "nurse")


@rt("/nurse/session/{sid}/close")
@login_required
async def nurse_close(request, sid: str):
    db = request.state.db
    guard = require_role(request, "nurse")
    if guard: return guard

    s = get_session_helper(db, sid)
    if not s: return Response(status_code=404)
    
    close_session(s, db)

    db_save_message(db, sid, Message(role="assistant", content="Session closed by nurse.", timestamp=datetime.now(), phase="system"))
    db.commit()
    s = get_session_helper(db, sid)
    if request.headers.get("HX-Request") == "true":
        return render_chat_view(s, "nurse")
    
    content = Div(
        Card(
            H3("Session Ended"),
            P("Thank you. Your session has been saved."),
            A("Return to Dashboard", href="/nurse", cls="btn btn-primary"),
            cls="p-8 text-center"
        ),
        id="chat-container"
    )
    return layout(request, content, page_title="End Chat - MedAIChat")

serve()

