from fasthtml.common import *
from monsterui.all import *
from dataclasses import dataclass, field
from starlette.staticfiles import StaticFiles
from uuid import uuid4
from datetime import datetime
from starlette.middleware.sessions import SessionMiddleware
from forms import nurse_form, beneficiary_form, beneficiary_controls
from helpers import hash_password, verify_password, login_required 
from forms import login_card, signup_card

import sqlite3


# --- DB setup ---
DB_PATH = "users.db"
def get_db():
    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)
        """
    )
    db.commit()
    db.close()

# Initialize DB on startup
init_db()


# -- App setup ---
hdrs = Theme.blue.headers()
app = FastHTML(hdrs=hdrs, static_dir="static")
app.add_middleware(SessionMiddleware, secret_key="secret-session-key")
app.mount("/static", StaticFiles(directory="static"), name="static")
rt = app.route
db = get_db()

@dataclass
class Message:
    role : str
    content : str
    timestamp :  datetime 
    phase : str # intake | post_intake

@dataclass
class ChatSession:
    session_id : str
    status : str # NEW | INTAKE
    messages: list[Message] = field(default_factory=list)
    intake_complete: bool = False
    urgent : bool = False

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



URGENT_KEYWORDS = [
    "chest pain",
    "shortness of breath",
    "can't breathe",
    "severe bleeding",
    "unconscious",
    "stroke",
    "heart attack"
]

def is_urgent(text: str) -> bool:
    t = text.lower()
    return any(keyword in t for keyword in URGENT_KEYWORDS)

# --- UI helpers ---

def layout(request, content):
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

    return Div(
        Header(nav),
        Div(Container(content, id="content", cls="mt-10"), cls="flex-1"),
        Footer("© 2025 MedAIChat", cls="bg-blue-600 text-white p-4"),
        cls="min-h-screen flex flex-col"
    )

def status_badge(status: str):
    color = {
        "INTAKE_IN_PROGRESS" : "badge-warning",
        "READY_FOR_REVIEW" : "badge-success",
        "URGENT_BYPASS" : "badge-error",
        "CLOSED" : "badge-neutral"
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

def chat_window(messages: list[Message]):
    return Div(
        *[chat_bubble(m) for m in messages],
        id="chat-window",
        cls="flex flex-col gap-2"
    )



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
    if request.method == "GET":
        return layout(request, signup_card())
    elif request.method == "POST":
        form = await request.form()

        email = form.get("email", "").strip().lower()
        password = form.get("password", "")
        repeat = form.get("repeat_password", "")
        role = form.get("role", "")

        if not email or not password or not role:
            return layout(request , signup_card("All fields are required.", email))
        
        if password != repeat:
            return layout(request, signup_card("Password do not match.", email))
        
        db = get_db()
        cur = db.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cur.fetchone():
            db.close()
            return layout(request, signup_card("User already exists.", email))
        
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
    if request.method == "GET":
        return layout(request, login_card())
    elif request.method == "POST":
        form = await request.form()
        email = form.get("email", "").strip().lower()
        password = form.get("password", "").strip()

        if not email or not password:
            return layout(request, login_card("All fields are required.", email))
        
        db = get_db()
        cur = db.execute(
                "SELECT email, password_hash, role FROM users WHERE email = ?",
                (email,)
        )
        user = cur.fetchone()
        db.close()

        if not user or not verify_password(password, user["password_hash"]):
            return layout(request, login_card("Invalid credentials.", email))
        
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
    sessions[sid] = ChatSession(
        session_id=sid,
        status="INTAKE_IN_PROGRESS"
    )
    return Redirect(f"/beneficiary/{sid}")


### Beneficiary Part

@rt("/beneficiary/{sid}")
@login_required
def beneficiary_view(request, sid: str):
    s = sessions[sid]

    content = Titled(
        "Chat with Care Team", 
        status_badge(s.status),
        chat_window(s.messages),
        beneficiary_form(sid, s.intake_complete),
        beneficiary_controls(sid, s.intake_complete)
    )
    return layout(request, content)


@rt("/beneficiary/{sid}/send")
@login_required
def beneficiary_send(request, sid: str, message: str):
    s = sessions[sid]

    phase = "post_intake" if s.intake_complete else "intake"

    s.messages.append(Message(role="beneficiary", content=message, timestamp=datetime.now(), phase=phase))
    
    # URGENT BYPASS
    if is_urgent(message) and s.status != "URGENT_BYPASS":
        s.urgent = True
        s.intake_complete = True
        s.status = "URGENT_BYPASS"

        s.messages.append(
            Message(
                role="assistant",
                content=(
                    "Your message suggests an urgent concern. "
                    "A nurse has been notified immediately."
                ),
                timestamp=datetime.now(),
                phase="system"
            )
        )
    return chat_window(s.messages)

@rt("/beneficiary/{sid}/complete")
@login_required
def complete_intake(request, sid: str):
    s = sessions[sid]
    s.intake_complete = True
    s.status = "READY_FOR_REVIEW" 
    return Redirect(f"/beneficiary/{sid}")

###  Nurse Part 
@rt("/nurse")
@login_required
def nurse_dashboard(request):
    ready = [
        s for s in sessions.values() if s.status in ("READY_FOR_REVIEW", "URGENT_BYPASS")
    ]
    
    if not ready:
        content =  Titled(
                "Nurse Dashboard",
                Div("No cases ready for review.", cls="alert alert-info")
            )
    else:
        content = Titled(
            "Nurse Dashboard",
            Div(
                *[nurse_case_card(s) for s in ready],
                cls="grid gap-4"
            )
        )
    return layout(request, content)


@rt("/nurse/{sid}")
@login_required
def nurse_view(request, sid: str):
    s = sessions[sid]

    if s.status not in ("READY_FOR_REVIEW", "URGENT_BYPASS"):
        content =  Titled(
            "Nurse View",
            Div("Case still in intake.", cls="alert alert-warning")
        )
    
    else:
        content = Titled(
            "Nurse Review",
            status_badge(s.status),
            chat_window(s.messages),
            nurse_form(sid)
        )
    return layout(request, content)


@rt("/nurse/{sid}/send")
@login_required
def nurse_send(request, sid : str, message: str):
    s = sessions[sid]

    s.messages.append(
        Message(
            role="nurse",
            content=message,
            timestamp=datetime.now(),
            phase="post_intake"
        )
    )

    s.status = "CLOSED"

    return chat_window(s.messages)

serve()