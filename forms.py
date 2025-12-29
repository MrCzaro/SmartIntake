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

def login_card
