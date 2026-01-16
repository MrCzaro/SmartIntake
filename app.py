from fasthtml.common import *
from monsterui.all import *
from starlette.staticfiles import StaticFiles
from uuid import uuid4
from datetime import datetime
from starlette.middleware.sessions import SessionMiddleware
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
def start(request):
    sid = str(uuid4())
    s = ChatSession(session_id=sid)

    first_question = INTAKE_SCHEMA[0]["q"]
    s.messages.append(Message( role="assistant", content=first_question, timestamp=datetime.now(), phase="intake"))
    sessions[sid] = s

    return Redirect(f"/beneficiary/{sid}")

### Chat Route
@rt("/chat/{sid}/poll")
@login_required
def poll_chat(request, sid: str):
    role = request.session.get("role")
    s = get_session_or_404(sessions, sid)
    return Div(*[chat_bubble(m, role) for m in s.messages],id="chat-messages")

@rt("/nurse/poll")
@login_required
def nurse_poll(request):
    guard = require_role(request, "nurse")
    if guard: return guard

    priority = {
        ChatState.URGENT : 0,
        ChatState.WAITING_FOR_NURSE : 1,
    }

    ready_sorted = sorted((s for s in sessions.values() if s.state in priority),key = lambda s: priority.get(s.state, 99))

    if not ready_sorted:
        case = Div("No cases ready.", cls="alert alert-info")
    else:
        case = Div(*[nurse_case_card(s) for s in ready_sorted], cls="grid gap-4")

    urgent_count = len([s for s in ready_sorted if s.state == ChatState.URGENT])
    counter = urgent_counter(urgent_count)

    return case, counter



### Beneficiary Part

@rt("/beneficiary/{sid}")
@login_required
def beneficiary_view(request, sid: str):
    guard = require_role(request, "beneficiary")
    if guard: return guard
    role = request.session.get("role")
    s = get_session_or_404(sessions, sid)



    content = Div(
        emergency_header(s),
        Div(beneficiary_chat_fragment(sid,s, role), cls="container mx-auto p-4"),cls="min-h-screen bg-base-100") 

    return layout(request, content, page_title = "Beneficiary Chat - MedAIChat")


@rt("/beneficiary/{sid}/send")
@login_required
async def beneficiary_send(request, sid: str):
    guard = require_role(request, "beneficiary")
    if guard: return guard
    role = request.session.get("role")
    s = get_session_or_404(sessions, sid)

    form = await request.form()
    message = form.get("message", "").strip()

    red_flags = ["chest pain", "shortness of breath", "can't breathe", "severe bleeding", "unconscious", "stroke", "heart attack"]
    
    if not message:
        return Div(
            *[chat_bubble(m, role) for m in s.messages],
            id="chat-messages"
        )

    is_message_urgent = any(flag in message.lower() for flag in red_flags)
    s.messages.append(Message(role="beneficiary", content=message, timestamp=datetime.now(), phase = "intake" if s.state == ChatState.INTAKE else "chat"))
    
    if s.state == ChatState.INTAKE:
        if is_message_urgent:
            urgent_bypass(s)
        else:
            q = INTAKE_SCHEMA[s.intake.current_index]
            s.intake.answers.append(
                IntakeAnswer(question_id=q["id"], question=q["q"], answer=message, timestamp=datetime.now()))
            s.intake.current_index += 1
            if intake_finished(s):
                s.intake.completed = True
                await complete_intake(s)
            else:
                s.messages.append(Message(role="assistant", content=current_intake_question(s), timestamp=datetime.now(), phase="intake"))
    chat = Div(*[chat_bubble(m, role) for m in s.messages], id = "chat-messages")
    ui_bundle = get_beneficiary_ui_updates(sid, s)
    return chat, *ui_bundle


@rt("/beneficiary/{sid}/emergency")
@login_required
def beneficiary_emergency(request, sid: str):
    guard = require_role(request, "beneficiary")
    if guard: return guard
    s = get_session_or_404(sessions, sid)
    manual_emergency_escalation(s)
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
def nurse_view(request, sid: str):
    guard = require_role(request, "nurse")
    if guard: return guard
    role = request.session.get("role")
    s = get_session_or_404(sessions, sid)
    nurse_joins(s)
    content = Titled("Nurse Review",nurse_chat_fragment(sid, s, role))
    return layout(request, content, page_title  = "Nurse Review - MedAIChat")


@rt("/nurse/{sid}/send")
@login_required
async def nurse_send(request, sid : str):
    guard = require_role(request, "nurse")
    if guard: return guard
    role = request.session.get("role")

    s = get_session_or_404(sessions, sid)

    form = await request.form()
    message = form.get("message", "").strip()

    if not message:
        return Div(*[chat_bubble(m, role) for m in s.messages], id="chat-messages")
    
    s.messages.append(Message(role="nurse", content=message, timestamp=datetime.now(), phase="chat"))
    nurse_joins(s)
    return Div(*[chat_bubble(m, role) for m in s.messages],id="chat-messages")

serve()