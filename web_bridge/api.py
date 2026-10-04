"""单机 Web 服务：认证、任务归属、异步调度与静态页面。"""

import hashlib
import hmac
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from config.settings import Settings
from src.agent.graph import initial_state, next_stage
from src.agent.llm import JsonLLM
from src.agent.nodes.explain_result import make_explain_node
from src.agent.nodes.parse_reaction import make_parse_node
from src.agent.nodes.select_reactor import select_reactor
from src.agent.nodes.validate_input import validate_input
from src.hysys.mock_controller import MockHysysController
from src.models.reaction import ReactionInfo
from src.runtime.service import TaskService
from src.runtime.store import TaskConflict, TaskStore
from src.runtime.telemetry import configure_logging, emit, failure, task_context
from src.tools.hysys_tools import make_hysys_runner
from web_bridge.security import Accounts

ROOT = Path(__file__).resolve().parents[1]


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=20000)
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    reaction_info: dict | None = None
    simulation_inputs: dict = Field(default_factory=dict)


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reaction_info: dict
    simulation_inputs: dict
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")


def create_app(data_dir=None, *, llm_factory=None):
    directory = Path(data_dir or os.environ.get("HYSYS_WEB_DATA", ROOT / "var/web"))
    accounts = Accounts(directory / "accounts.sqlite3")
    store = TaskStore(directory / "tasks.sqlite3")
    cfg = Settings.from_env()
    llm = llm_factory() if llm_factory else JsonLLM(cfg)
    runner = make_hysys_runner(MockHysysController)
    pool = ThreadPoolExecutor(max_workers=cfg.web_worker_threads, thread_name_prefix="web-task")
    lock = threading.Lock()
    scheduled = set()
    secure_cookie = os.environ.get("HYSYS_WEB_SECURE_COOKIE", "0") == "1"
    origins = set(
        os.environ.get(
            "HYSYS_WEB_ORIGINS",
            "http://127.0.0.1:8765,http://localhost:8765,http://127.0.0.1:5173,http://localhost:5173",
        ).split(",")
    )

    @asynccontextmanager
    async def lifespan(app):
        configure_logging(directory / "events.jsonl")
        yield
        pool.shutdown(wait=True, cancel_futures=False)

    app = FastAPI(title="反应工程工作台接口", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.accounts, app.state.store = accounts, store

    @app.middleware("http")
    async def protection(request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("origin") not in origins:
                return JSONResponse({"detail": "请求来源不受信任"}, status_code=403)
            length = request.headers.get("content-length")
            if length and (not length.isdigit() or int(length) > cfg.web_request_max_bytes):
                return JSONResponse({"detail": "请求内容过大"}, status_code=413)
            body = await request.body()
            if len(body) > cfg.web_request_max_bytes:
                return JSONResponse({"detail": "请求内容过大"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(TaskConflict)
    async def conflict(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse({"detail": "请求字段格式或范围不正确，请检查输入"}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        failure("web_request_failed", exc)
        return JSONResponse(
            {"detail": "服务处理失败，请稍后重试或联系管理员检查日志"}, status_code=500
        )

    def authenticated(request: Request):
        session = accounts.session(request.cookies.get("hysys_session", ""))
        if not session:
            raise HTTPException(401, "登录已过期，请重新登录")
        if request.method not in {"GET", "HEAD"} and not hmac.compare_digest(
            request.headers.get("x-csrf-token", ""), session["csrf"]
        ):
            raise HTTPException(403, "会话校验失败，请刷新页面")
        return session

    def access(task_id, user):
        with accounts.connect() as db:
            row = db.execute("SELECT * FROM access WHERE task_id=?", (task_id,)).fetchone()
        if not row or (row["user_id"] != user["id"] and user["role"] != "admin"):
            raise HTTPException(404, "任务不存在")
        return dict(row)

    def public_task(task_id, user):
        meta = access(task_id, user)
        # 先看穿过期 lease：把"视觉上的 terminal"状态真正写回 DB，让 resume 与 GET 看到一致结果。
        store.sweep_expired(task_id)
        row = store.get(task_id)
        with store.connect() as db:
            ancestry = db.execute(
                """WITH RECURSIVE lineage(id, parent_id, depth) AS (
                SELECT id,json_extract(request,'$.parent_id'),0 FROM tasks WHERE id=?
                UNION ALL
                SELECT t.id,json_extract(t.request,'$.parent_id'),l.depth+1
                FROM tasks t JOIN lineage l ON t.id=l.parent_id
            ) SELECT id,depth FROM lineage ORDER BY depth DESC LIMIT 1""",
                (task_id,),
            ).fetchone()
        return {
            "id": task_id,
            "title": row["request"]["user_query"][:80],
            "status": row["status"],
            "stage": row["stage"],
            "created": meta["created"],
            "updated": row["updated"],
            "owner": meta["user_id"],
            "parent_id": row["request"].get("parent_id"),
            "root_id": ancestry["id"],
            "revision": ancestry["depth"],
            "state": row["state"],
        }

    def analyze(task_id):
        token = store.claim(task_id, cfg.task_timeout_seconds + 60)
        if not token:
            return
        row = store.get(task_id)
        request = row["request"]
        state = initial_state(
            request["user_query"], request["reaction_info"], request["simulation_inputs"]
        )
        engine = llm if request["reaction_info"] is None else None
        deadline = time.monotonic() + cfg.task_timeout_seconds

        try:
            if engine:
                engine.begin(deadline, [])
            # 预分析复用同一组纯分析节点；完整运行仍交给原有五节点 LangGraph。
            # current_stage 用于异常时把真实的"即将执行 / 正在执行"节点写回 DB，
            # 避免恢复时从头重跑已完成节点（原先硬编码为 parse_reaction）。
            current_stage = "parse_reaction"
            for name, node in [
                ("parse_reaction", make_parse_node(engine)),
                ("select_reactor", select_reactor),
                ("validate_input", validate_input),
            ]:
                current_stage = name
                if time.monotonic() >= deadline:
                    raise TimeoutError("分析时限已用尽")
                store.save(task_id, token, state, name)
                started = time.monotonic()
                emit("node_started", node=name)
                state.update(node(state))
                store.save(task_id, token, state, next_stage(name, state))
                emit(
                    "node_completed",
                    node=name,
                    duration_ms=round((time.monotonic() - started) * 1000),
                )
                if state.get("error"):
                    break
            state.update(make_explain_node(None)(state))
            status = (
                "failed"
                if state.get("error")
                else "awaiting_confirmation"
                if state["validation_passed"]
                else "needs_input"
            )
            store.save(
                task_id,
                token,
                state,
                "run_hysys" if status == "awaiting_confirmation" else None,
                status,
                release=True,
            )
        except Exception:
            store.save(task_id, token, state, current_stage, "interrupted", release=True)
            raise

    def worker(task_id, kind):
        context = task_context.set({"task_id": task_id})
        try:
            if kind == "analysis":
                analyze(task_id)
            else:
                service = TaskService(
                    store,
                    runner,
                    llm
                    if kind == "explain" or store.get(task_id)["request"].get("online")
                    else None,
                    max_retries=cfg.max_retries,
                    deadline_seconds=cfg.task_timeout_seconds,
                )
                service.execute(task_id)
        except Exception as exc:
            failure("web_task_failed", exc)
        finally:
            task_context.reset(context)
            with lock:
                scheduled.discard(task_id)

    def enqueue(task_id, kind):
        with lock:
            if task_id in scheduled:
                return
            if len(scheduled) >= cfg.web_queue_capacity:
                raise HTTPException(503, "任务队列已满，请稍后重试")
            scheduled.add(task_id)
            try:
                pool.submit(worker, task_id, kind)
            except Exception:
                scheduled.discard(task_id)
                raise

    def submit(user, payload, kind, parent_id=None):
        task_id = hashlib.sha256(f"{user['id']}:{payload.idempotency_key}".encode()).hexdigest()
        request = {
            "user_query": payload.query,
            "reaction_info": payload.reaction_info,
            "simulation_inputs": payload.simulation_inputs,
            "parent_id": parent_id,
            "web_kind": kind,
            "online": store.get(parent_id)["request"].get("online", False)
            if parent_id
            else payload.reaction_info is None,
        }
        state = initial_state(payload.query, payload.reaction_info, payload.simulation_inputs)
        if parent_id:
            state["llm_trace"] = store.get(parent_id)["state"].get("llm_trace", [])
        store.create(
            request,
            state,
            task_id,
        )
        with accounts.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO access VALUES(?,?,?,?)",
                (task_id, user["id"], time.time(), kind),
            )
        if store.get(task_id)["status"] == "pending":
            enqueue(task_id, kind)
        return public_task(task_id, user)

    @app.post("/api/login")
    def login(payload: LoginInput, request: Request, response: Response):
        result, error = accounts.login(
            payload.username,
            payload.password,
            request.client.host if request.client else "local",
            session_max_age=cfg.web_session_max_age,
        )
        if error:
            raise HTTPException(
                429 if error == "limited" else 401,
                "登录尝试过多，请5分钟后重试" if error == "limited" else "账号或密码不正确",
            )
        response.set_cookie(
            "hysys_session",
            result["token"],
            httponly=True,
            secure=secure_cookie,
            samesite="strict",
            max_age=cfg.web_session_max_age,
            path="/",
        )
        return {"user": result["user"], "csrf": result["csrf"]}

    @app.get("/api/session")
    def session(user=Depends(authenticated)):
        return {"user": {k: user[k] for k in ("id", "username", "role")}, "csrf": user["csrf"]}

    @app.post("/api/logout")
    def logout(request: Request, response: Response, user=Depends(authenticated)):
        accounts.logout(request.cookies.get("hysys_session", ""))
        response.delete_cookie("hysys_session", path="/")
        return {"ok": True}

    @app.get("/api/examples")
    def examples(user=Depends(authenticated)):
        labels = [
            ("equilibrium", "可逆反应 · 平衡控制", "Equilibrium / 平衡反应器"),
            ("conversion", "明确给定转化率", "Conversion / 转化反应器"),
            ("gibbs", "复杂体系 · 路径未知", "Gibbs / 吉布斯反应器"),
        ]
        return [
            {
                **json.loads((ROOT / "examples" / f"{name}.json").read_text(encoding="utf-8")),
                "id": name,
                "title": title,
                "subtitle": subtitle,
            }
            for name, title, subtitle in labels
        ]

    @app.get("/api/tasks")
    def tasks(user=Depends(authenticated)):
        with accounts.connect() as db:
            rows = db.execute(
                "SELECT task_id FROM access "
                + ("" if user["role"] == "admin" else "WHERE user_id=? ")
                + "ORDER BY created DESC LIMIT ?",
                (() if user["role"] == "admin" else (user["id"],)) + (cfg.web_task_list_limit,),
            ).fetchall()
        return [public_task(row["task_id"], user) for row in rows]

    @app.get("/api/tasks/{task_id}")
    def task(task_id: str, user=Depends(authenticated)):
        return public_task(task_id, user)

    @app.get("/api/task-history")
    def history(
        q: str = Query("", max_length=200),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        user=Depends(authenticated),
    ):
        with accounts.connect() as db:
            db.execute("ATTACH DATABASE ? AS task_data", (str(store.path),))
            where = "WHERE (?='admin' OR a.user_id=?) AND (instr(lower(json_extract(t.request,'$.user_query')),lower(?))>0 OR instr(t.id,lower(?))>0)"
            params = (user["role"], user["id"], q.strip(), q.strip())
            source = " FROM access a JOIN task_data.tasks t ON t.id=a.task_id "
            total = db.execute("SELECT COUNT(*)" + source + where, params).fetchone()[0]
            rows = db.execute(
                "SELECT t.id"
                + source
                + where
                + " ORDER BY a.created DESC,t.id DESC LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "items": [public_task(row["id"], user) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @app.post("/api/selection-preview")
    def preview(info: ReactionInfo, user=Depends(authenticated)):
        # 只读取同一套工程规则，不调用模型、创建任务或执行模拟。
        return select_reactor({"reaction_info": info})

    @app.post("/api/tasks", status_code=202)
    def new_task(payload: TaskInput, user=Depends(authenticated)):
        if not payload.query.strip():
            raise HTTPException(422, "请输入反应描述")
        return submit(user, payload, "analysis")

    @app.post("/api/tasks/{task_id}/run", status_code=202)
    def run_task(task_id: str, payload: RunInput, user=Depends(authenticated)):
        parent = public_task(task_id, user)
        if parent["status"] not in {"awaiting_confirmation", "needs_input", "completed", "failed"}:
            raise HTTPException(409, "当前任务不能修改参数或重新提交")
        return submit(
            user,
            TaskInput(query=parent["state"]["user_query"], **payload.model_dump()),
            "run",
            task_id,
        )

    @app.post("/api/tasks/{task_id}/{action}", status_code=202)
    def resume(task_id: str, action: Literal["resume", "explain"], user=Depends(authenticated)):
        meta = access(task_id, user)
        row = public_task(task_id, user)
        if action == "explain":
            store.retry_explanation(task_id)
            enqueue(task_id, "explain")
        else:
            if row["status"] not in {"interrupted", "pending"}:
                raise HTTPException(409, "当前任务不能恢复；结果待核对的任务禁止重放")
            enqueue(task_id, meta["kind"])
        return public_task(task_id, user)

    dist = ROOT / "web/dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app


if __name__ == "__main__":
    import uvicorn

    # 云平台（如 Railway）注入 PORT 并要求监听 0.0.0.0；本地默认行为不变。
    uvicorn.run(create_app(),
                host=os.environ.get("HYSYS_WEB_HOST", "127.0.0.1"),
                port=int(os.environ.get("PORT", "8765")),
                access_log=False)
