import os
import psycopg2
from psycopg2.extras import RealDictCursor, Json
import logging

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- FIX START ---
# Vercel Storage uses POSTGRES_URL. We fallback to DATABASE_URL just in case.
# We also enforce SSL mode which is required for Neon.
DB_URL = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")

if not DB_URL:
    logger.error("❌ DATABASE ERROR: No 'POSTGRES_URL' or 'DATABASE_URL' found in Environment Variables.")

def get_db_connection():
    try:
        # We explicitly pass the DSN (Data Source Name)
        # sslmode='require' is often needed for cloud DBs
        conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor, sslmode='require')
        return conn
    except Exception as e:
        logger.error(f"DB Connection Failed: {e}")
        # Re-raising allows Vercel logs to catch the specific error
        raise e
# --- FIX END ---

def init_db():
    """
    Initializes the database schema.
    Run this manually or check on startup (careful with cold start latency).
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # 1. Users Table (For Guild Members list)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 2. User States (The "RAM" for our stateless bot)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_states (
                    user_id BIGINT PRIMARY KEY,
                    chat_id BIGINT,
                    state TEXT DEFAULT 'DASHBOARD',
                    data JSONB DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 3. Transactions (The Financial History)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id),
                    amount NUMERIC(10, 2) NOT NULL,
                    description TEXT,
                    involved_users TEXT[], -- Array of names/ids
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            conn.commit()
            logger.info("Database Schema Initialized.")
    except Exception as e:
        logger.error(f"Schema Init Failed: {e}")
    finally:
        conn.close()

# --- State Management Methods ---

def get_user_state(user_id):
    """
    Fetches the current state of a user.
    Returns default 'DASHBOARD' if user not found.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT state, data FROM user_states WHERE user_id = %s", (user_id,))
            result = cur.fetchone()
            if result:
                return result
            return {'state': 'DASHBOARD', 'data': {}}
    finally:
        conn.close()

def update_user_state(user_id, chat_id, state, data=None):
    """
    Updates the user's position in the app flow.
    Upsert logic: Insert if new, Update if exists.
    """
    conn = get_db_connection()
    data = data if data is not None else {}
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_states (user_id, chat_id, state, data, updated_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) 
                DO UPDATE SET 
                    state = EXCLUDED.state, 
                    chat_id = EXCLUDED.chat_id,
                    data = EXCLUDED.data,
                    updated_at = CURRENT_TIMESTAMP;
            """, (user_id, chat_id, state, Json(data)))
            conn.commit()
    finally:
        conn.close()

# --- Transaction Methods ---

def add_transaction(user_id, amount, description, involved=None):
    conn = get_db_connection()
    involved = involved if involved else []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO transactions (user_id, amount, description, involved_users)
                VALUES (%s, %s, %s, %s)
            """, (user_id, amount, description, involved))
            conn.commit()
    finally:
        conn.close()

def get_balances():
    """
    Calculates balances. 
    (Simplified for Phase 2: Just returns total spent per user).
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.username, SUM(t.amount) as total
                FROM transactions t
                JOIN users u ON t.user_id = u.user_id
                GROUP BY u.username
            """)
            return cur.fetchall()
    finally:
        conn.close()
