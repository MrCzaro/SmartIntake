import sqlite3

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
