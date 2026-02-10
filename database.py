import sqlite3
from starlette.middleware.base import BaseHTTPMiddleware


class DatabaseMiddleware(BaseHTTPMiddleware):
    """
    Middleware to provide a database connection for each request.
    The connection is available as `request.state.db`.
    """

    async def dispatch(self, request, call_next):
        request.state.db = get_db()
        
        try:
            response = await call_next(request)
        finally:
            request.state.db.close()
        return response



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
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

    
def init_db() -> None:
    """
    Initialize the database schema.
    
    Creates the `users` table if it does not already exist.
    This function is safe to call multiple times.
    """
    db = get_db()
    
    # User table
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)
        """
    ),
    
    # Session table
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_email TEXT NOT NULL,
            state TEXT NOT NULL,
            summary TEXT,
            is_read BOOLEAN DEFAULT 0,
            intake_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_activity DATETIME DEFAULT CURRENT_TIMESTAMP)
        """
    )

    # Chat persistence table
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL, 
            phase TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions (id)
        )
    """)
    
    # Migration: Add last_activity column if it does not exist
    # This handles existing databases that do not have this field yet.
    try:
        db.execute("SELECT last_activity FROM sessions LIMIT 1")
    except sqlite3.OperationalError:
        print("[MIGRATION] Adding last_activity column to session table...")
        db.execute("ALTER TABLE sessions ADD COLUMN last_activity DATETIME")
        # Update existing sessions to have their last_activity set to created_at
        db.execute("UPDATE sessions SET last_activity = created_at")
        db.commit()
        print("[MIGRATION] Migration complete!")
    db.commit()
    db.close()


