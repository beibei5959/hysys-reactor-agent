"""管理员发放账号、服务端会话与任务访问记录。"""

import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()


class Accounts:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    salt TEXT NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    csrf TEXT NOT NULL, expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS access (
                    task_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    created REAL NOT NULL, kind TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS login_attempts (
                    address TEXT NOT NULL, created REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_login_attempts_lookup
                    ON login_attempts(address, created);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            with db:
                yield db
        finally:
            db.close()

    def create_user(self, username, password, role="user"):
        if not username.strip() or len(username) > 64 or not 12 <= len(password) <= 256:
            raise ValueError("账号不能为空；密码长度须为12至256字符")
        salt = secrets.token_hex(16)
        with self.connect() as db:
            db.execute(
                "INSERT INTO users VALUES(?,?,?,?,?)",
                (
                    secrets.token_hex(16),
                    username.strip(),
                    salt,
                    password_hash(password, salt),
                    role,
                ),
            )

    def login(self, username, password, address, session_max_age=28800):
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # 索引 idx_login_attempts_lookup(address, created) 让该 DELETE 与后续 COUNT 都走覆盖索引。
            db.execute("DELETE FROM login_attempts WHERE created<?", (now - 300,))
            count = db.execute(
                "SELECT COUNT(*) FROM login_attempts WHERE address=?", (address,)
            ).fetchone()[0]
            if count >= 10:
                return None, "limited"
            attempt_id = db.execute(
                "INSERT INTO login_attempts VALUES(?,?)", (address, now)
            ).lastrowid
            row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        digest = password_hash(password, row["salt"] if row else "00" * 16)
        if row is None or not hmac.compare_digest(digest, row["password"]):
            return None, "invalid"
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("DELETE FROM login_attempts WHERE rowid=?", (attempt_id,))
            db.execute("DELETE FROM sessions WHERE expires<?", (now,))
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?,?)",
                (
                    hashlib.sha256(token.encode()).hexdigest(),
                    row["id"],
                    csrf,
                    now + session_max_age,
                ),
            )
        return {
            "token": token,
            "csrf": csrf,
            "user": {k: row[k] for k in ("id", "username", "role")},
        }, None

    def session(self, token):
        with self.connect() as db:
            row = db.execute(
                """SELECT users.id,username,role,csrf FROM sessions
                JOIN users ON users.id=sessions.user_id WHERE token=? AND expires>?""",
                (hashlib.sha256(token.encode()).hexdigest(), time.time()),
            ).fetchone()
        return dict(row) if row else None

    def logout(self, token):
        with self.connect() as db:
            db.execute(
                "DELETE FROM sessions WHERE token=?", (hashlib.sha256(token.encode()).hexdigest(),)
            )
