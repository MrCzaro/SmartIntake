from fasthtml.common import *
from monsterui.all import *

def beneficiary_form(sid: str, intake_complete: bool):
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

def beneficiary_controls(sid: str, intake_complete: bool):
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

def nurse_form(sid: str):
    return Form(
        Input(type="hidden", name="sid", value=sid),
        Input(name="message", placeholder="Reply to beneficiary...", cls="input input-bordered w-full"),
        Button("Send", cls="btn btn-primary mt-2"),
        hx_post=f"/nurse/{sid}/send",
        hx_target="#chat-window",
        hx_swap="outerHTML"
    )

def login_card(error_message: str|None = None, prefill_email: str = ""):
    """
    Returns a login card form.
        error_message: Optional error message to display.
        prefill_email: Optional email to prefill the form.
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
                        cls="ButtonT.primary + rounded-lg py-2 px-4 md:py-3 md:px-5 text-sm md:text-base",
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


def signup_card(error_message: str | None = None, prefill_email: str =""):
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
                    Button("Sign Up", cls=ButtonT.primary + " mt-4"),
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

