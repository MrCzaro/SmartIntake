from fasthtml.common import Redirect
from inspect import iscoroutinefunction
from functools import wraps
import bcrypt

def hash_password(plain_password: str) -> str:
    hashed = bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt())
    return hashed.decode()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode(),
        hashed_password.encode()
    )

def login_required(route_func):
    """
    Restrict access to authenticated usesrs in FastHTML routes.
    Works for both sync and async route handlers.
    Redirects to `/login` if no `user` key exists in session.
    """
    @wraps(route_func)
    async def wrapper(request, *args, **kwargs):
        if not request.session.get("user"):
            return Redirect("/login")

        # If the original route is async, await it
        if iscoroutinefunction(route_func):
            return await route_func(request, *args, **kwargs)
        
        # If normal sync function,
        return route_func(request, *args, **kwargs)
    
    return wrapper