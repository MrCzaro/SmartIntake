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
    
    Returns:
        Redirect to favicon.ico
    """
    return Redirect("/static/favicon.ico")

### Registration/Login/Logout
@rt("/signup")
async def signup_user(request):
    """
    Handler user registration for both beneficiaries and nurses.
    
    GET: Display signup form
    POST: Process registration, create user account, and establish session.
    
    Returns: 
        GET: Signup form page
        POST: Redirect to / (role-based dashboard) on success, or form with errors.
    """
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
    """
    Handle user authentication for existing accounts.
    
    GET: Display login form
    POST: Validate credentials and establish session
    
    Returns:
        GET: Login form page
        POST: Redirect to / (role-based dashboard) on success, or form with errors.
    """
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
    """
    Clear user session and redirect to login page.
    
    Returns:
        Redirect to /login
    """
    request.session.clear()
    return Redirect("/login")

### Home Route
@rt("/")
@login_required
def index(request):
    """
    Role-based dashboard router for authenticated users.
    
    Redirects users to their appropriate dashboard based on role:
    - Beneficiaries -> /beneficiary (patient consultation view)
    - Nurses -> /nurse (triage queue view)
    
    Returns:
        Redirect to role-specific dashboard
    """
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
    """
    Create new consultation session for authenticated beneficiaries.
    
    Initializes a new ChatSession with INTAKE state and first intake question.
    Redirects to the chat interface for the new session
    
    Returns:
        Redirect to /beneficiary/{session_id}
    """
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
    """
    HTMX polling endpoint for real-time chat updates.
    
    Called every 3 seconds by cilent to refresh chat messages, controls, and session status.
    Runs cleanup on each poll to handle timeouts.
    
    Args:
        request: Authenticated request
        id: Session ID to poll
        
    Returns:
        Tuple of HTMX partials: (messages, controls, form, banner)
        - messages: All chat bubbles
        - controls: Session status/instructions
        - form: Input form (only for CLOSED state)
        - banner: Inactive session warning (beneficiary only)
    
    Note:
        Returns different componets based on session state and user role.
    """
    db = request.state.db
    role = request.session.get("role")
    db_cleanup_stale_sessions(db)
    s = get_session_helper(db, sid)
    if not s: return layout(request, Card(H3("Session not found")), "Error")
    
    messages = Div(*[chat_bubble(m, role) for m in s.messages])
    controls = beneficiary_controls(s) if role == "beneficiary" else ""
    banner = inactive_banner_fragment(s) if role == "beneficiary" else ""

    if s.state == ChatState.CLOSED:       
        if role == "beneficiary":
            form = beneficiary_form(s.session_id, s)
        if role == "nurse":
            form = nurse_form(s.session_id, s)
        return messages, controls, form, banner
      
    return messages, controls, banner

@rt("/nurse/poll")
@login_required
def nurse_poll(request):
    """
    HTMX polling endpoint for nurse dashboard updates.
    
    Called every 3 seconds to refresh avtive cases queue and urgent count.
    Runs cleanup to move stale sessions to INACTIVE/CLOSED states.
    
    Returns:
        Tuple of HTMX partials (case_table, urgent count)
        - case table: Active sessions or 'no cases' message
        - urgent_badge: Count of urgent cases with styling.
    """
    db = request.state.db
    guard = require_role(request, "nurse")
    if guard: return guard
    db_cleanup_stale_sessions(db)
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
    """
    Display beneficiary's consultation history and start button.
    
    Shows all past and active consultation for the current user,
    with ability to start new session or view existing ones.
    
    Returns:
        Full page with consultation table and "Start New" button.
    """
    db = request.state.db
    db_cleanup_stale_sessions(db)
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
    """
    Display active chat session interface for beneficiary.
    
    Shows full chat interface with message history, input form,
    emergency button, and session controls.
    
    Args:
        request: Authenticated beneficiary request
        sid: Session ID to display
    
    Returns:
        Full page with chat interface
    """
    db = request.state.db
    guard = require_role(request, "beneficiary")
    if guard: return guard

    role = request.session.get("role")
    s = get_session_helper(db, sid)
    if not s: return layout(request, Card(H3("Session not found")), "Error")

    content = Titled(f"Beneficiary Chat", render_chat_view(s, role))
    return layout(request, content, page_title = "Beneficiary Chat - MedAIChat")


@rt("/beneficiary/{sid}/send")
@login_required
async def beneficiary_send(request, sid: str):
    """
    Process beneficiary message submission and handle session reactivation.
    
    Handles incoming messages from beneficiaries, manages session reactivation
    for INACTIVE sessions, and controls intake workflow including emergency
    escalation and question progression.
    
    Args:
        request: Beneficiary request with form data
        sid: Session ID receiving the message
    
    Form Data: User's message text
    
    Returns:
        HTMX partial with new messages, controls, and status updates
    """
    db = request.state.db
    role = request.session.get("role")
    guard = require_role(request, "beneficiary")
    if guard: return guard

    s = get_session_helper(db, sid)
    if not s: return Response(status_code=404)

    form = await request.form()
    message = form.get("message", "").strip()
    if not message: return "" 
     

    if s.state == ChatState.INACTIVE:
        success, status = reactivate_session(sid, db)
        if not success:
            if status == "expired":
                # Past grace period
                return Div(
                    Div("", id="inactive-banner", hx_swap_oob="true"),
                    Div("⚠️ This session has expired. Please start a new consultation.", cls="alert alert-warning"),
                    A("Start New Consultation", href="/start", cls="btn btn-primary mt-2")
                )
            return Div(
                Div("", id="inactive-banner", hx_swap_oob="true"),
                Div("Unable to resume session.", cls="alert alert-error")
            )
        s = get_session_helper(db, sid)
        if not s: return Response(status_code=404)
        
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
            s = get_session_helper(db, sid)
            return Div(
                *out,
                inactive_banner_fragment(s),
                beneficiary_controls(s)
            )
        
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
            s = get_session_helper(db, sid)
            return Div(
                *out,
                inactive_banner_fragment(s),
                beneficiary_controls(s)
            )

        else:
            next_q = INTAKE_SCHEMA[intake.current_index]["q"]
            next_msg = Message(role="assistant", content=next_q, timestamp=datetime.now(), phase="intake")
            db_save_message(db, sid, next_msg)
            out.append(chat_bubble(next_msg, "assistant"))
        
    
    db.commit()
    s = get_session_helper(db, sid)
    return Div(
        *out,
        inactive_banner_fragment(s),
        beneficiary_controls(s)
    )


@rt("/beneficiary/{sid}/emergency")
@login_required
def beneficiary_emergency(request, sid: str):
    """
    Escalate session to URGENT status via emergency SOS button.
    
    Manually flags case for immediate nurse attention, bypassing normal
    triage queue. Returns updated emergency header via HTMX.
    
    Args:
        request: Beneficiary request
        sid: Session to escalate 
    
    Returns:
        Updated emergency header showing 'NURSE NOTIFIED' status
    """
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
    """
    Close consultation session manually by beneficiary.
    
    Marks session as CLOSED and adds system message documenting closure.
    Returns either HTMX partial or full page based on request type.
    
    Args:
        request: Beneficiary request
        sid: Session to close
        
    Returns:
        HTMX request: Updated chat view with closed state
        Normal requst: Full 'Session Ended' page
    
    """
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

@rt("/beneficiary/{sid}/history")
@login_required
def view_completed_session(request, sid: str):
    """
    View the complete history of a completed session.

    Display read-only view of past consultation including all messages,
    completion notes (if any), and option to start new consultation.

    Args:
        request: Beneficairy request
        sid: Session ID to view

    Returns:
        Full page with completed session view.
    """
    db = request.state.db
    guard = require_role(request, "beneficiary")
    if guard: return guard

    s = get_session_helper(db, sid)
    if not s: return layout(request, Card(H3("Session not found")), "Error")
        
    # Check it is actually completed
    if s.state not in (ChatState.COMPLETED, ChatState.CLOSED):
        return Redirect(f"/beneficiary/{sid}")
    
    # Render completed session view
    content = Titled("Completed Consultation", completed_session_view(s, s.messages))
    return layout(request, content, page_title="Consultation History")

###  Nurse Part 
@rt("/nurse")
@login_required
def nurse_dashboard(request):
    """
    Display nurse triage dashboard with active case queue.
    
    Shows real-time list of sessions requiring nurse attention, 
    with urgent cases highlighted and auto-refresh every 3 seconds.
    
    Returns:
        Full page with dashboard layout.
    """
    guard = require_role(request, "nurse")
    if guard: return guard

    content = Titled( "Nurse Dashboard", Div("Urgent: 0", id="urgent-count", cls="badge badge-ghost"),
        Div(id="nurse-cases", hx_get="/nurse/poll", hx_trigger="load, every 3s", hx_swap="innerHTML"))
    
    return layout(request, content, page_title = "Nurse Dashboard - MedAIChat")


@rt("/nurse/{sid}")
@login_required
def nurse_view(request, sid: str):
    """
    Display nurse review interface for patient session.
    
    Shows AI-generated intake summary, full chat history, and provides
    interface for nurse to communicate with patient and mange case.
    
    Args:
        request: Nurse request
        sid: Session to review
        
    Returns:
        Full page with nurse chat interface
    """
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
    """
    Process nurse message submission to patient.
    
    Sends nurse message to beneficiary and returns message bubble
    via HTMX for real-time display.
    
    Args:
        request: Nurse request with form data
        sid: Session receiving the message
        
    Form Data:
        message: Nurse's message text
        
    Returns:
        Single chat bubble HTMX partial (nurse message)
    """
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

@rt("/nurse/session/{sid}/complete")
@login_required
async def nurse_complete_case(request, sid: str):
    """
    Formally complete case with required nurse documentation.

    Enforces minimum 20-character completion note required and 
    marks case as COMPLETED. Used primarily for urgent cases requiring 
    formal closure.

    Args:
        request: Nurse requset with form data
        sid: Session to complete

    Form Data: 
        completion_note: Nurse's documentation (min 20 chars)

    Returns:
        Success page with 'Back to Dashboard' button, or error alert.
    """
    db = request.state.db
    guard = require_role(request, "nurse")
    if guard: return guard
    nurse_email = request.session.get("user")

    form = await request.form()
    completion_note = form.get("completion_note", "").strip()

    # Validate minimum length
    if len(completion_note) < 20:
        return Div(
            Div("Completion note must be at least 20 characters.",
                cls="alert alert-error"), id="chat-root"
        )
    
    # Complete the session
    success = complete_session(sid, nurse_email, completion_note, db)

    if not success:
        return Div(
            Div("Failed to complete session. Please try again.",
                cls="alert alert-error"), id="chat-root"
        )
    
    # Fetch updated session and render
    s = get_session_helper(db, sid)
    if not s: return Div(Div("Session not found.", cls="alert alert-error"), id="chat-root")

    # Return success view
    return Div(
        Div("✅ Case completed successfully. You can now close this window.", cls="alert alert-success p-4"),
        Div(
            A("Back to Dashboard", href="/nurse", cls="btn btn-primary mt-4"),
            cls="p-4"
        ),
        id="chat-root"
    )

@rt("/nurse/session/{sid}/close")
@login_required
async def nurse_close(request, sid: str):
    """
    Close session manually by nurse.
    
    Marks session as CLOSED and documents nurse closure.
    Returns either HTMX partial or full page based on request type.
    
    Args:
        request: Nurse request
        sid: Session to close
        
    Returns:
        HTMX request: Updated chat view with closed state
        Normal request: Full 'Session Ended' page
    """
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

