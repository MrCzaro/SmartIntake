from fasthtml.common import *
from monsterui.all import *
from typing import Any


def beneficiary_form(sid: str, intake_complete: bool) -> Any:
    """
    Render the beneficiary message input form.
    
    Sends a chat message to the backend using HTMX and updates
    the chat window with the server-rendered response.
    
    
    Args:
        sid (str): Chat session ID.
        intake_complete (bool) : Whether intake has been completed.
    
    Returns:
        Any: FastHTML Form component.
    """

    return Form( 
        Input(type="hidden", name="sid", value=sid),
        Input(
            name="message",
            placeholder="Type your message...",
            cls="input input-bordered w-full"
        ),
        Button("Send", cls="btn btn-primary mt-2"),
        hx_post=f"/beneficiary/{sid}/send",
        hx_target="#chat-window",
        hx_swap="outerHTML"
    )


def beneficiary_controls(sid: str, intake_complete: bool) -> Any:
    """
    Render intake control actions for the beneficiary.
    
    Displays either:
    - A button to complete intake and notify the nurse, or
    - An informational message once intake is complete.
    
    Args:
        sid (str): Chat session ID.
        intake_complete (bool) : Whether intake is finished.
        
    Returns:
        Any: FastHTML Form component.
    """
    if intake_complete:
        return Div(
            "Intake completed. You may continue messaging.",
            cls="alert alert-info mt-4"
        )
    
    return Form(
        Button(
            "Finish intake and send to Nurse",
            cls="btn btn-success mt-4"
        ),
        hx_post=f"/beneficiary/{sid}/complete",
        hx_target="body",
        hx_swap="outerHTML"
    )


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
        Input(name="message", placeholder="Reply to beneficiary...", cls="input input-bordered w-full"),
        Button("Send", cls="btn btn-primary mt-2"),
        hx_post=f"/nurse/{sid}/send",
        hx_target="#chat-window",
        hx_swap="outerHTML"
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

