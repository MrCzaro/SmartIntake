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


def nurse_case_card(s: ChatSession): # not used
    """
    Renders a preview card for a specific chat session in the nurse dashboard.
    
    The card displays the session ID, the most recent message, and a prominent
    'URGENT' badge if the session state is set to URGENT.
    It also provides a link to open the full case view.
    
    Args: 
        s (ChatSession): The session data used to populate the card.
        
    Returns:
        Div: A styled card component using MonsterUI/DaisyUI classes.
    """
    last_msg = s.messages[-1].content if s.messages else "No messages yet."

    is_urgent = s.state == ChatState.URGENT

    # Conditional styling for urgent alerts
    urgent_styles = "bg-error/10 border-l-8 border-error shadow-lg" if is_urgent else "bg-base-100"
    
    return Div(
        DivLAligned( Div(f"Session: {s.session_id[:8]}", cls="font-mono text-sm font-bold"), Span("URGENT", cls="badge badge-error ml-2") if is_urgent else Span()),
        Div(f"Last message: {last_msg[:80]}...", cls="text-sm mt-1"),
        A("Open case", href=f"/nurse/{s.session_id}", cls="btn btn-primary btn-sm mt-2 w-full"),cls=f"card {urgent_styles} shadow p-4 transition-all duration-300")


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

def close_chat_button(sid: str, role: str):
    """
    A consistent 'End Chat' button for both roles.
    """
    close_cls =  "btn btn-warning btn-square"
    label = "✖"
    tit = "Close Session"
    if role == "nurse":
        return A(
            label, 
            hx_post=f"/nurse/session/{sid}/close",
            hx_confirm="Are you sure you want to end this session?",
            cls=close_cls,
            title=tit)
    return A(
        label,
        hx_post=f"/beneficiary/{sid}/close",
        hx_confirm="Are you sure you want to end this session?",
        hx_target="body",
        cls=close_cls,
        title=tit
    )

def beneficiary_chat_fragment(sid: str, s:ChatSession, user_role: str):
    """
    Assembles the complete chat interface for a beneficiary.

    This top-level fragment combines the chat history window, the message 
    input form, and the state-dependent controls (like 'Please answer all intake questions').

    Args:
        sid (str): The unique session ID.
        s (ChatSession): The current state and data of the chat session.
        user_role (str): The current user's role.

    Returns:
        Div: A single container encapsulating the full beneficiary view.
    """
    return Div(chat_window(s.messages, sid, user_role), beneficiary_form(sid,s), beneficiary_controls(s), id="chat-fragment")

def nurse_chat_fragment(sid: str, s:ChatSession, user_role):
    """
    Assembles the complete chat interface for a nurse.
    
    Similar to the beneficiary fragment, but provides the nurse-specific
    form and omits the intake progress controls.
    
    Args:
        sid (str): The unique session ID.
        s (ChatSession): The current state and data of the chat session.
        user_role (str): The current user's role.
        
    Returns:
        Div: A single container encapsulating the full nurse view.
    """
    return Div(chat_window(s.messages, sid, user_role), nurse_form(sid, s), id="chat-fragment")


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
    is_urgent = s.state == ChatState.URGENT

    status_content = Span("🆘 NURSE NOTIFIED - Responding Shortly", cls="font-bold animate-pulse") if is_urgent else \
                    Button("EMERGENCY: NEED A NURSE", 
                           hx_post=f"/beneficiary/{s.session_id}/emergency", 
                           hx_target="#chat-messages",
                           hx_confirm="Are you sure you need to escalate to emergency care?",
                           hx_on__htmx_config_request="this.setAttribute('disabled', 'disabled')",
                           cls="btn btn-error btn-sm lg:btn-md")
    header_cls = "navbar bg-error/20 border-b-4 border-error" if is_urgent else "navbar bg-base-100 border-b-2 border-base-300"

    return Div(H3("MedAIChat", cls="text-xl font-bold"), status_content,id = "chat-header",
               cls=f"{header_cls} mb-4 flex justify-between px-4 sticky top-0 z-50")


       
def beneficiary_form(sid: str, s: ChatSession) -> Any:
    """
    Render the beneficiary message input form.
    
    Sends a chat message to the backend using HTMX and appends
    the server-rendered bubble(s) into the chat window.
    
    Args:
        sid (str): Chat session ID.
    
    Returns:
        Any: FastHTML Form component.
    """
    if s.state == ChatState.CLOSED:
        return Div(
            Div(Span("🛑 This session is closed.", cls="alert alert-info w-full text-center")),
            Div(A("Back to Dashboard", href="/beneficiary", cls="btn btn-primary mt-4")),
            cls="p-4"
        )
    
    is_escalated = s.state in (ChatState.URGENT, ChatState.NURSE_ACTIVE)

    if is_escalated:
        sos_btn = Span("✅ Notified", cls="btn btn-ghost no-animation text-success btn-square")
    else:
        sos_btn = Button("🆘", hx_post=f"/beneficiary/{sid}/emergency", hx_target="#chat-messages", hx_confirm="Escalate to a nurse?",
                hx_on__htmx_config_request="this.setAttribute('disabled', 'disabled')", type="button",  cls="btn btn-error btn-square", title="Emergency Escalation")

    return Form(
        Div(
            sos_btn, 
            close_chat_button(sid, "beneficiary"),
            Input(name="message", id="chat-input", placeholder="Type your message...", cls="input input-bordered w-full"),
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
        
    Returns:
        Any: FastHTML Form component.
    """

    return Form(
        Div(
            Div(close_chat_button(sid, "nurse"), cls="flex gap-2"),
            Input(type="hidden", name="sid", value=sid),
            Input(name="message", id="chat-input", placeholder="Reply to beneficiary...", cls="input input-bordered w-full"),
            Button("Send", cls="btn btn-primary mt-2", type="submit", hx_disable_elt="this"),
            cls="flex flex-col gap-2 p-4 bg-base-200 border-t"
        ),
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






def past_sessions_table(session_list: list[ChatSession]): # used in nurse archive so far not used
    """
    Renders a scannable table of previous medical consultations.
    """
    header = Thead(Tr(Th("Date"), Th("Issue"), Th("Status"), Th("Action")))

    rows = []
    for s in session_list:
        # We grab the first intake answer as the 'Issue' summary
        issue = s.intake.answers.get("chief_complaint", "General Inquiry")[:30] + "..."

        rows.append(Tr(
            Td(s.messages[0].timestamp.strftime("%Y-%m-%d %H:%M") if s.messages else "N/A"),
            Td(issue),
            Td(Span(s.state.value.upper(), cls="badge badge-ghost")),
            Td(A("View", href=f"/beneficiary/archieve/{s.session_id}", cls="btn btn-sm btn-primary"))
        ))
    
    return Table(header, Tbody(*rows), cls="table w-full")

def session_row(s: ChatSession):
    """
    Renders a single row in the nurse's archive table.
    Highlights unread sessions to prioritize patient safety.
    """
    row_style = "bg-blue-50 font-bold" if not s.is_read else ""

    return Tr(style=row_style)(
        Td(s.user_email),
        Td(Span(s.state.value.upper(), cls=f"badge {'badge-error' if s.state == ChatState.URGENT else 'badge-info'}")),
        Td(s.intake.answers.get("chief_complaint", "N/A").capitalize()),
        Td(
            Div(
                A("Review", href=f"/nurse/{s.session_id}", cls="btn btn-primary btn-sm"),
                cls="flex gap-2"
                )
            )
        )

def render_nurse_review(s: ChatSession, messages: list[Message]): # used in session details, not used so far 
    """
    Creates the full HTML page for the nurse to review a case.

    Args:
        s (ChatSession): The chat session data.
        messages (list[Message]): The list of chat messages in the session.
    """

    return Titled(f"Review: {s.user_email}",
                  Card(
                      H3("Patient Intake Data"),
                      Ul(*[Li(f"{k.replace("_", "").capitalize()}: {v}") for k, v in s.intake.answers.items()])
                  ),
                  Div(id="chat-history", cls="my-4")(
                      *[chat_bubble(m, "nurse") for m in messages]
                  ),
                  # A place for the nurse to write their own summary/notes
                  Form(hx_post=f"/nurse/session/{s.session_id}/finalize")(
                      Textarea(name="nurse_summary", placeholder="Enter final clinical notes and summary...",
                      cls="textarea textarea-bordered w-full"),
                      Button("Finalize & Archive", cls="btn btn-primary mt-2")
                  ))

def nurse_sidebar_link(count: int): # Not used
    badge = Span(count, cls="badge badge-error ml-2") if count > 0 else ""
    return Li(A(href="/nurse")("Active Cases", badge))




def nurse_case_row(s:ChatSession): 
    """
    Renders a single row in the nurse dashboard table.
    """
    # Formating the timestamp
    time_str = s.timestamp.strftime("%H:%M") if isinstance(s.timestamp, datetime) else str(s.timestamp)

    # Dynamic badges for status
    status_cls = "badge-warning" if s.state == ChatState.URGENT else "badge-info"

    case_row = Tr(
        Td(time_str, cls="font-mono text-xs"),
        Td(s.session_id[:8] + "...", cls="font-mono text-xs opacity-50"),
        Td(Span(s.state.name, cls=f"badge {status_cls} badge-sm")),
        Td(
            A("Open Chat", href="/nurse/chat/{s.session_id}", cls="btn btn-xs btn-ghost"),
            close_chat_button(s.session_id, "nurse")
        ),
        id=f"session-row-{s.session_id}"
    )
    return case_row

def nurse_dashboard_table(sessions):
    """
    The container table.
    """
    if not sessions:
        return Div("No activbe cases found.", cls="p-10 text-center opacity-50 italic")
    
    tab = Table(
        Thead(Tr(Th("Time"), Th("ID"), Th("Status"), Th("Actions"))),
        Tbody(*[nurse_case_row(s) for s in sessions]),
        cls="table table-zebra w-full"
    )
    return tab