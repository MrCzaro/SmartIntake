import bcrypt
from typing import Optional
from functools import wraps
from inspect import iscoroutinefunction
from starlette.requests import Request
from fasthtml.common import Redirect

def  require_role(request: Request, role:str) -> Optional[Redirect]:
    """
    Ensure the current user has the required role.
    
    Args:
        request (Request): Starlette request object.
        role (str): Required role name (e.g. "nurse", "beneficiary").
    Raises:
        Redirect: Redirects to home if role is not authorized.
    """
    if request.session.get("role") != role:
        return Redirect("/")
    return None



def login_required(route_func):
    """
    Require authentication for a FastHTML route.

    Works for both sync and async route handlers.
    Redirects unauthenticated users tp `/login`.

    Args:
        route_func (Callable): Route handler function.

    Returns:
        Callable: Wrapped route handler.
    """
    @wraps(route_func)
    async def wrapper(request: Request, *args, **kwargs):
        if not request.session.get("user"):
            return Redirect("/login")

        if iscoroutinefunction(route_func):
            return await route_func(request, *args, **kwargs)
        
        return route_func(request, *args, **kwargs)
    
    return wrapper


def hash_password(plain_password: str) -> str:
    """
    Has a plaintext password using bcrypt.
    
    The password is encoded to UTF-8 bytes and hashed with
    a randomly generated salt. The resulting has is returned
    as a UTF-8 string for storage (e.g. in a database).
    
    Args:
        plain_password (str): User-provided plaintext password.
        
    Returns:
        str: Bcrypt hashed password (UTF-8 encoded).
    """
    hashed : bytes = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash.
    
    Args:
        plain_password (str): Password provided by the user.
        hashed_password (str): Stored bcrypt hash.
        
    Returns:
        bool: True if the password matches the hash, False otherwise.
    """
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
