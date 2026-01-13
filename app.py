from fasthtml.common import *
from monsterui.all import *
from starlette.staticfiles import StaticFiles
from uuid import uuid4
from datetime import datetime
from starlette.middleware.sessions import SessionMiddleware
from forms import nurse_form, beneficiary_form, beneficiary_controls, login_card, signup_card, summary_message_fragment, nurse_case_card, urgent_counter, emergency_header
from helpers import hash_password, verify_password, login_required, get_session_or_404, require_role, init_db, get_db, generate_intake_summary
from models import ChatSession, Message, ChatState, IntakeAnswer


# Initialize DB on startup
init_db()


# -- App setup ---
hdrs = Theme.blue.headers()
hdrs.append(Script(src="https://unpkg.com/htmx.org@1.9.12"))
hdrs.append(Script("""
    document.addEventListener("htmx:afterSwap", function (e) {
        // Auto-scroll chat window
        const chat = document.getElementById("chat-window");
        if (chat) {
            chat.scrollTop = chat.scrollHeight;
        }

        // Auto-focus input if present
        const input = document.getElementById("chat-input");
        if (input) {
            input.focus();
        }
    });
    """
))
app = FastHTML(hdrs=hdrs, static_dir="static")
app.add_middleware(SessionMiddleware, secret_key="secret-session-key")
app.mount("/static", StaticFiles(directory="static"), name="static")
rt = app.route



sessions : dict[str, ChatSession] = {}


# Globals
INTAKE_SCHEMA = [
    {"id": "chief_complaint", "q": "What is your main issue today?"},
    {"id": "location", "q": "Where is the problem located?"},
    {"id": "onset", "q": "When did it start?"},
    {"id": "severity", "q": "How severe is it from 1 to 10?"},
    {"id": "relieving_factors", "q": "What makes it better?"},
    {"id": "aggravating_factors", "q": "What makes it worse?"},
    {"id": "fever", "q": "Have you had a fever?"},
    {"id": "medications", "q": "What medications are you currently taking?"},
    {"id": "conditions", "q": "Any chronic conditions?"},
    {"id": "prior_contact", "q": "Have you contacted us about this before?"}
]


URGENT_KEYWORDS = [ ### Temp
    "chest pain",
    "shortness of breath",
    "can't breathe",
    "severe bleeding",
    "unconscious",
    "stroke",
    "heart attack"
]

def is_urgent(text: str) -> bool: ### Temp
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



def chat_bubble(msg: Message, user_role: str):
# If it's a summary and the viewer is not a nurse return nothing
    if msg.phase == "summary":
        if user_role == "nurse":
            return summary_message_fragment(msg.content)
        else: return Span()
  
        
 
    align = {
        "beneficiary": "chat-start",
        "nurse": "chat-end",
        "assistant": "chat-middle",
    }.get(msg.role, "chat-start")

    color = {
        "beneficiary": "chat-bubble-neutral",
        "nurse": "chat-bubble-primary",
        "assistant": "chat-bubble-info",
    }.get(msg.role, "chat-bubble-neutral")

    # System messages are special: centered + italic
    if msg.phase == "system":
        return Div(
            Div(
                msg.content,
                cls="text-center text-sm text-gray-500 italic"
            ),
            cls="my-2"
        )

    return Div(
        Div(msg.role.capitalize(), cls="chat-header"),
        Div(msg.content, cls=f"chat-bubble {color}"),
        cls=f"chat {align}"
    )

    


def chat_window(messages: list[Message], sid: str, user_role: str):
    return Div(
        Div(
            *[chat_bubble(m, user_role) for m in messages],
            id = "chat-messages"
        ),
        id="chat-window",
        cls="flex flex-col gap-2 overflow-y-auto h-[60vh]",
        hx_get=f"/chat/{sid}/poll",
        hx_trigger="every 2s",
        hx_swap="innerHTML",
        hx_target="#chat-messages"
    )

def beneficiary_chat_fragment(sid: str, s:ChatSession, user_role: str):
    return Div(
        chat_window(s.messages, sid, user_role),
        beneficiary_form(sid),
        beneficiary_controls(s),
        id="chat-fragment"
    )

def nurse_chat_fragment(sid: str, s:ChatSession, user_role):
    return Div(
        chat_window(s.messages, sid, user_role),
        nurse_form(sid),
        id="chat-fragment"
    )

def intake_finished(s: ChatSession):
    return s.intake.current_index >= len(INTAKE_SCHEMA)

def current_intake_question(s: ChatSession) -> str | None:
    if intake_finished(s): return None
    return INTAKE_SCHEMA[s.intake.current_index]["q"]

def system_message(s: ChatSession, text: str):
    s.messages.append(
        Message(
            role="assistant",
            content=text,
            timestamp=datetime.now(),
            phase="system"
        )
    )

async def complete_intake(s: ChatSession):
    if s.state != ChatState.INTAKE: return
    
    # Generate the intake summary
    await generate_intake_summary(s)
    
    # Add it as a hidden message in the chat history
    if s.summary:
        s.messages.append(
            Message(
                role="assistant",
                content=s.summary,
                timestamp=datetime.now(),
                phase="summary"
            )
        )

    
    s.state = ChatState.WAITING_FOR_NURSE
    system_message(
        s, 
        "Thank you. Your intake is complete. A nurse will review your case shortly."
    )

def urgent_bypass(s: ChatSession): ### Temp
    s.state = ChatState.URGENT
    system_message(
        s,
        "Your message suggests a potentially urgent condition. A nurse has been notified immediately."
    )

def nurse_joins(s: ChatSession):
    if s.state not in (ChatState.WAITING_FOR_NURSE, ChatState.URGENT):
        return
    
    s.state = ChatState.NURSE_ACTIVE
    system_message(s, "A nurse has joined your case.")

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
        session_id=sid
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
    role = request.session.get("role")
    s = get_session_or_404(sessions, sid)
    return Div(
        *[chat_bubble(m, role) for m in s.messages],
        id="chat-messages"
    )

@rt("/nurse/poll")
@login_required
def nurse_poll(request):
    guard = require_role(request, "nurse")
    if guard: return guard

    priority = {
        ChatState.URGENT : 0,
        ChatState.WAITING_FOR_NURSE : 1,
    }

    ready_sorted = sorted(
        (s for s in sessions.values() if s.state in priority),
        key = lambda s: priority.get(s.state, 99)
    )

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
        Div(
            beneficiary_chat_fragment(sid,s, role),
            cls="container mx-auto p-4"
            ),
            cls="min-h-screen bg-base-100"
        ) 

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
    s.messages.append(
        Message(
            role="beneficiary", 
            content=message, 
            timestamp=datetime.now(),
            phase = "intake" if s.state == ChatState.INTAKE else "chat"
        )
    )
    
    if s.state == ChatState.INTAKE:
        if is_message_urgent:
            urgent_bypass(s)
        else:
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
                urgent_bypass(s)
            
            else: 
                s.intake.current_index += 1

                if intake_finished(s):
                    s.intake.completed = True
                    await complete_intake(s)
                
                else:
                    s.messages.append(
                        Message(
                            role="assistant",
                            content=current_intake_question(s),
                            timestamp=datetime.now(),
                            phase="intake"
                        )
                        
                    )
   
    return Div(
        *[chat_bubble(m, role) for m in s.messages], 
        id = "chat-messages"
        )


@rt("/beneficiary/{sid}/emergency")
@login_required
def beneficiary_emergency(request, sid: str):
    guard = require_role(request, "beneficiary")
    if guard: return guard
    role = request.session.get("role")
    s = get_session_or_404(sessions, sid)

    urgent_bypass(s)

    chat = Div(*[chat_bubble(m, role) for m in s.messages], id="chat-messages")
    header = emergency_header(s)
    header.attrs["hx_swap_oob"] = "true"
    controls = beneficiary_controls(s)
    controls.attrs["hx_swap_oob"] = "true"

    return chat, header, controls


###  Nurse Part 
@rt("/nurse")
@login_required
def nurse_dashboard(request):
    guard = require_role(request, "nurse")
    if guard: return guard

    content = Titled(
        "Nurse Dashboard",
        Div("Urgent: 0", id="urgent-count", cls="badge badge-ghost"),
        Div(
            id="nurse-cases",
            hx_get="/nurse/poll",
            hx_trigger="load, every 3s",
            hx_swap="innerHTML"
        )
    )
    
    return layout(request, content, page_title = "Nurse Dashboard - MedAIChat")


@rt("/nurse/{sid}")
@login_required
def nurse_view(request, sid: str):
    guard = require_role(request, "nurse")
    if guard: return guard
    role = request.session.get("role")
    s = get_session_or_404(sessions, sid)
    
    
    nurse_joins(s)
    
    content = Titled(
        "Nurse Review",
        nurse_chat_fragment(sid, s, role)
    )
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
        return Div(
            *[chat_bubble(m, role) for m in s.messages],
            id="chat-messages"
        )
    
    s.messages.append(
        Message(
            role="nurse",
            content=message,
            timestamp=datetime.now(),
            phase="chat"
        )
    )

    nurse_joins(s)

    return Div(
        *[chat_bubble(m, role) for m in s.messages],
        id="chat-messages"
    )

serve()