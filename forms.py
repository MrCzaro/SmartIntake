from fasthtml.common import *
from monsterui.all import *
from typing import Any
from models import ChatSession, ChatState


def urgent_counter(count: int):
    # The ID must match where we want to swap it
    badge_cls = "badge-error" if count > 0 else "badge-ghost"
    return Div(
        f"Urgent Cases: {count}",
        id="urgent-count",
        cls=f"badge {badge_cls} p-4 font-bold",
        # This is the magic attribute for the poll response
        hx_swap_oob="true" if count is not None else "false"
    )

def nurse_case_card(s: ChatSession):
    last_msg = s.messages[-1].content if s.messages else "No messages yet."


    # Determine if the casae is urgent
    is_urgent = s.state == ChatState.URGENT

    # Conditional styling
    urgent_styles = "bg-error/10 border-l-8 border-error shadow-lg" if is_urgent else "bg-base-100"
    return Div(
        # Header with Urgent Badge
        DivLAligned(
            Div(f"Session: {s.session_id[:8]}", cls="font-mono text-sm font-bold"),
            Badge("URGENT", cls="badge-error ml-2") if is_urgent else Span()
        ),
        Div(f"Last message: {last_msg[:80]}...", cls="text-sm mt-1"),
        A(
            "Open case", href=f"/nurse/{s.session_id}",
            cls="btn btn-primary btn-sm mt-2 w-full"
        ),
        cls=f"card {urgent_styles} shadow p-4 transition-all duration-300"
    )

def summary_message_fragment(content : str):
    return Card(
        DivLAligned(
            UkIcon("clipboard-list", cls="mr-2 text-primary"),
            H4("Intake Summary", cls=TextPresets.bold_sm)
        ),
        P(content, cls=TextPresets.muted_sm),
        cls=(CardT.secondary, "my-4 border-l-4 border-primary")
    )

def emergency_header(s: ChatSession):
    is_urgent = s.state == ChatState.URGENT

    status_content = Span("🆘 NURSE NOTIFIED - Responding Shortly", cls="font-bold animate-pulse") if is_urgent else \
                    Button("EMERGENCY: NEED A NURSE", 
                           hx_post=f"/beneficiary/{s.session_id}/emergency", 
                           hx_confirm="Are you sure you need to escalate to emergency care?",
                           cls="btn btn-error btn-sm lg:btn-md")
    header_cls = "navbar bg-error/20 border-b-4 border-error" if is_urgent else "navbar bg-base-100 border-b-2 border-base-300"

    return Div(
        H3("MedAIChat", cls="text-xl font-bold"),
        status_content,
        id = "chat-header",
        cls=f"{header_cls} mb-4 flex justify-between px-4 sticky top-0 z-50" 
    )
       
def beneficiary_form(sid: str) -> Any:
    """
    Render the beneficiary message input form.
    
    Sends a chat message to the backend using HTMX and updates
    the chat window with the server-rendered response.
    
    
    Args:
        sid (str): Chat session ID.
    
    Returns:
        Any: FastHTML Form component.
    """

    return Form( 
        Input(type="hidden", name="sid", value=sid),
        Input(
            name="message",
            id="chat-input",
            placeholder="Type your message...",
            cls="input input-bordered w-full"
        ),
        Button("Send", cls="btn btn-primary mt-2", type="submit", hx_disable_elt="this"),
        hx_post=f"/beneficiary/{sid}/send",
        hx_target="#chat-messages",
        hx_swap="innerHTML",
        hx_on="htmx:afterRequest: this.reset()",
        method="post"
    )


def beneficiary_controls(s: ChatSession) -> Any:
    """
    Render control/status information for the beneficiary
    based on the current chat session state.

    States:
    - INTAKE: Intake still in progress
    - WAITING_FOR_NURSE: Intake completed, awaiting nurse review
    - NURSE_ACTIVE / URGENT: Nurse is engaged, free chat enabled

    Args:
        s (ChatSession): The current chat session instance.

    Returns:
        Any: A FastHTML component representing the appropriate UI message.
    """

    if s.state == ChatState.INTAKE:
        return Div(
            "Please answer all intake questions to continue.",
            cls="alert alert-warning mt-4"
        )
    
    if s.state == ChatState.WAITING_FOR_NURSE:
        return Div(
            "Your intake is complete. Waiting for a nurse...",
            cls="alert alert-info mt-4"
        )
    
    if s.state in (ChatState.NURSE_ACTIVE, ChatState.URGENT):
        return Div(
            "You may continue chatting with the nurse.",
            cls = "alert alert-success mt-4"
        )
    
    return Div()
    


def nurse_form(sid: str) -> Any:
    """
    Render the nurse reply form for an active chat session.
    
    Sends a nurse response and updates the chat window using HTMX.
    
    Args:
        sid (str): Chat session ID.
        
    Returns:
        Any: FastHTML Form component.
    """
    return Form(
        Input(type="hidden", name="sid", value=sid),
        Input(name="message", id="chat-input", placeholder="Reply to beneficiary...", cls="input input-bordered w-full"),
        Button("Send", cls="btn btn-primary mt-2", type="submit", hx_disable_elt="this"),
        hx_post=f"/nurse/{sid}/send",
        hx_target="#chat-messages",
        hx_swap="innerHTML",
        hx_on="htmx:afterRequest: this.reset()",
        method="post"
    )

def chat_input_group(sid: str) -> Any:
    return Form(
        Div(
        # Urgent Button 
            Button("🆘", hx_post=f"/beneficiary/{sid}/emergency", cls="btn btn-error btn-square", title="Emergency Escalation"),
            Input(name="message", placeholder="Type your message...", cls="input input-bordered flex-grow"),
            Button("Send", cls="btn btn-primary"),
            cls="flex gap-2 p-4 bg-base-200 border-t"
        ),
        hx_post=f"/beneficiary/{sid}/send",
        hx_target="#chat-messages",
        hx_swap="innerHTML"
    )

def login_card(error_message: str | None = None, prefill_email: str = "") -> Any:
    """
    Render the login form card.

    Args: 
        error_message (str | None): Optional error message to display.
        prefill_email (str) : Optional email to prefill the form.

    
    Returns:
        Any: FastHTML Card component.
    """
    return Card(
        CardHeader(H3("Login")),
        CardBody(
            *([P(error_message, cls="bg-red-600 font-semibold")] if error_message else []),
            Form(
                LabelInput(
                    "Email",
                    name="email", 
                    value=prefill_email,
                    placeholder="user@example.com",
                ),
                LabelInput(
                    "Password",
                    name="password",
                    type="password",
                    placeholder="Enter your password"
                ),
                Div(
                    Button(
                        "Login",
                        cls=ButtonT.primary + " rounded-lg py-2 px-4 md:py-3 md:px-5 text-sm md:text-base",
                        type="submit"
                        ),
                        cls="mt-4"
                ),
                action="/login",
                method="post"
            )
        ),
        CardFooter("Do not have an account? ", A(B("Sign up"), href="/signup"))
    )


def signup_card(error_message: str | None = None, prefill_email: str = "") -> Any:
    """
    Render the signup form card.

    Allows users to register and select their role.

    Args:
        error_message (str | None): Optional error message to dispaly.
        prefill_email (str) : Email value to prefill the form input.

    Returns: 
        Any: FastHTML Card component.
    """
    
    return Card(
        CardHeader(H3("Create Account")),
        CardBody(
            *([P(error_message, cls="text-red-600 font-semibold")] if error_message else []),
            Form(
                LabelInput(
                    "Email",
                    name="email",
                    value=prefill_email,
                    placeholder="user@example.com"
                ),
                LabelInput(
                    "Password",
                    name="password",
                    type="password",
                    placeholder="Choose a password"
                ),
                LabelInput(
                    "Repeat Password",
                    name="repeat_password",
                    type="password",
                    placeholder="Repeat password"
                ),
                Div(
                    Label("Role"),
                    Select(
                        Option("Beneficiary", value="beneficiary"),
                        Option("Nurse", value="nurse"),
                        name="role",
                        cls="select select-bordered w-full"
                    ),
                    cls="mt-2"
                ),
                Div(
                    Button("Sign Up", cls=ButtonT.primary + " rounded-lg py-2 px-4 md:py-3 md:px-5 text-sm md:text-base"),
                ),
                action="/signup",
                method="post"
            )
        ),
        CardFooter(
            "Already have an account? ",
            A(B("Login"), href="/login")
        )
    )

