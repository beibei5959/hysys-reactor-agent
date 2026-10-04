"""单机任务存储：短事务、租约所有权与原子阶段快照。"""

import hashlib
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


class TaskConflict(RuntimeError):
    pass


def encode(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        default=lambda obj: obj.model_dump(),
    )


class TaskStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, digest TEXT NOT NULL, request TEXT NOT NULL,
                    state TEXT NOT NULL, status TEXT NOT NULL, stage TEXT,
                    owner TEXT, lease_until REAL, updated REAL NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0, contract INTEGER NOT NULL DEFAULT 1,
                    in_flight INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    attempt INTEGER NOT NULL, stage TEXT, status TEXT NOT NULL,
                    created REAL NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def create(self, request, state, task_id=None):
        task_id = task_id or uuid4().hex
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", task_id):
            raise ValueError("任务 ID 只能包含字母、数字、下划线和连字符，最长80字符")
        payload = encode(request)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with self.transaction() as db:
            row = db.execute("SELECT digest FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row:
                if row["digest"] != digest:
                    raise TaskConflict("同一任务 ID 不能提交不同输入；修改参数请创建新任务")
            else:
                db.execute(
                    "INSERT INTO tasks(id,digest,request,state,status,stage,updated) VALUES(?,?,?,?,?,?,?)",
                    (
                        task_id,
                        digest,
                        payload,
                        encode(state),
                        "pending",
                        "parse_reaction",
                        time.time(),
                    ),
                )
        return task_id

    def get(self, task_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise TaskConflict("任务不存在")
        result = dict(row)
        for key in ("request", "state"):
            result[key] = json.loads(result[key])
        return result

    def claim(self, task_id, lease_seconds):
        token = uuid4().hex
        unknown = False
        with self.transaction() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None or row["contract"] != 1:
                raise TaskConflict("任务不存在或任务格式版本不兼容")
            if row["status"] in {"completed", "needs_input", "failed"}:
                return None
            if row["status"] == "outcome_unknown":
                raise TaskConflict("执行结果待核对，禁止自动重放模拟操作")
            # 取一次时间戳用于本次事务内的所有判断和写入，避免 time.time() 跨调用漂移。
            now = time.time()
            if row["owner"] and row["lease_until"] > now:
                raise TaskConflict("任务正在被另一执行进程处理")
            # 从 run_hysys 中断时无法知道外部操作是否已经发生。
            if row["owner"] and row["stage"] == "run_hysys" and row["in_flight"]:
                db.execute(
                    "UPDATE tasks SET status='outcome_unknown',owner=NULL,lease_until=NULL,updated=? WHERE id=?",
                    (now, task_id),
                )
                unknown = True
            else:
                db.execute(
                    "UPDATE tasks SET status='running',owner=?,lease_until=?,attempt=attempt+1,updated=? WHERE id=?",
                    (token, now + lease_seconds, now, task_id),
                )
        if unknown:
            raise TaskConflict("模拟阶段中断，已标记为执行结果待核对；禁止自动重跑")
        return token

    def heartbeat(self, task_id, token, lease_seconds):
        now = time.time()
        with self.connect() as db:
            changed = db.execute(
                "UPDATE tasks SET lease_until=? WHERE id=? AND owner=? AND lease_until>?",
                (now + lease_seconds, task_id, token, now),
            ).rowcount
        if changed != 1:
            raise TaskConflict("任务执行权已失效")

    def retry_explanation(self, task_id):
        with self.transaction() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise TaskConflict("任务不存在")
            state = json.loads(row["state"])
            if row["status"] != "completed" or state.get("explanation_status") != "degraded":
                raise TaskConflict("仅可补做已完成计算但解释失败的任务")
            db.execute(
                "UPDATE tasks SET status='pending',stage='explain_result',updated=? WHERE id=?",
                (time.time(), task_id),
            )

    def save(self, task_id, token, state, stage, status="running", release=False, in_flight=False):
        now = time.time()
        with self.transaction() as db:
            changed = db.execute(
                """UPDATE tasks SET state=?,stage=?,status=?,updated=?,in_flight=?,
                owner=CASE WHEN ? THEN NULL ELSE owner END,
                lease_until=CASE WHEN ? THEN NULL ELSE lease_until END
                WHERE id=? AND owner=? AND lease_until>?""",
                (
                    encode(state),
                    stage,
                    status,
                    now,
                    in_flight,
                    release,
                    release,
                    task_id,
                    token,
                    now,
                ),
            ).rowcount
            if changed != 1:
                raise TaskConflict("任务执行权已失效；旧进程不能提交结果")
            db.execute(
                "INSERT INTO events(task_id,attempt,stage,status,created) SELECT id,attempt,?,?,? FROM tasks WHERE id=?",
                (stage, status, now, task_id),
            )

    def sweep_expired(self, task_id):
        """检查指定任务的 lease，若已过期则回写派生状态；返回是否发生过回收。"""
        now = time.time()
        with self.transaction() as db:
            return (
                db.execute(
                    """UPDATE tasks SET status=CASE
                            WHEN stage='run_hysys' AND in_flight=1 THEN 'outcome_unknown'
                            ELSE 'interrupted'
                        END, owner=NULL, lease_until=NULL, updated=?
                    WHERE id=? AND status='running' AND lease_until IS NOT NULL AND lease_until<?""",
                    (now, task_id, now),
                ).rowcount
                > 0
            )

    def purge(self, days):
        if days < 1:
            raise ValueError("保留时间至少为1天")
        cutoff = time.time() - days * 86400
        with self.transaction() as db:
            deleted = db.execute(
                "DELETE FROM tasks WHERE status IN ('completed','failed') AND owner IS NULL AND updated<?",
                (cutoff,),
            ).rowcount
            # 同时清理因任务被保留而级联未删的孤立 events（例如长期停留在 pending/needs_input 的任务）。
            db.execute(
                "DELETE FROM events WHERE task_id NOT IN (SELECT id FROM tasks)"
            )
            return deleted
