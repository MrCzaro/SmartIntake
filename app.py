from fasthtml.common import *
from dataclasses import dataclass, field
from uuid import uuid4
from datetime import datetime

app = FastHTML()
rt = app.route

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

sessions = {}

# --- UI helpers ---
def chat_bubble(msg: Message):
    align = "chat-start" if msg.role == "beneficiary" else "chat-end"
    color = "chat-bubble-neutral" if msg.role == "beneficiary" else "chat-bubble-primary"

    phase_tag = ""
    if msg.phase == "post_intake":
        phase_tag = Span("POST-INTAKE", cls="badge badge-outline ml-2")

    return Div(
        Div(msg.role.capitalize(), phase_tag, cls="chat-header"),
        Div(msg.content, cls=f"chat-bubble {color}"),
        cls=f"chat {align}"
    )


    return Div(
        Div(msg.role.capitalize(), cls="chat-header"),
        Div(msg.content, cls=f"chat-bubble {color}"),
        cls=f"chat {align}"
    )

def chat_window(messages):
    return Div(
        *[chat_bubble(m) for m in messages],
        id="chat-window",
        cls="flex flex-col gap-2"
    )


def status_badge(status):
    color = {
        "READY_FOR_REVIEW" : "badge-success",
        "URGENT_BYPASS" : "badge-error",
        "INTAKE_IN_PROGRESS" : "badge-warning"
    }.get(status, "badge-neutral")

    return Div(
        status.replace("_", " "),
        cls=f"badge {color} mb-4"
    )

def render_beneficiary_chat(messages):
    return Div(
        *[chat_bubble(m) for m in messages if m.role != "assistant"],
        cls="flex flex-col gap-2"
    )

def render_nurse_chat(messages):
    return Div(
        *[chat_bubble(m) for m in messages],
        cls="flex flex-col gap-2"
    )
# --- Routes ---

@rt("/")
def index():
    session_id = str(uuid4())
    sessions[session_id] = []

    return Titled(
        "Nurse-Beneficiary Chat",
        Form(
            Input(type="hidden", name="session_id", value=session_id),
            Select(
                Option("Beneficiary", value="beneficiary"),
                Option("Nurse", value="nurse"),
                name="role",
                cls="select select-bordered w-full max-w-xs"
            ),
            Input(
                name="message",
                placeholder="Type your message...",
                cls="input input-bordered w-full"
            ),
            Button("Send", cls="btn btn-primary"),
            hx_post="/send",
            hx_target="#chat-area",
            hx_swap="outerHTML"
        ),
        Div(id="chat-area", cls="mt-6")
    )
# Start Session
@rt("/start")
def start():
    sid = str(uuid4())
    sessions[sid] = ChatSession(
        session_id=sid,
        status="INTAKE_IN_PROGRESS"
    )
    return Redirect(f"/beneficiary/{sid}")

# Beneficiary View
@rt("/beneficiary/{sid}")
def beneficiary_view(sid: str):
    s = sessions[sid]

    return Titled(
        "Chat with Care Team", 
        status_badge(s.status),
        chat_window(s.messages),
        beneficiary_form(sid, s.intake_complete)
    )

# Beneficiary send
@rt("/beneficiary/{sid}/send")
def beneficiary_send(sid: str, message: str):
    s = sessions[sid]

    phase = "post_intake" if s.intake_complete else "intake"

    s.messages.append(Message(role="beneficiary", content=message, timestamp=datetime.now(), phase=phase))
    
    # URGENT BYPASS
    if is_urgent(message) and s.status != "URGENT_BYPASS":
        s.urgent = True
        s.status = "URGENT_BYPASS"
        s.intake_complete = True

        s.message.append(
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

# Beneficiary - intake completion 
@rt("beneficiary/{sid}/complete")
def complete_intake(sid: str):
    s = sessions[sid]
    s.intake_complete = True
    s.status = "READY_FOR_REVIEW",
    return Redirect(f"/beneficiary/{sid}")

# Nurse View
@rt("/nurse/{sid}")
def nurse_view(sid: str):
    s = sessions[sid]

    if s.status not in ("READY_FOR_REVIEW", "URGENT_BYPASS"):
        return Titled(
            "Nurse View",
            Div("Case still in intake.", cls="alert alert-warning")
        )
    
    return Titled(
        "Nurse Review",
        status_badge(s.status),
        chat_window(s.messages),
        nurse_form(sid)
    )


@rt("/send")
def send(session_id : str, role : str, message: str):
    sessions[session_id].append(Message(role=role, content=message))
    return Div(
        chat_window(sessions[session_id]),
        id="chat-area"
    )



serve()