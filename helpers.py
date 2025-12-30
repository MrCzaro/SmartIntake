import bcrypt
import sqlite3
from typing import Dict, TypeVar
from functools import wraps
from inspect import iscoroutinefunction
from fasthtml.common import Redirect, HTTPException
from starlette.requests import Request



# Generic type for chat sessions (import ChatSession where used)
TSession = TypeVar("TSession")



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
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8")
    )


def get_db() -> sqlite3.Connection:
    """
    Create and return a SQLite database connection.
    
    The connection uses `sqlite3.Row` as row factory,
    allowing column access by name.
    
    Returns:
        sqlite3.Connection: Open database connection.
    """

    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    Initialize the database schema.
    
    Creates the `users` table if it does not already exist.
    This function is safe to call multiple times.
    """
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)
        """
    )
    db.commit()
    db.close()


def get_session_or_404(sessions: Dict[str, TSession], sid: str) -> TSession:
    """
    Retrieve a chat session by ID or raise a 404 error.
    
    Args:
        sessions (dict[str, TSession]): In-memory session store.
        sid (str) : Session ID.
        
    Raises:
        HTTPEXception: 404 if session does not exist.
        
    Returns:
        TSession: The requested chat session.
    """
    session = sessions.get(sid)
    if session is None: 
        raise HTTPException(404, "Session not found")
    return session


def  require_role(request: Request, role:str) -> None:
    """
    Ensure the current user has the required role.
    
    Args:
        request (Request): Starlette request object.
        role (str): Required role name (e.g. "nurse", "beneficiary").
    Raises:
        Redirect: Redirects to home if role is not authorized.
    """
    if request.session.get("role") != role:
        raise Redirect("/")



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