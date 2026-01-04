from fasthtml.common import *
from monsterui.all import *
from dataclasses import dataclass, field
from starlette.staticfiles import StaticFiles
from uuid import uuid4
from datetime import datetime
from starlette.middleware.sessions import SessionMiddleware
from forms import nurse_form, beneficiary_form, beneficiary_controls, login_card, signup_card
from helpers import hash_password, verify_password, login_required, get_session_or_404, require_role, init_db, get_db




# Initialize DB on startup
init_db()

# -- App setup ---
hdrs = Theme.blue.headers()
hdrs.append(Script(src="https://unpkg.com/htmx.org@1.9.12"))
app = FastHTML(hdrs=hdrs, static_dir="static")
app.add_middleware(SessionMiddleware, secret_key="secret-session-key")
app.mount("/static", StaticFiles(directory="static"), name="static")
rt = app.route

@dataclass
class Message:
    role : str
    content : str
    timestamp :  datetime 
    phase : str

@dataclass
class IntakeAnswer:
    question_id : str
    question : str
    answer : str
    timestamp : datetime

@dataclass
class IntakeState:
    current_index : int = 0
    answers : list[IntakeAnswer] = field(default_factory=list)
    completed : bool = False

@dataclass
class ChatSession:
    session_id : str
    status : str 
    messages: list[Message] = field(default_factory=list)
    intake_complete: bool = False
    urgent : bool = False
    intake : IntakeState = field(default_factory=IntakeState)

sessions : dict[str, ChatSession] = {}

def nurse_case_card(s: ChatSession):
    last_msg = s.messages[-1].content if s.messages else "No messages yet."

    return Div(
        status_badge(s.status),
        Div(f"Session: {s.session_id}", cls="font-mono text-sm"),
        Div(f"Last message: {last_msg[:80]}"),
        A(
            "Open case", href=f"/nurse/{s.session_id}",
            cls = "btn btn-primary btn-sm mt-2"
            ),
        cls="card bg-base-100 shadow p-4"
    )


# Globals
INTAKE_SCHEMA = [
    {"id" : "chief_complaint", "q" : "What is your main issue today?"},
    {"id" : "onest", "q" : "When did is start?"},
    {"id" : "severity", "q" : "How severe is it from 1-10?"},
    {"id" : "location", "q" : "Where is the problem located?"},
    {"id" : "modifiers", "q" : "What makes it better or worse?"},
    {"id" : "fever", "q" : "Have you had a fever?"},
    {"id" : "q", "medications" : "What medications are you currently taking?"},
    {"id" : "conditions", "q" : "Any chronic conditions?"},
    {"id" : "prior_contact", "q" : "Have you contacted us about this before?"}
]

URGENT_KEYWORDS = [
    "chest pain",
    "shortness of breath",
    "can't breathe",
    "severe bleeding",
    "unconscious",
    "stroke",
    "heart attack"
]
STATUS_INTAKE = "INTAKE_IN_PROGRESS"
STATUS_READY = "READY_FOR_REVIEW"
STATUS_URGENT = "URGENT_BYPASS"
STATUS_CLOSED = "CLOSED"
STATUS_VIEWING = "NURSE_VIEWING"


def is_urgent(text: str) -> bool:
    t = text.lower()
    return any(keyword in t for keyword in URGENT_KEYWORDS)

# --- UI helpers ---

def layout(request, content, page_title="MedAiChat"):
    user = request.session.get("user")
    role = request.session.get("role")

    logo = A("MedAIChat", href="/", cls="text-xl font-bold text-white")

    links = []

    if not user:
        links.append(A("Login", href="/login", cls=ButtonT.primary))
        links.append(A("Signup", href="/signup", cls=ButtonT.secondary))
    else:
        links.append(Span(f"Role: {role.capitalize()}", cls="text-white mr-4"))
        links.append(A("Logout", href="/logout", cls=ButtonT.secondary))

    nav = Nav(
        Div(logo),
        Div(*links, cls="flex gap-2"),
        cls="flex justify-between bg-blue-600 px-4 py-2"
    )
    return Html(
        Head(
            *hdrs,
            Title(page_title)
            ),
            Body(
                Div(
                    Header(nav),
                    Div(Container(content, id="content", cls="mt-10"), cls="flex-1"),
                    Footer("© 2025 MedAIChat", cls="bg-blue-600 text-white p-4"),
                    cls="min-h-screen flex flex-col"
                )
            )
    )


def status_badge(status: str):
    color = {
        STATUS_INTAKE : "badge-warning",
        STATUS_READY  : "badge-success",
        STATUS_URGENT : "badge-error",
        STATUS_CLOSED : "badge-neutral"
    }.get(status, "badge-neutral")

    return Div(
        status.replace("_", " "),
        cls=f"badge {color} mb-4"
    )

def chat_bubble(msg: Message):
    align = "chat-start" if msg.role == "beneficiary" else "chat-end"
    color = {
        "beneficiary" : "chat-bubble-neutral",
        "nurse" : "chat-bubble-primary",
        "assistant" : "chat-bubble-info",
    }.get(msg.role, "chat-bubble-neutral")

    phase_tag = ""
    if msg.phase == "post_intake":
        phase_tag = Span("POST-INTAKE", cls="badge badge-outline ml-2")

    return Div(
        Div(msg.role.capitalize(), phase_tag, cls="chat-header"),
        Div(msg.content, cls=f"chat-bubble {color}"),
        cls=f"chat {align}"
    )

def chat_window(messages: list[Message], sid: str):
    return Div(
        *[chat_bubble(m) for m in messages],
        id="chat-window",
        cls="flex flex-col gap-2",
        hx_get=f"/chat/{sid}/poll",
        hx_trigger="every 2s",
        hx_swap="outerHTML"
    )

def beneficiary_chat_fragment(sid: str, s:ChatSession):
    return Div(
        chat_window(s.messages, sid),
        beneficiary_form(sid),
        beneficiary_controls(sid, s.intake_complete),
        id="chat-fragment"
    )

def nurse_chat_fragment(sid: str, s:ChatSession):
    return Div(
        chat_window(s.messages, sid),
        nurse_form(sid),
        id="chat-fragment"
    )

def intake_finished(s: ChatSession):
    return s.intake.current_index >= len(INTAKE_SCHEMA)

def current_intake_question(s: ChatSession) -> str | None:
    if intake_finished(s): return None
    return INTAKE_SCHEMA[s.intake.current_index]["q"]

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
        
        db.execute(
            "INSERT INTO users (email, password_hash, role) VALUES (?, ?, ?)",
            (email, hash_password(password), role)
        )
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
        cur = db.execute(
                "SELECT email, password_hash, role FROM users WHERE email = ?",
                (email,)
        )
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
    s = ChatSession(
        session_id=sid,
        status=STATUS_INTAKE
    )

    first_question = INTAKE_SCHEMA[0]["q"]
    s.messages.append(
        Message(
            role="assistant",
            content=first_question,
            timestamp=datetime.now(),
            phase="intake"
        )
    )

    sessions[sid] = s

    return Redirect(f"/beneficiary/{sid}")

### Chat Route
@rt("/chat/{sid}/poll")
@login_required
def poll_chat(request, sid: str):
    s = get_session_or_404(sessions, sid)
    return chat_window(s.messages, sid)

@rt("/nurse/poll")
@login_required
def nurse_poll(request):
    guard = require_role(request, "nurse")
    if guard: return guard

    ready = [s for s in sessions.values() if s.status in (STATUS_READY, STATUS_URGENT)]

    cases = (
        Div("No cases ready.", cls="alert alert-info")
        if not ready
        else Div(*[nurse_case_card(s) for s in ready], cls="grid gap-4")
    )
    
    content = Div(
        cases,
        id="nurse-cases",
        hx_get="/nurse/poll",
        hx_trigger="every 3s",
        hx_swap="outerHTML"
    )
    return content



### Beneficiary Part

@rt("/beneficiary/{sid}")
@login_required
def beneficiary_view(request, sid: str):
    guard = require_role(request, "beneficiary")
    if guard: return guard

    s = get_session_or_404(sessions, sid)

    # Start intake if empty
    if not s.messages and not s.intake.completed:
        s.messages.append(
            Message(
                role="assistant",
                content=current_intake_question(s),
                timestamp=datetime.now(),
                phase="intake"
            )
        )
    
    typing_indicator = (
        Span(
            "Nurse is reviewing your case...",
            cls="animate-pulse text-sm text-gray-500 mt-2"
        )
        if s.status == STATUS_VIEWING
        else None
    )

    content = Titled(
        "Chat with Care Team", 
        typing_indicator,
        beneficiary_chat_fragment(sid,s)
    )

    return layout(request, content, page_title = "Beneficiary Chat - MedAIChat")


@rt("/beneficiary/{sid}/send")
@login_required
async def beneficiary_send(request, sid: str):
    guard = require_role(request, "beneficiary")
    if guard: return guard

    s = get_session_or_404(sessions, sid)

    form = await request.form()
    message = form.get("message", "").strip()

    if not message:
        return beneficiary_chat_fragment(sid, s)

    s.messages.append(
        Message(
            role="beneficiary", 
            content=message, 
            timestamp=datetime.now(),
            phase = "post_intake" if s.intake_complete else "intake"
        )
    )
    
    if not s.intake.completed:
        q = INTAKE_SCHEMA[s.intake.current_index]
        
        s.intake.answers.append(
            IntakeAnswer(
                question_id=q["id"],
                question=q["q"],
                answer=message,
                timestamp=datetime.now()
            )
        )
        # URGENT BYPASS
        if is_urgent(message):
            s.urgent = True
            s.intake.completed = True
            s.intake_complete = True
            s.status = STATUS_URGENT

            s.messages.append(
                Message(
                    role="assistant",
                    content=(
                        "Your message suggests a potentially  urgent condition. "
                        "A nurse has been notified immediately."
                    ),
                    timestamp=datetime.now(),
                    phase="system"
                )
            )
            return beneficiary_chat_fragment(sid, s)
        
        s.intake.current_index += 1

        if intake_finished(s):
            s.intake.completed = True
            s.intake_complete = True
            s.status = STATUS_READY

            s.messages.append(
                Message(
                    role="assistant",
                    content="Thank you. Your intake is complete. A nurse will review your information shortly. You may add more details if needed.",
                    timestamp=datetime.now(),
                    phase="system"
                )
            )
        
        else:
            s.messages.append(
                role="assistant",
                content=current_intake_question(s),
                timestamp=datetime.now(),
                phase="intake"
            )
        return beneficiary_chat_fragment(sid, s)
    
    return beneficiary_chat_fragment(sid, s)

@rt("/beneficiary/{sid}/complete")
@login_required
def complete_intake(request, sid: str):
    guard = require_role(request, "beneficiary")
    if guard: return guard

    s = get_session_or_404(sessions, sid)
    s.intake_complete = True
    s.status = STATUS_READY 

    return beneficiary_chat_fragment(sid, s)

###  Nurse Part 
@rt("/nurse")
@login_required
def nurse_dashboard(request):
    guard = require_role(request, "nurse")
    if guard: return guard
    
   

    content = Titled(
        "Nurse Dashboard",
        Div(
            id="nurse-cases",
            hx_get="/nurse/poll",
            hx_trigger="load",
            hx_swap="outerHTML"
        )
    )
    
    return layout(request, content, page_title = "Nurse Dashboard - MedAIChat")


@rt("/nurse/{sid}")
@login_required
def nurse_view(request, sid: str):
    guard = require_role(request, "nurse")
    if guard: return guard

    s = get_session_or_404(sessions, sid)
    s.status = STATUS_VIEWING

    content = Titled(
        "Nurse Review",
        status_badge(s.status),
        nurse_chat_fragment(sid, s)
    )
    return layout(request, content, page_title  = "Nurse Review - MedAIChat")


@rt("/nurse/{sid}/send")
@login_required
async def nurse_send(request, sid : str):
    guard = require_role(request, "nurse")
    if guard: return guard

    s = get_session_or_404(sessions, sid)

    form = await request.form()
    message = form.get("message", "").strip()

    if not message:
        return chat_window(s.messages, sid)
    
    s.messages.append(
        Message(
            role="nurse",
            content=message,
            timestamp=datetime.now(),
            phase="post_intake"
        )
    )

    s.status = STATUS_VIEWING 

    return nurse_chat_fragment(sid, s)

serve()