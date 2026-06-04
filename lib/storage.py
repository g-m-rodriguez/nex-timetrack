"""
Nex Timetrack - SQLite storage layer
Copyright 2026 Nex AI (Kevin Blancaflor)
"""
import os
import stat
import json
import math
import sqlite3
import platform
import datetime as dt
from pathlib import Path
from contextlib import contextmanager

# Paths — were in lib/config.py, now live here
DATA_DIR = Path(os.environ.get("NEX_TIMETRACK_DIR", Path.home() / ".nex-timetrack"))
DB_PATH = DATA_DIR / "timetrack.db"
EXPORT_DIR = DATA_DIR / "exports"


# --- Helpers ---

SETTING_TYPE_MAP = {
    'default_rate': float,
    'round_to_minutes': int,
    'approval_required': bool,
}

SETTING_DEFAULTS = {
    'default_rate': 85.00,
    'currency': 'EUR',
    'currency_symbol': '€',
    'round_to_minutes': 15,
    'approval_required': False,
}

CATEGORY_SEED = [
    'development', 'design', 'meeting', 'research', 'admin',
    'support', 'review', 'testing', 'deployment', 'planning',
    'communication', 'other',
]


@contextmanager
def _connect():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --- DB init & migration ---

def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    if platform.system() != "Windows":
        try:
            os.chmod(str(DATA_DIR), stat.S_IRWXU)
        except OSError:
            pass

    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                rate REAL,
                contact_email TEXT,
                notes TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                client_id INTEGER,
                rate REAL,
                budget_hours REAL,
                notes TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                client_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                category TEXT DEFAULT 'other',
                started_at TEXT,
                ended_at TEXT,
                duration_minutes REAL,
                billable INTEGER DEFAULT 1,
                rate REAL,
                tags TEXT,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                user_id TEXT,
                external_id TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS active_timer (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                description TEXT NOT NULL,
                project_id INTEGER,
                client_id INTEGER,
                category TEXT DEFAULT 'other',
                billable INTEGER DEFAULT 1,
                tags TEXT,
                started_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS user_roles (
                user_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('manager','timekeeper','collaborator')),
                PRIMARY KEY (user_id, role),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                client_id INTEGER NOT NULL,
                project_id INTEGER,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, client_id, project_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                active INTEGER DEFAULT 1
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
                description, notes, tags, external_id
            );

            CREATE INDEX IF NOT EXISTS idx_entries_project ON entries(project_id);
            CREATE INDEX IF NOT EXISTS idx_entries_client ON entries(client_id);
            CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(started_at);
            CREATE INDEX IF NOT EXISTS idx_entries_billable ON entries(billable);
            CREATE INDEX IF NOT EXISTS idx_entries_category ON entries(category);
            CREATE INDEX IF NOT EXISTS idx_entries_user ON entries(user_id);
            CREATE INDEX IF NOT EXISTS idx_entries_external_id ON entries(external_id);
            CREATE INDEX IF NOT EXISTS idx_projects_client ON projects(client_id);
            CREATE INDEX IF NOT EXISTS idx_clients_active ON clients(active);
            CREATE INDEX IF NOT EXISTS idx_projects_active ON projects(active);
            CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id);
            CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role);
            CREATE INDEX IF NOT EXISTS idx_assignments_user ON assignments(user_id);
            CREATE INDEX IF NOT EXISTS idx_assignments_client ON assignments(client_id);
            CREATE INDEX IF NOT EXISTS idx_categories_active ON categories(active);

            CREATE TABLE IF NOT EXISTS entry_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL,
                approver_id TEXT NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('approved','rejected')),
                reason TEXT,
                approved_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE,
                FOREIGN KEY (approver_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_approvals_entry ON entry_approvals(entry_id);
            CREATE INDEX IF NOT EXISTS idx_approvals_approver ON entry_approvals(approver_id);
        """)

        # Seed settings
        for key, value in SETTING_DEFAULTS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value))
            )

        # Migration: add approval_status column to entries if not exists
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(entries)")
        columns = {row[1] for row in cursor.fetchall()}
        if 'approval_status' not in columns:
            conn.execute("ALTER TABLE entries ADD COLUMN approval_status TEXT DEFAULT 'pending' CHECK(approval_status IN ('pending','approved','rejected'))")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_approval ON entries(approval_status)")

        # Migration: expand user_roles CHECK to include 'approver'
        conn.execute("SAVEPOINT check_approver")
        try:
            conn.execute("INSERT OR IGNORE INTO user_roles (user_id, role) VALUES ('__mig_test__', 'approver')")
            conn.execute("DELETE FROM user_roles WHERE user_id = '__mig_test__' AND role = 'approver'")
        except Exception:
            conn.execute("ROLLBACK TO check_approver")
            conn.execute("""
                CREATE TABLE user_roles_new (
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('manager','timekeeper','collaborator','approver')),
                    PRIMARY KEY (user_id, role),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            """)
            conn.execute("INSERT INTO user_roles_new SELECT * FROM user_roles")
            conn.execute("DROP TABLE user_roles")
            conn.execute("ALTER TABLE user_roles_new RENAME TO user_roles")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role)")
        conn.execute("RELEASE check_approver")

        # Seed categories
        for cat in CATEGORY_SEED:
            conn.execute(
                "INSERT OR IGNORE INTO categories (name) VALUES (?)",
                (cat,)
            )


# --- Settings ---

def get_setting(key, default=None):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            cast = SETTING_TYPE_MAP.get(key)
            if cast:
                return cast(row['value'])
            return row['value']
    if default is not None:
        return default
    return SETTING_DEFAULTS.get(key)


def set_setting(key, value):
    with _connect() as conn:
        conn.execute("""
            INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
        """, (key, str(value)))


def list_settings():
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value, updated_at FROM settings ORDER BY key")
        return [dict(r) for r in cursor.fetchall()]


def has_managers():
    """Check if any user has the manager role. Used for bootstrap."""
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as c FROM user_roles WHERE role = 'manager'")
        return cursor.fetchone()['c'] > 0


# --- Categories ---

def get_categories(active_only=True):
    with _connect() as conn:
        cursor = conn.cursor()
        query = "SELECT name FROM categories"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY name"
        cursor.execute(query)
        return [r['name'] for r in cursor.fetchall()]


def add_category(name):
    with _connect() as conn:
        conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))


def deactivate_category(name):
    with _connect() as conn:
        conn.execute("UPDATE categories SET active = 0 WHERE name = ?", (name,))


# --- Multi-user helpers ---

def is_multiuser():
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as c FROM users WHERE active = 1")
        return cursor.fetchone()['c'] > 0


# --- Users CRUD ---

def save_user(user_id, name):
    with _connect() as conn:
        conn.execute("""
            INSERT INTO users (user_id, name) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET name = excluded.name, active = 1
        """, (user_id, name))


def get_user(user_id):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_users():
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users ORDER BY name ASC")
        return [dict(r) for r in cursor.fetchall()]


def deactivate_user(user_id):
    with _connect() as conn:
        conn.execute("UPDATE users SET active = 0 WHERE user_id = ?", (user_id,))


# --- Roles ---

def add_role(user_id, role):
    with _connect() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO user_roles (user_id, role) VALUES (?, ?)
        """, (user_id, role))


def remove_role(user_id, role):
    with _connect() as conn:
        conn.execute("""
            DELETE FROM user_roles WHERE user_id = ? AND role = ?
        """, (user_id, role))


def get_roles(user_id):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM user_roles WHERE user_id = ?", (user_id,))
        return {r['role'] for r in cursor.fetchall()}


# --- Assignments ---

def add_assignment(user_id, client_id, project_id=None):
    with _connect() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO assignments (user_id, client_id, project_id)
            VALUES (?, ?, ?)
        """, (user_id, client_id, project_id))


def remove_assignment(user_id, client_id, project_id=None):
    with _connect() as conn:
        if project_id:
            conn.execute("""
                DELETE FROM assignments
                WHERE user_id = ? AND client_id = ? AND project_id = ?
            """, (user_id, client_id, project_id))
        else:
            conn.execute("""
                DELETE FROM assignments
                WHERE user_id = ? AND client_id = ? AND project_id IS NULL
            """, (user_id, client_id))


def get_assignments(user_id=None):
    with _connect() as conn:
        cursor = conn.cursor()
        if user_id:
            cursor.execute("""
                SELECT a.*, c.name as client_name, p.name as project_name
                FROM assignments a
                LEFT JOIN clients c ON a.client_id = c.id
                LEFT JOIN projects p ON a.project_id = p.id
                WHERE a.user_id = ?
                ORDER BY c.name, p.name
            """, (user_id,))
        else:
            cursor.execute("""
                SELECT a.*, u.name as user_name, c.name as client_name, p.name as project_name
                FROM assignments a
                JOIN users u ON a.user_id = u.user_id
                LEFT JOIN clients c ON a.client_id = c.id
                LEFT JOIN projects p ON a.project_id = p.id
                ORDER BY u.name, c.name, p.name
            """)
        return [dict(r) for r in cursor.fetchall()]


def has_assignment(user_id, client_id, project_id=None):
    with _connect() as conn:
        cursor = conn.cursor()
        # Check client-level wildcard (project_id IS NULL = all projects)
        cursor.execute("""
            SELECT id FROM assignments
            WHERE user_id = ? AND client_id = ? AND project_id IS NULL
        """, (user_id, client_id))
        if cursor.fetchone():
            return True
        # Check specific project
        if project_id:
            cursor.execute("""
                SELECT id FROM assignments
                WHERE user_id = ? AND client_id = ? AND project_id = ?
            """, (user_id, client_id, project_id))
            return cursor.fetchone() is not None
        return False


# --- FTS sync ---

def _sync_fts(conn, row_id, description, notes, tags, external_id=None):
    conn.execute("DELETE FROM entries_fts WHERE rowid = ?", (row_id,))
    conn.execute("""
        INSERT INTO entries_fts(rowid, description, notes, tags, external_id)
        VALUES (?, ?, ?, ?, ?)
    """, (row_id, description or '', notes or '', tags or '', external_id or ''))


def _sync_fts_from_row(conn, row_id):
    cursor = conn.cursor()
    cursor.execute("SELECT description, notes, tags, external_id FROM entries WHERE id = ?", (row_id,))
    row = cursor.fetchone()
    if row:
        _sync_fts(conn, row_id, row['description'], row['notes'], row['tags'],
                  row['external_id'])


# --- Timer (deprecated in multi-user) ---

def start_timer(description, project_id=None, client_id=None, category="other",
                billable=True, tags=None):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM active_timer WHERE id = 1")
        existing = cursor.fetchone()
        if existing:
            return None, dict(existing)

        now = dt.datetime.now().isoformat()
        cursor.execute("""
            INSERT OR REPLACE INTO active_timer (id, description, project_id, client_id,
                                                  category, billable, tags, started_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?)
        """, (description, project_id, client_id, category, 1 if billable else 0,
              tags, now))
        return now, None


def stop_timer(notes=None):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM active_timer WHERE id = 1")
        timer = cursor.fetchone()
        if not timer:
            return None

        timer = dict(timer)
        now = dt.datetime.now()
        started = dt.datetime.fromisoformat(timer['started_at'])
        duration = (now - started).total_seconds() / 60.0

        cursor.execute("""
            INSERT INTO entries (project_id, client_id, description, category,
                                started_at, ended_at, duration_minutes, billable,
                                rate, tags, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (timer['project_id'], timer['client_id'], timer['description'],
              timer['category'], timer['started_at'], now.isoformat(),
              round(duration, 1), timer['billable'],
              _resolve_rate(conn, timer['project_id'], timer['client_id']),
              timer['tags'], notes))

        entry_id = cursor.lastrowid
        _sync_fts(conn, entry_id, timer['description'], notes, timer['tags'])
        cursor.execute("DELETE FROM active_timer WHERE id = 1")

        return {
            'entry_id': entry_id,
            'description': timer['description'],
            'started_at': timer['started_at'],
            'ended_at': now.isoformat(),
            'duration_minutes': round(duration, 1),
        }


def get_active_timer():
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM active_timer WHERE id = 1")
        row = cursor.fetchone()
        if not row:
            return None
        timer = dict(row)
        now = dt.datetime.now()
        started = dt.datetime.fromisoformat(timer['started_at'])
        timer['elapsed_minutes'] = round((now - started).total_seconds() / 60.0, 1)
        return timer


def cancel_timer():
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM active_timer WHERE id = 1")
        timer = cursor.fetchone()
        if not timer:
            return None
        timer = dict(timer)
        cursor.execute("DELETE FROM active_timer WHERE id = 1")
        return timer


# --- Entries CRUD ---

def save_entry(description, duration_minutes, project_id=None, client_id=None,
               category="other", billable=True, tags=None, notes=None,
               entry_date=None, rate=None, user_id=None, external_id=None):
    if not client_id:
        raise ValueError("client_id is required")
    if not project_id:
        raise ValueError("project_id is required")
    if not entry_date:
        entry_date = dt.date.today().isoformat()

    started_at = f"{entry_date}T09:00:00"

    with _connect() as conn:
        if rate is None:
            rate = _resolve_rate(conn, project_id, client_id)

        cursor = conn.cursor()
        approval_status = 'pending' if get_setting('approval_required') else 'approved'
        cursor.execute("""
            INSERT INTO entries (project_id, client_id, description, category,
                                started_at, duration_minutes, billable, rate,
                                tags, notes, user_id, external_id, approval_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, client_id, description, category, started_at,
              duration_minutes, 1 if billable else 0, rate, tags, notes,
              user_id, external_id, approval_status))
        row_id = cursor.lastrowid
        _sync_fts(conn, row_id, description, notes, tags, external_id)
        return row_id


def get_entry(entry_id):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT e.*, p.name as project_name, c.name as client_name
            FROM entries e
            LEFT JOIN projects p ON e.project_id = p.id
            LEFT JOIN clients c ON e.client_id = c.id
            WHERE e.id = ?
        """, (entry_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_entry_by_external_id(external_id):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT e.*, p.name as project_name, c.name as client_name
            FROM entries e
            LEFT JOIN projects p ON e.project_id = p.id
            LEFT JOIN clients c ON e.client_id = c.id
            WHERE e.external_id = ?
            ORDER BY e.started_at DESC
        """, (external_id,))
        return [dict(r) for r in cursor.fetchall()]


def list_entries(project_id=None, client_id=None, category=None,
                 billable=None, date_from=None, date_to=None, limit=50,
                 user_id=None, external_id=None):
    with _connect() as conn:
        query = """
            SELECT e.*, p.name as project_name, c.name as client_name
            FROM entries e
            LEFT JOIN projects p ON e.project_id = p.id
            LEFT JOIN clients c ON e.client_id = c.id
            WHERE 1=1
        """
        params = []

        if project_id:
            query += " AND e.project_id = ?"
            params.append(project_id)
        if client_id:
            query += " AND e.client_id = ?"
            params.append(client_id)
        if category:
            query += " AND e.category = ?"
            params.append(category)
        if billable is not None:
            query += " AND e.billable = ?"
            params.append(1 if billable else 0)
        if date_from:
            query += " AND e.started_at >= ?"
            params.append(date_from)
        if date_to:
            query += " AND e.started_at <= ?"
            params.append(date_to + "T23:59:59")
        if user_id:
            query += " AND e.user_id = ?"
            params.append(user_id)
        if external_id:
            query += " AND e.external_id = ?"
            params.append(external_id)

        query += " ORDER BY e.started_at DESC LIMIT ?"
        params.append(limit)

        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def update_entry(entry_id, **kwargs):
    allowed = {
        'description', 'category', 'duration_minutes', 'billable',
        'rate', 'tags', 'notes', 'project_id', 'client_id',
        'user_id', 'external_id',
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False

    if 'client_id' in fields and fields['client_id'] is None:
        raise ValueError("client_id cannot be null")
    if 'project_id' in fields and fields['project_id'] is None:
        raise ValueError("project_id cannot be null")

    if 'billable' in fields:
        fields['billable'] = 1 if fields['billable'] else 0

    fields['updated_at'] = dt.datetime.now().isoformat()

    # Reset approval_status to pending when editing an approved/rejected entry
    fields['approval_status'] = 'pending'

    set_clause = ', '.join([f"{k} = ?" for k in fields.keys()])
    values = list(fields.values()) + [entry_id]

    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE entries SET {set_clause} WHERE id = ?", values)
        if cursor.rowcount > 0:
            _sync_fts_from_row(conn, entry_id)
            return True
        return False


def delete_entry(entry_id):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM entries_fts WHERE rowid = ?", (entry_id,))
        cursor.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        return cursor.rowcount > 0


def search_entries(query_text, user_id=None):
    with _connect() as conn:
        cursor = conn.cursor()
        try:
            base_query = """
                SELECT e.*, p.name as project_name, c.name as client_name
                FROM entries_fts fts
                JOIN entries e ON e.id = fts.rowid
                LEFT JOIN projects p ON e.project_id = p.id
                LEFT JOIN clients c ON e.client_id = c.id
                WHERE entries_fts MATCH ?
            """
            params = [query_text]
            if user_id:
                base_query += " AND e.user_id = ?"
                params.append(user_id)
            base_query += " ORDER BY fts.rank LIMIT 50"
            cursor.execute(base_query, params)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            like_q = f"%{query_text}%"
            base_query = """
                SELECT e.*, p.name as project_name, c.name as client_name
                FROM entries e
                LEFT JOIN projects p ON e.project_id = p.id
                LEFT JOIN clients c ON e.client_id = c.id
                WHERE (e.description LIKE ? OR e.notes LIKE ? OR e.tags LIKE ? OR e.external_id LIKE ?)
            """
            params = [like_q, like_q, like_q, like_q]
            if user_id:
                base_query += " AND e.user_id = ?"
                params.append(user_id)
            base_query += " ORDER BY e.started_at DESC LIMIT 50"
            cursor.execute(base_query, params)
            return [dict(row) for row in cursor.fetchall()]


# --- Approvals ---

def record_approval(entry_id, approver_id, action, reason=None):
    """Record an approval or rejection. Updates entry approval_status."""
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO entry_approvals (entry_id, approver_id, action, reason)
            VALUES (?, ?, ?, ?)
        """, (entry_id, approver_id, action, reason))
        conn.execute("""
            UPDATE entries SET approval_status = ? WHERE id = ?
        """, (action, entry_id))
        return cursor.lastrowid


def get_pending_entries(approver_id, client_id=None, project_id=None,
                        for_user=None, date_from=None, date_to=None):
    """Get pending entries the approver can approve.
    Joins assignments to scope by client/project.
    Excludes approver's own entries."""
    with _connect() as conn:
        cursor = conn.cursor()
        query = """
            SELECT e.*, p.name as project_name, c.name as client_name
            FROM entries e
            JOIN assignments a ON e.client_id = a.client_id
                AND (a.project_id IS NULL OR e.project_id = a.project_id)
            LEFT JOIN projects p ON e.project_id = p.id
            LEFT JOIN clients c ON e.client_id = c.id
            WHERE e.approval_status = 'pending'
                AND a.user_id = ?
                AND e.user_id != ?
        """
        params = [approver_id, approver_id]

        if client_id:
            query += " AND e.client_id = ?"
            params.append(client_id)
        if project_id:
            query += " AND e.project_id = ?"
            params.append(project_id)
        if for_user:
            query += " AND e.user_id = ?"
            params.append(for_user)
        if date_from:
            query += " AND e.started_at >= ?"
            params.append(f"{date_from}T00:00:00")
        if date_to:
            query += " AND e.started_at <= ?"
            params.append(f"{date_to}T23:59:59")

        query += " ORDER BY e.started_at ASC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_approval_history(entry_id):
    """Get full approval/rejection history for an entry."""
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ea.*, u.name as approver_name
            FROM entry_approvals ea
            LEFT JOIN users u ON ea.approver_id = u.user_id
            WHERE ea.entry_id = ?
            ORDER BY ea.approved_at DESC
        """, (entry_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_rejected_entries(user_id):
    """Get rejected entries for a user (collaborator view)."""
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT e.*, p.name as project_name, c.name as client_name
            FROM entries e
            LEFT JOIN projects p ON e.project_id = p.id
            LEFT JOIN clients c ON e.client_id = c.id
            WHERE e.user_id = ? AND e.approval_status = 'rejected'
            ORDER BY e.started_at DESC
        """, (user_id,))
        return [dict(row) for row in cursor.fetchall()]


# --- Clients ---

def save_client(name, rate=None, contact_email=None, notes=None):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO clients (name, rate, contact_email, notes)
            VALUES (?, ?, ?, ?)
        """, (name, rate, contact_email, notes))
        return cursor.lastrowid


def get_client(client_id):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def find_client_by_name(name):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM clients WHERE name LIKE ?", (f"%{name}%",))
        results = cursor.fetchall()
        return [dict(r) for r in results]


def list_clients():
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM clients ORDER BY name ASC")
        return [dict(row) for row in cursor.fetchall()]


def rename_client(client_id, new_name):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE clients SET name = ? WHERE id = ?", (new_name, client_id))
        return cursor.rowcount > 0


def deactivate_client(client_id):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE clients SET active = 0 WHERE id = ?", (client_id,))
        return cursor.rowcount > 0


def reactivate_client(client_id):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE clients SET active = 1 WHERE id = ?", (client_id,))
        return cursor.rowcount > 0


def is_client_active(client_id):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT active FROM clients WHERE id = ?", (client_id,))
        row = cursor.fetchone()
        return row is not None and row['active'] == 1


# --- Projects ---

def save_project(name, client_id=None, rate=None, budget_hours=None, notes=None):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO projects (name, client_id, rate, budget_hours, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (name, client_id, rate, budget_hours, notes))
        return cursor.lastrowid


def get_project(project_id):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*, c.name as client_name
            FROM projects p
            LEFT JOIN clients c ON p.client_id = c.id
            WHERE p.id = ?
        """, (project_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def find_project_by_name(name):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*, c.name as client_name
            FROM projects p
            LEFT JOIN clients c ON p.client_id = c.id
            WHERE p.name LIKE ?
        """, (f"%{name}%",))
        return [dict(r) for r in cursor.fetchall()]


def list_projects(active_only=True):
    with _connect() as conn:
        query = """
            SELECT p.*, c.name as client_name
            FROM projects p
            LEFT JOIN clients c ON p.client_id = c.id
        """
        if active_only:
            query += " WHERE p.active = 1"
        query += " ORDER BY p.name ASC"

        cursor = conn.cursor()
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]


def deactivate_project(project_id):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE projects SET active = 0 WHERE id = ?", (project_id,))
        return cursor.rowcount > 0


def reactivate_project(project_id):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE projects SET active = 1 WHERE id = ?", (project_id,))
        return cursor.rowcount > 0


def is_project_active(project_id):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT active FROM projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        return row is not None and row['active'] == 1


# --- Rate resolution ---

def _resolve_rate(conn, project_id=None, client_id=None):
    if project_id:
        cursor = conn.cursor()
        cursor.execute("SELECT rate, client_id FROM projects WHERE id = ?", (project_id,))
        proj = cursor.fetchone()
        if proj and proj['rate']:
            return proj['rate']
        if proj and proj['client_id']:
            client_id = proj['client_id']

    if client_id:
        cursor = conn.cursor()
        cursor.execute("SELECT rate FROM clients WHERE id = ?", (client_id,))
        cl = cursor.fetchone()
        if cl and cl['rate']:
            return cl['rate']

    return get_setting('default_rate')


# --- Reporting ---

def _round_up(minutes):
    round_to = get_setting('round_to_minutes')
    if round_to <= 0:
        return minutes
    return math.ceil(minutes / round_to) * round_to


def get_summary(client_id=None, project_id=None, date_from=None, date_to=None,
                billable_only=False, round_up=False, user_id=None, team=False):
    filters = dict(
        client_id=client_id,
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
        billable=True if billable_only else None,
        limit=10000,
    )
    if not team and user_id:
        filters['user_id'] = user_id

    entries = list_entries(**filters)

    default_rate = get_setting('default_rate')
    currency_symbol = get_setting('currency_symbol')
    total_minutes = 0
    billable_minutes = 0
    total_amount = 0.0
    by_client = {}
    by_project = {}
    by_category = {}
    by_date = {}

    for e in entries:
        mins = e['duration_minutes'] or 0
        if round_up:
            mins = _round_up(mins)

        total_minutes += mins

        if e['billable']:
            billable_minutes += mins
            rate = e['rate'] or default_rate
            total_amount += (mins / 60.0) * rate

        client = e['client_name'] or "No client"
        by_client.setdefault(client, {'minutes': 0, 'amount': 0.0})
        by_client[client]['minutes'] += mins
        if e['billable']:
            by_client[client]['amount'] += (mins / 60.0) * (e['rate'] or default_rate)

        project = e['project_name'] or "No project"
        by_project.setdefault(project, {'minutes': 0, 'amount': 0.0})
        by_project[project]['minutes'] += mins
        if e['billable']:
            by_project[project]['amount'] += (mins / 60.0) * (e['rate'] or default_rate)

        cat = e['category'] or "other"
        by_category.setdefault(cat, 0)
        by_category[cat] += mins

        date_key = e['started_at'][:10] if e['started_at'] else "unknown"
        by_date.setdefault(date_key, 0)
        by_date[date_key] += mins

    return {
        'total_entries': len(entries),
        'total_minutes': total_minutes,
        'total_hours': round(total_minutes / 60.0, 2),
        'billable_minutes': billable_minutes,
        'billable_hours': round(billable_minutes / 60.0, 2),
        'total_amount': round(total_amount, 2),
        'by_client': by_client,
        'by_project': by_project,
        'by_category': by_category,
        'by_date': dict(sorted(by_date.items())),
    }


def get_stats(user_id=None, scope='own'):
    default_rate = get_setting('default_rate')

    with _connect() as conn:
        cursor = conn.cursor()

        user_filter = ""
        user_params = []
        if scope == 'own' and user_id:
            user_filter = " AND user_id = ?"
            user_params = [user_id]

        cursor.execute(f"SELECT COUNT(*) as c FROM entries WHERE 1=1{user_filter}", user_params)
        total_entries = cursor.fetchone()['c']

        cursor.execute("SELECT COUNT(*) as c FROM clients")
        total_clients = cursor.fetchone()['c']

        cursor.execute("SELECT COUNT(*) as c FROM projects WHERE active = 1")
        total_projects = cursor.fetchone()['c']

        cursor.execute(f"SELECT COALESCE(SUM(duration_minutes), 0) as t FROM entries WHERE 1=1{user_filter}", user_params)
        total_minutes = cursor.fetchone()['t']

        cursor.execute(f"SELECT COALESCE(SUM(duration_minutes), 0) as t FROM entries WHERE billable = 1{user_filter}", user_params)
        billable_minutes = cursor.fetchone()['t']

        cursor.execute(f"""
            SELECT COALESCE(SUM(duration_minutes / 60.0 * COALESCE(rate, ?)), 0) as t
            FROM entries WHERE billable = 1{user_filter}
        """, [default_rate] + user_params)
        total_revenue = cursor.fetchone()['t']

        cursor.execute(f"""
            SELECT category, COALESCE(SUM(duration_minutes), 0) as t
            FROM entries WHERE 1=1{user_filter}
            GROUP BY category ORDER BY t DESC
        """, user_params)
        by_category = {row['category']: row['t'] for row in cursor.fetchall()}

        cursor.execute(f"""
            SELECT c.name, COALESCE(SUM(e.duration_minutes), 0) as t
            FROM entries e
            JOIN clients c ON e.client_id = c.id
            WHERE 1=1{user_filter.replace('user_id', 'e.user_id')}
            GROUP BY c.name ORDER BY t DESC LIMIT 10
        """, user_params)
        top_clients = {row['name']: row['t'] for row in cursor.fetchall()}

        cursor.execute(f"""
            SELECT strftime('%Y-%m', started_at) as month, COALESCE(SUM(duration_minutes), 0) as t
            FROM entries WHERE started_at IS NOT NULL{user_filter}
            GROUP BY month ORDER BY month DESC LIMIT 12
        """, user_params)
        by_month = {row['month']: row['t'] for row in cursor.fetchall()}

        return {
            'total_entries': total_entries,
            'total_clients': total_clients,
            'total_projects': total_projects,
            'total_minutes': total_minutes,
            'total_hours': round(total_minutes / 60.0, 2),
            'billable_minutes': billable_minutes,
            'billable_hours': round(billable_minutes / 60.0, 2),
            'total_revenue': round(total_revenue, 2),
            'by_category': by_category,
            'top_clients': top_clients,
            'by_month': by_month,
        }


# --- Export ---

def export_entries(format_type='json', user_id=None, **filters):
    if user_id:
        filters['user_id'] = user_id
    entries = list_entries(limit=10000, **filters)
    if format_type == 'json':
        return json.dumps(entries, indent=2, default=str)
    elif format_type == 'csv':
        import csv
        import io
        if not entries:
            return ""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=entries[0].keys())
        writer.writeheader()
        writer.writerows(entries)
        return output.getvalue()
    return ""
