from fasthtml.common import *
from monsterui.all import *
from typing import Any
from models import *

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

def layout(request, content, page_title="MedAiChat"):
    """
    Provides the standard HTML wrapper for all pages in the application.
    
    This function generates the global navigation bar, a consistent footer
    and the main content container. It dynamically adjusts the navigation 
    links based on the user's session state (logged in/out and user role).
    
    Args:
        request: The FastHTML request object, used to check session data.
        content: The specific page content to render within the layout.
        page_title (str): The title to be displayed in the browser tab.
        
    Returns:
        Html: A complete FastHTML Html component including Head and Body tags.
    """
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

    nav = Nav(Div(logo), Div(*links, cls="flex gap-2"), cls="flex justify-between bg-blue-600 px-4 py-2")
    return Html(
        Head(*hdrs,Title(page_title)),
        Body(Div(Header(nav), Div(Container(content, id="content", cls="mt-10"), cls="flex-1"),
                    Footer("© 2025 MedAIChat", cls="bg-blue-600 text-white p-4"), cls="min-h-screen flex flex-col")))

def urgent_counter(count: int):
    """
    Renders a status badge showing the number of active urgent cases.
    
    This component is designed to be updated via HTMX Out-of-Band (OOB) swaps.
    It changes its visual style (color) based on whether any urgent cases are currently pending.
    
    Args:
        count (int) : The current number of urgent chat sessions.
        
    Returns: 
        Div: A FastHTML Div component with HTMX OOB swapping enabled.
    """

    badge_cls = "badge-error" if count > 0 else "badge-ghost"
    return Div( f"Urgent Cases: {count}", id="urgent-count", cls=f"badge {badge_cls} p-4 font-bold", hx_swap_oob="true" if count is not None else "false")



def chat_bubble(msg: Message, user_role: str):
    """
    Renders an individual message bubble within the chat interface.
    
    This component dynamically handles three distinc message types:
        1. Summaries: Only visible to users with the 'nurse' role.
        2. System Messages: Centered, gray, and italicized for status updates.
        3. Chat Messages: Aligned and colored based on the sender's role.
        
    Args:
        msg (Message): The message object containing content, role, and phase.
        user_role (str): The role of the current viewer, used for premission checks.
    
    Returns: 
        Union[Div, Span]: A styled message component or an empty Span if unauthorized."""
    
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

    if msg.phase == "system":
        return Div(Div(msg.content, cls="text-center text-sm text-gray-500 italic"),cls="my-2")

    return Div(Div(msg.role.capitalize(), cls="chat-header"),Div(msg.content, cls=f"chat-bubble {color}"), cls=f"chat {align}")

def chat_window(messages: list[Message], sid: str, user_role: str):
    """
    Creates a scrollable container for the entire message history.
    
    This component includes built-in HTMX pooling logic, causing it to automatically
    refresh its content from the sever every 2 seconds.
    It manages the mapping of message objects to their respective bubble components.
    
    Args:
        messages (list[Message]): The list of messages to be displayed.
        sid (str): The unique session ID for the polling endpoint.
        user_role (str): The role of the current viewer to pass to chat_bubble.
        
    Returns:
        Div: An auto-pooling container with a fixed height and scrollable overflow.
    """
    return Div(Div(*[chat_bubble(m, user_role) for m in messages], id="chat-messages"),
        id="chat-window",
        cls="flex flex-col gap-2 overflow-y-auto h-[60vh]",
        hx_get=f"/chat/{sid}/poll",
        hx_trigger="every 3s",
        hx_swap="innerHTML",
        hx_target="#chat-messages"
    )

def close_chat_button(sid: str, role: str) -> Any:
    """
    A consistent 'End Chat' button for both roles.
    """
    endpoint = ""
    target = ""
    if role == "beneficiary":
        endpoint = f"/{role}/{sid}/close"
        target = "#beneficiary-input-form"
    if role == "nurse":
        endpoint = f"/nurse/session/{sid}/close"
        target = "#nurse-input-form"
    return Button(
        "✖",
        type="button",
        cls = "btn btn-warning btn-square",
        hx_post=endpoint,
        hx_target=target, 
        hx_swap="outerHTML",
        hx_confirm = "Are you sure you want to end this session?"
    )


def render_chat_view(s: ChatSession, role:str):
    """
    Main chat view renderer that handles all session states.
    Includes resume notices, inactive banners, and completion modals.
    
    Args:
        s: ChatSession object
        role: User role ("beneficiary" or "nurse")
        
    Returns:
        Complete chat interface
    """
    window = chat_window(s.messages, s.session_id, role)
    header = Div()
    form = Div()
    controls = Div()
    notices = []
    
    # Show resume notice if session was just reactivated
    if s.messages and s.messages[-1].phase == "system" and "resumed" in s.messages[-1].content.lower():
        notices.append(session_resume_notice(s.session_id))

    # Show inactive banner if currently inactive
    if s.state == ChatState.INACTIVE:
        notices.append(inactive_session_banner(s))


    if role == "beneficiary":
        header = emergency_header(s)
        form = beneficiary_form(s.session_id, s)
        controls = beneficiary_controls(s)
    
    if role == "nurse":
        form = nurse_form(s.session_id, s)
        if s.state == ChatState.URGENT:
            notices.append(completion_modal(s.session_id))

    return Div(
        header,
        Div(*notices, window, form, controls, cls="container mx-auto p-4"),
        id="chat-root", 
        cls="min-h-screen bg-base-100"
        )

def summary_message_fragment(content : str):
    """
    Renders a specialized UI card for displaying an AI-generated intake summary.
    
    This component uses a clipboard icon and distinct styling to separate the medical summary
    from standard chat bubbles, making it easier for nurses to identify key information.
    
    Args:
        content (str): The markdown or plain text content of the summary.
    
    Returns:
        Card: A styled MonsterUI Card component with a primary accent border.
    """
    return Card(DivLAligned(UkIcon("clipboard-list", cls="mr-2 text-primary"), H4("Intake Summary", cls=TextPresets.bold_sm)),
        P(content, cls=TextPresets.muted_sm), cls=(CardT.secondary, "my-4 border-l-4 border-primary"))

def emergency_header(s: ChatSession):
    """
    Generates the sticky top navigation bar for the beneficiary chat interface.
    
    The header dynamically switches between two states:
        1. Normal: Displays the 'EMERGENCY' button to allow manual escalation.
        2. Urgent: Displays a pulsing notification indicating a nurse is on the way.
        
    Args:
        s (ChatSession): The current session data used to determine urgency status.
        
    Returns: 
        Div: A navbar component with a unique ID for HTMX Out-of-Band (OOB) updates.
    """
    if s.state == ChatState.CLOSED:
        return Div(id="chat-header", hx_swap_oob="true") 
    is_urgent = s.state == ChatState.URGENT

    status_content = Span("🆘 NURSE NOTIFIED - Responding Shortly", cls="font-bold animate-pulse") if is_urgent else \
                    Button("EMERGENCY: NEED A NURSE", 
                           hx_post=f"/beneficiary/{s.session_id}/emergency", 
                           hx_target="#chat-header",
                           hx_confirm="Are you sure you need to escalate to emergency care?",
                           hx_on__htmx_config_request="this.setAttribute('disabled', 'disabled')",
                           cls="btn btn-error btn-sm lg:btn-md")
    header_cls = "navbar bg-error/20 border-b-4 border-error" if is_urgent else "navbar bg-base-100 border-b-2 border-base-300"

    return Div(H3("MedAIChat", cls="text-xl font-bold"), status_content,id = "chat-header",
               hx_swap_oob="true", cls=f"{header_cls} mb-4 flex justify-between px-4 sticky top-0 z-50")


       
def beneficiary_form(sid: str, s: ChatSession) -> Any:
    """
    Render the beneficiary message input form.
    
    Sends a chat message to the backend using HTMX and appends
    the server-rendered bubble(s) into the chat window.
    
    Args:
        sid (str): Chat session ID.
        s (ChatSession) : Current session object
    
    Returns:
        Any: FastHTML Form component.
    """
    if s.state == ChatState.CLOSED:
        return Div(
            Div(
                Span("🛑 This session is closed.", cls="alert alert-info w-full text-center"),
                Div(A("Back to Dashboard", href="/beneficiary", cls="btn btn-primary mt-4")),
                id="beneficiary-input-form",
                hx_swap_oob="true",
                cls="p-4"
        ),
        Div("", id="beneficiary-controls", hx_swap_oob="true")
        )
    
    if s.state == ChatState.COMPLETED:
        return Div(
            Div(Span("✅ This case has been completed by a nurse.", cls="alert alert-success w-full text-center")),
            Div(
                A("View Full History", href=f"/beneficiary/{sid}/history", cls="btn btn-ghost mt-4"),
                A("Start New Consultation", href="/start", cls="btn btn-primary mt-4 ml-2")
            ),
            cls="p-4"
        )
    
    is_escalated = s.state in (ChatState.URGENT, ChatState.NURSE_ACTIVE)
    is_inactive = s.state == ChatState.INACTIVE
    if is_escalated:
        sos_btn = Span("✅ Notified", cls="btn btn-ghost no-animation text-success btn-square")
    else:                                        
        sos_btn = Button("🆘", hx_post=f"/beneficiary/{sid}/emergency", hx_target="#chat-header", hx_swap="outerHTML", hx_confirm="Escalate to a nurse?",
                hx_on__htmx_config_request="this.setAttribute('disabled', 'disabled')", type="button",  cls="btn btn-error btn-square", title="Emergency Escalation")

    return Form(
        Div(
            sos_btn, 
            close_chat_button(sid, "beneficiary"),
            Input(name="message", id="chat-input", placeholder="Type your message to resume..." if is_inactive else "Type your message...", cls="input input-bordered w-full" + (" border-warning" if is_inactive else "")),
            Button("Send", cls="btn btn-primary mt-2", type="submit", hx_disable_elt="this"),
            cls="flex gap-2 p-4 bg-base-200 border-t items-center"
        ), 
        id="beneficiary-input-form", 
        hx_post=f"/beneficiary/{sid}/send",
        hx_target="#chat-messages", 
        hx_swap="beforeend", 
        hx_on="htmx:afterRequest: this.reset(); htmx:afterSwap: (function(){var el=document.getElementById('chat-window'); if(el) el.scrollTop = el.scrollHeight; })()", 
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
    content = ""
    if s.state == ChatState.CLOSED:
        return Div("", id="beneficiary-controls")
    if s.state == ChatState.INTAKE:
        content =  Div("Please answer all intake questions to continue.", cls="alert alert-warning mt-4")
    
    if s.state == ChatState.WAITING_FOR_NURSE:
        content =  Div("Your intake is complete. Waiting for a nurse...", cls="alert alert-info mt-4")
    
    if s.state in (ChatState.NURSE_ACTIVE, ChatState.URGENT):
        content = Div("You may continue chatting with the nurse.", cls = "alert alert-success mt-4")
    
    return Div(content, id="beneficiary-controls")
    

def nurse_form(sid: str, s: ChatSession) -> Any:
    """ 
    Render the nurse reply form for an active chat session.
    
    Sends a nurse response and updates the chat window using HTMX.
    
    Args:
        sid (str): Chat session ID.
        s (ChatSession): Current session object
        
    Returns:
        Any: FastHTML Form component.
    """
    if s.state == ChatState.CLOSED:
        return Div(
            Div(Span("🛑 This session is closed.", cls="alert alert-info w-full text-center")),
            Div(A("Back to Dashboard", href="/nurse", cls="btn btn-primary mt-4")),
            id="nurse-input-form",
            hx_swap_oob="true",
            cls="p-4"
        )
    
    # Check if this is an urgent case
    is_urgent = s.state == ChatState.URGENT

    # Top controls - close button and complete button if urgent
    controls = Div(
        close_chat_button(sid, "nurse"),
        (nurse_complete_button(sid, is_urgent) if is_urgent else ""),
        cls="flex gap-2"
    )

    return Form(
        Div(
            controls,
            Input(type="hidden", name="sid", value=sid),
            Input(name="message", id="chat-input", placeholder="Reply to beneficiary...", cls="input input-bordered w-full"),
            Button("Send", cls="btn btn-primary mt-2", type="submit", hx_disable_elt="this"),
            cls="flex flex-col gap-2 p-4 bg-base-200 border-t"
        ),
        id="nurse-input-form",
        hx_post=f"/nurse/{sid}/send",
        hx_target="#chat-messages", 
        hx_swap="beforeend",
        hx_on="htmx:afterRequest: this.reset(); htmx:afterSwap: (function(){var el=document.getElementById('chat-window'); if(el) el.scrollTop = el.scrollHeight; })()",
        method="post"
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
        CardBody(*([P(error_message, cls="bg-red-600 font-semibold")] if error_message else []),
            Form(LabelInput("Email", name="email", value=prefill_email, placeholder="user@example.com",),
                LabelInput("Password", name="password", type="password", placeholder="Enter your password"),
                Div(Button("Login", cls=ButtonT.primary + " rounded-lg py-2 px-4 md:py-3 md:px-5 text-sm md:text-base", type="submit"),cls="mt-4"),
                action="/login",method="post")),
        CardFooter("Do not have an account? ", A(B("Sign up"), href="/signup")))


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
        CardBody(*([P(error_message, cls="text-red-600 font-semibold")] if error_message else []),
            Form(LabelInput( "Email",name="email", value=prefill_email, placeholder="user@example.com"),
                LabelInput("Password",name="password",type="password",placeholder="Choose a password"),
                LabelInput("Repeat Password", name="repeat_password", type="password", placeholder="Repeat password"),
                Div(Label("Role"), Select(Option("Beneficiary", value="beneficiary"),
                        Option("Nurse", value="nurse"),name="role",cls="select select-bordered w-full"),cls="mt-2"),
                Div(Button("Sign Up", cls=ButtonT.primary + " rounded-lg py-2 px-4 md:py-3 md:px-5 text-sm md:text-base"),),
                action="/signup", method="post")),
        CardFooter("Already have an account? ",
            A(B("Login"), href="/login")))



def session_row(s: ChatSession):
    """
    Renders a single row in the nurse's archive table.
    Highlights unread sessions to prioritize patient safety.
    """
    row_style = "bg-blue-50 font-bold" if not s.is_read else ""

    return Tr(style=row_style)(
        Td(s.user_email),
        Td(Span(s.state.value.upper(), cls=f"badge {'badge-error' if s.state == ChatState.URGENT else 'badge-info'}")),
        Td(str(s.intake.answers.get("chief_complaint", "N/A")).capitalize()),
        Td(
            Div(
                A("Review", href=f"/nurse/{s.session_id}", cls="btn btn-primary btn-sm"),
                cls="flex gap-2"
                )
            )
        )

def session_resume_notice(session_id: str) -> Any:
    """
    Dismissible alert shown when a session has been reactivated from INACTIVE state.
    This appears at the top of the chat to inform the user their session resumed.

    Args:
        session_id: The session that was reactivated

    Returns:
        A dimissible alert component
    """ 
    return Div(
        Div(
            DivLAligned(
                Span("ℹ️", cls="text-2xl"),
                Div(
                    Strong("Session Resumed"),
                    P("Your session was inactive but has been resumed. You can continue where you left off.",
                      cls=TextPresets.muted_sm),
                    cls="ml-3"
                )
            ),
            Button(
                "X", 
                cls="btn btn-sm btn-circle btn-ghost",
                onclick="this.parentElement.parentElement.remove()"
            ),
            cls="alert alert-info flex justify-between items-start"
        ),
        id=f"resume-notice-{session_id}",
        cls="mb-4"
    )

def completion_modal(session_id: str) -> Any:
    """
    Modal for nurses to complete/close a case with required documentation.
    Enforces minimum 20-character comment requirement.
    
    Args:
        session_id: The session being completed
        
    Returns:
        Modal component with form for case completion
    """
    return Div(
        # Modal backdrop
        Input(type="checkbox", id=f"completion-modal-{session_id}", cls="modal-toggle"),
        
        # Modal content
        Div(
            Div(
                # Modal header
                H3("Complete Case", cls="font-bold text-lg"),
                P("Document the resolution of this case. This action will close the case and remove it from your active queue.",
                  cls=TextPresets.muted_sm + " py-2"),
                
                # Alert about urgent cases
                Div(
                    DivLAligned(
                        Span("⚠️"),
                        P("This is an urgent case. Please confirm you have attempted appropriate follow-up contact before closing.",
                          cls="ml-2")
                    ),
                    cls="alert alert-warning mb-4"
                ),
                
                # Completion form
                Form(
                    Div(
                        Label(
                            Span("Completion Notes", cls="label-text font-semibold"),
                            Span("(minimum 20 characters)", cls="label-text-alt text-gray-500"),
                            cls="label"
                        ),
                        Textarea(
                            id=f"completion-note-{session_id}",
                            name="completion_note",
                            placeholder="Example: Patient contacted by phone, confirmed symptoms resolved.\n\nOR\n\nUnable to reach patient after 2 call attempts. Left voicemail requesting callback. Case closed pending patient re-contact.",
                            cls="textarea textarea-bordered h-32 w-full",
                            required=True,
                            minlength="20",
                            oninput=f"document.getElementById('submit-completion-{session_id}').disabled = this.value.trim().length < 20"
                        ),
                        P(
                            "Character count: ",
                            Span("0", id=f"char-count-{session_id}"),
                            " / 20 minimum",
                            cls="text-sm text-gray-500 mt-1"
                        ),
                        cls="form-control w-full"
                    ),
                    
                    # Action buttons
                    Div(
                        Label(
                            "Cancel",
                            fr=f"completion-modal-{session_id}",
                            cls="btn btn-ghost"
                        ),
                        Button(
                            "Complete Case",
                            id=f"submit-completion-{session_id}",
                            type="submit",
                            cls="btn btn-primary",
                            disabled=True  # Disabled until 20 chars entered
                        ),
                        cls="modal-action"
                    ),
                    
                    method="post",
                    action=f"/nurse/session/{session_id}/complete",
                    hx_post=f"/nurse/session/{session_id}/complete",
                    hx_target="#chat-root",
                    hx_swap="outerHTML"
                ),
                
                # Character counter script
                Script(f"""
                    const textarea = document.getElementById('completion-note-{session_id}');
                    const counter = document.getElementById('char-count-{session_id}');
                    textarea.addEventListener('input', function() {{
                        counter.textContent = this.value.trim().length;
                    }});
                """),
                
                cls="modal-box max-w-2xl"
            ),
            cls="modal"
        ),
        id=f"completion-modal-container-{session_id}"
    )

def inactive_session_banner(session: ChatSession) -> Any:
    """
    Banner shown when viewing an INACTIVE session (within grace period).
    Informs user they can still send messages to resume.
    
    Args: 
        session: The inactive session

    Returns:
        Alert banner component
    """
    minutes_left = 80 - session.minutes_since_activity

    return Div(
        DivLAligned(
            Span("⏸️", cls="text-2xl"),
            Div(
                Strong("Session Inactive"),
                P(f"This session has been inactive. You have approximately {minutes_left} minutes to send a message and resume. After that, the session will be permanently closed.",
                  cls=TextPresets.muted_sm),
                  cls="ml-3"
            )
        ),
        cls="alert alert-warning mb-4"
    )

def completed_session_view(session: ChatSession, messages: List[Message]) -> Any:
    """
    View for a COMPLETED session - shows history with completion note and option to start new session.
    
    Args: 
        session: The completed session
        messages: All messages in the session
        
    Returns:
        Complete view component for completed session
    """
    # Find the completion message
    completion_msg = next((m for m in messages if m.phase == "completion"), None)

    return Div(
        # Header indicating completed status
        Div(
            H3("Completed Consultation", cls="text-xl font-bold"),
            Span("This case has been completed by a nurse and is now closed.", cls="badge badge-success"),
            cls="flex justify-between items-center mb-4 p-4 bg-base-200 rounded-lg"
        ),
        # Completion note (if exists)
        (Card(
            H4("Case Completion Notes", cls=TextPresets.bold_sm),
            Div(completion_msg.content, cls="prose mt-2"),
            P(f"Completed at {completion_msg.display_time}", cls=TextPresets.muted_sm + " mt-2"),
            cls="mb-4 bg-green-50"
        ) if completion_msg else ""),

        # Chat history
        Div(
            H4("Conversation History", cls="mb-2"),
            Div(
                *[chat_bubble(m, "beneficiary") for m in messages if m.phase != "completion"],
                cls="space-y-2 max-h-96 overflow-y-auto p-4 bg-base-100 rounded-lg"
            ),
            cls="mb-4"
        ),
        # Action button
        Div(
            A(
                "Back to Dashboard",
                href="/beneficiary",
                cls="btn btn-ghost"
            ),
            A(
                "Start New Consultation",
                href="/start",
                cls="btn btn-primary"
            ),
            cls="flex justify-between"
        ),
        id="completed-session-view"
    )

def nurse_complete_button(session_id: str, is_urgent: bool) -> Any:
    """
    Button for nurses to initiate case completion.
    Opens the completion modal.
    
    Args:
        session_id: The session to complete
        is_urgent: Whether this in an urgent case
        
    Returns:
        Label button that triggers completion modal
    """
    button_text = "Complete Urgent Case" if is_urgent else "Complete Case"
    button_class = "btn btn-warning btn-sm" if is_urgent else "btn btn-success btn-sm"

    return Label(
        button_text,
        fr=f"completion-modal-{session_id}",
        cls=button_class,
        title="Formally close this case with documentation"
    )