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
    timestamp :  datetime = datetime.now()
    phase : str # intake | post_intake

@dataclass
class ChatSession:
    session_id : str
    status : str # NEW | INTAKE
    messages: list[Message]
    intake_complete: bool = False
    urgent : bool = False

chat_sessions = {}

# --- UI helpers ---
def chat_bubble(msg: Message):
    align = "chat-start" if msg.role == "beneficiary" else "chat-end"
    color = "chat-bubble-neutral" if msg.role == "beneficiary" else "chat-bubble-primary"

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
    chat_sessions[session_id] = []

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

@rt("/send")
def send(session_id : str, role : str, message: str):
    chat_sessions[session_id].append(Message(role=role, content=message))
    return Div(
        chat_window(chat_sessions[session_id]),
        id="chat-area"
    )

serve()