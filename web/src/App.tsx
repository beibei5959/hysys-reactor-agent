import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  ChevronRight,
  Download,
  FileText,
  FlaskConical,
  History,
  Info,
  LogOut,
  Menu,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import { api, ApiError } from "./api";
import Login, { Brand } from "./Login";
import Parameters from "./Parameters";
import { readable, currentStage } from "./presentation";
import type { Example, Task, User } from "./types";

const names: Record<string, string> = {
  Conversion: "转化反应器",
  Equilibrium: "平衡反应器",
  Gibbs: "吉布斯反应器",
};
const labels: Record<string, string> = {
  pending: "等待执行",
  running: "正在处理",
  awaiting_confirmation: "待确认参数",
  needs_input: "待补充参数",
  completed: "已完成",
  failed: "执行失败",
  interrupted: "执行已中断",
  outcome_unknown: "结果待核对",
};
const stages = [
  "parse_reaction",
  "select_reactor",
  "validate_input",
  "run_hysys",
  "explain_result",
];
const stageLabels = [
  "理解反应",
  "规则选型",
  "参数校验",
  "运行流程",
  "结果解释",
];
const active = (task: Task) => ["pending", "running"].includes(task.status);
const message = (error: unknown) =>
  error instanceof Error ? error.message : "操作未成功，请重试";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    api
      .session()
      .then((value) => {
        if (live) setUser(value);
      })
      .catch((e) => {
        if (live && !(e instanceof ApiError && e.status === 401))
          setError(message(e));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    const expired = () => {
      setUser(null);
      setError("会话已过期，请重新登录。");
    };
    window.addEventListener("session-expired", expired);
    return () => {
      live = false;
      window.removeEventListener("session-expired", expired);
    };
  }, []);
  if (loading)
    return (
      <div className="page-loading">
        <span className="spinner" /> 正在连接工作空间
      </div>
    );
  return user ? (
    <Workspace
      user={user}
      onLogout={() => {
        setUser(null);
        setError("");
        window.location.hash = "";
      }}
    />
  ) : (
    <Login
      connectionError={error}
      onLogin={(value) => {
        setUser(value);
        setError("");
      }}
    />
  );
}

function Workspace({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [examples, setExamples] = useState<Example[]>([]);
  const [selected, setSelected] = useState(window.location.hash.slice(1));
  const [task, setTask] = useState<Task | null>(null);
  const [query, setQuery] = useState("");
  const [example, setExample] = useState<Example>();
  const [search, setSearch] = useState("");
  const [historyQuery, setHistoryQuery] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyTick, setHistoryTick] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [sidebar, setSidebar] = useState(false);
  const [about, setAbout] = useState(false);
  const requestKey = useRef({ signature: "", key: "" });
  const mounted = useRef(true);
  const aboutButton = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    let live = true;
    let fetching = false;
    setHistoryLoading(true);
    const refresh = async () => {
      if (fetching) return;
      fetching = true;
      try {
        const data = await api.history(historyQuery, page);
        if (live) {
          setTasks(data.items);
          setTotal(data.total);
          if (page > Math.max(1, Math.ceil(data.total / 20)))
            setPage(Math.max(1, Math.ceil(data.total / 20)));
        }
      } catch (e) {
        if (live) setError(message(e));
      } finally {
        fetching = false;
        if (live) setHistoryLoading(false);
      }
    };
    void refresh();
    const timer = window.setInterval(refresh, 4000);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [historyQuery, page, historyTick]);
  useEffect(() => {
    if (search === historyQuery) return;
    const timer = window.setTimeout(() => {
      setHistoryQuery(search);
      setPage(1);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search, historyQuery]);
  useEffect(() => {
    let live = true;
    api
      .examples()
      .then((data) => {
        if (live) setExamples(data);
      })
      .catch((e) => {
        if (live) setError(message(e));
      });
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    const change = () => setSelected(window.location.hash.slice(1));
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  useEffect(() => {
    let live = true;
    setTask(null);
    if (!selected) return;
    const refresh = async () => {
      try {
        const data = await api.task(selected);
        if (live) setTask(data);
      } catch (e) {
        if (live) setError(message(e));
      }
    };
    void refresh();
    const timer = window.setInterval(refresh, 1800);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [selected]);
  useEffect(() => {
    if (!about) return;
    closeButton.current?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setAbout(false);
      if (event.key === "Tab") {
        event.preventDefault();
        closeButton.current?.focus();
      }
    };
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("keydown", escape);
      aboutButton.current?.focus();
    };
  }, [about]);
  function choose(id: string) {
    setSelected(id);
    window.location.hash = id;
    setSidebar(false);
    setError("");
  }
  function fresh() {
    choose("");
    setQuery("");
    setExample(undefined);
    requestKey.current = { signature: "", key: "" };
  }
  function key(signature: string) {
    if (requestKey.current.signature !== signature)
      requestKey.current = { signature, key: crypto.randomUUID() };
    return requestKey.current.key;
  }
  async function action(work: () => Promise<Task>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await work();
      if (mounted.current) {
        choose(result.id);
        setTask(result);
        setHistoryTick((value) => value + 1);
      }
    } catch (e) {
      if (mounted.current) setError(message(e));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  async function logout() {
    setBusy(true);
    try {
      await api.logout();
      onLogout();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  const filtered = tasks;
  const state = task?.state;
  const ready =
    task &&
    ["awaiting_confirmation", "needs_input", "completed", "failed"].includes(
      task.status,
    ) &&
    !!state?.reaction_info;
  function download() {
    if (!task) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(task, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `hysys-${task.id.slice(0, 12)}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <div className="workspace">
      {sidebar && (
        <button
          className="sidebar-scrim"
          aria-label="关闭任务列表"
          onClick={() => setSidebar(false)}
        />
      )}
      <aside className={`sidebar ${sidebar ? "open" : ""}`}>
        <Brand compact />
        <button className="primary new-task" onClick={fresh}>
          <Plus size={18} /> 新建分析
        </button>
        <div className="nav-label">
          <History size={14} />{" "}
          {user.role === "admin" ? "全部任务" : "我的任务"} <span>{total}</span>
        </div>
        <div className="history-search">
          <Search size={15} />
          <input
            aria-label="搜索任务"
            placeholder="搜索反应或任务"
            maxLength={200}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <nav className="task-list" aria-label="历史任务">
          {historyLoading ? (
            <p className="history-empty">正在查询任务…</p>
          ) : filtered.length ? (
            filtered.map((item) => (
              <button
                key={item.id}
                className={`task-item ${selected === item.id ? "selected" : ""}`}
                onClick={() => choose(item.id)}
              >
                <FileText size={16} />
                <div>
                  <strong>{item.title}</strong>
                  <span className="revision-label">
                    {item.revision === 0 ? "原始分析" : `修订 ${item.revision}`}{" "}
                    · {item.root_id.slice(0, 8)}
                    {item.revision > 0 ? ` / ${item.id.slice(0, 6)}` : ""}
                  </span>
                  <span>
                    <i className={`status-dot ${item.status}`} />
                    {labels[item.status] ?? item.status} ·{" "}
                    {new Date(item.created * 1000).toLocaleDateString("zh-CN", {
                      month: "numeric",
                      day: "numeric",
                    })}
                  </span>
                </div>
              </button>
            ))
          ) : (
            <p className="history-empty">
              {search ? "没有匹配的任务" : "你的分析记录会保存在这里"}
            </p>
          )}
        </nav>
        <div className="history-pagination">
          <button
            disabled={page <= 1 || historyLoading}
            onClick={() => setPage((value) => value - 1)}
          >
            上一页
          </button>
          <span>
            {page} / {Math.max(1, Math.ceil(total / 20))}
          </span>
          <button
            disabled={page * 20 >= total || historyLoading}
            onClick={() => setPage((value) => value + 1)}
          >
            下一页
          </button>
        </div>
        <div className="sidebar-note">
          <ShieldCheck size={18} />
          <div>
            工程规则约束选型<small>每一个推荐，都保留判断依据</small>
          </div>
        </div>
        <div className="account">
          <span className="avatar">
            {user.username.slice(0, 1).toUpperCase()}
          </span>
          <div>
            <strong>{user.username}</strong>
            <small>{user.role === "admin" ? "管理员" : "工作空间成员"}</small>
          </div>
          <button
            className="icon-button"
            onClick={logout}
            disabled={busy}
            aria-label="退出登录"
            title="退出登录"
          >
            <LogOut size={18} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <button
              className="icon-button mobile-menu"
              aria-label="打开任务列表"
              onClick={() => setSidebar(true)}
            >
              <Menu size={20} />
            </button>
            <span>工作空间</span>
            <ChevronRight size={14} />
            <strong>{selected ? "反应分析" : "新建分析"}</strong>
          </div>
          <div>
            <span className="mode-chip">
              <span /> MOCK · 流程验证
            </span>
            <button
              ref={aboutButton}
              className="icon-button"
              aria-label="查看运行模式说明"
              onClick={() => setAbout(true)}
            >
              <Info size={18} />
            </button>
          </div>
        </header>
        <main className="content">
          {error && (
            <div className="error-banner" role="alert">
              {error}
              <button
                className="icon-button"
                aria-label="关闭提示"
                onClick={() => setError("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {!selected ? (
            <>
              <div className="page-heading">
                <div className="eyebrow">
                  <span /> REACTION WORKSPACE
                </div>
                <h1>反应器选型与模拟分析</h1>
                <p>输入反应条件，查看选型依据，确认参数并运行模拟。</p>
              </div>
              <form
                className="query-card"
                onSubmit={(e) => {
                  e.preventDefault();
                  void action(() =>
                    api.analyze(
                      query.trim(),
                      key(JSON.stringify({ query, example })),
                      example,
                    ),
                  );
                }}
              >
                <div className="card-title">
                  <span className="soft-icon">
                    <FlaskConical size={21} />
                  </span>
                  <div>
                    <h2>开始一次反应分析</h2>
                    <p>尽量包含反应物、产物、温度、压力及已知转化率。</p>
                  </div>
                </div>
                <label className="sr-only" htmlFor="reaction-query">
                  反应描述
                </label>
                <textarea
                  id="reaction-query"
                  value={query}
                  maxLength={20000}
                  onChange={(e) => {
                    setQuery(e.target.value);
                    setExample(undefined);
                  }}
                  placeholder="例如：已知具体可逆反应，并且体系受化学平衡控制。请分析适合的反应器类型，并告诉我还需要补充哪些参数。"
                  required
                  rows={6}
                />
                <div className="query-footer">
                  <span>
                    {example
                      ? "已载入结构化示例 · 无需在线模型解析"
                      : "模型顺序：本地 → DeepSeek → 硅基流动"}
                  </span>
                  <button className="primary" disabled={busy || !query.trim()}>
                    {busy ? (
                      <span className="spinner" />
                    ) : (
                      <ArrowRight size={17} />
                    )}{" "}
                    开始分析
                  </button>
                </div>
              </form>
              <div className="examples-heading">
                <h2>从典型场景开始</h2>
                <span>开发示例，参数未经工程适用性核验</span>
              </div>
              <div className="example-grid">
                {examples.map((item, index) => (
                  <button
                    className="example-card"
                    key={item.id}
                    onClick={() => {
                      setQuery(item.user_query);
                      setExample(item);
                      document.getElementById("reaction-query")?.focus();
                    }}
                  >
                    <span className="example-number">
                      0{index + 1}
                      <ArrowRight size={16} />
                    </span>
                    <h3>{item.title}</h3>
                    <p>{item.subtitle}</p>
                    <span className="example-link">
                      载入示例 <ChevronRight size={14} />
                    </span>
                  </button>
                ))}
              </div>
              <div className="principle">
                <Info size={18} />
                <p>
                  选型由工程规则约束；温度高并不意味着必须选择
                  Gibbs。当前仅验证工作流，真实计算需完成远程 HYSYS 接口验证。
                </p>
              </div>
            </>
          ) : !task ? (
            <div className="page-loading">
              <span className="spinner" /> 正在读取任务
            </div>
          ) : (
            <>
              <div className="task-heading">
                <div>
                  <div className="eyebrow">
                    ANALYSIS / {task.id.slice(0, 8).toUpperCase()}
                  </div>
                  <h1>
                    {state?.reaction_info?.reaction_name || "反应工程分析"}
                  </h1>
                  <p>{task.title}</p>
                  <div className="task-lineage">
                    <span>
                      {task.revision === 0
                        ? "原始分析"
                        : `修订 ${task.revision}`}{" "}
                      · 原始任务 {task.root_id.slice(0, 8)}
                    </span>
                    {task.parent_id && (
                      <button
                        className="text-button"
                        onClick={() => choose(task.parent_id!)}
                      >
                        查看上一版本
                      </button>
                    )}
                  </div>
                </div>
                <span className={`status-pill ${task.status}`}>
                  {active(task) && <span className="spinner" />}
                  {labels[task.status] ?? task.status}
                </span>
              </div>
              <ol className="progress-steps">
                {stages.map((stage, index) => {
                  const current = stages.indexOf(task.stage ?? "");
                  const done =
                    !(
                      task.status === "needs_input" &&
                      (index === 2 || (index === 1 && !state?.selected_reactor))
                    ) &&
                    (task.status === "completed" ||
                      (current >= 0 && index < current) ||
                      (["needs_input", "awaiting_confirmation"].includes(
                        task.status,
                      ) &&
                        index < 3));
                  return (
                    <li
                      key={stage}
                      className={`${done ? "done" : ""} ${task.stage === stage && active(task) ? "current" : ""}`}
                    >
                      <span>{done ? <Check size={15} /> : index + 1}</span>
                      <div>
                        {stageLabels[index]}
                        <small>
                          {task.status === "needs_input" && index === 2
                            ? "发现缺项"
                            : task.status === "needs_input" &&
                                index === 1 &&
                                !state?.selected_reactor
                              ? "待补充依据"
                              : task.status === "awaiting_confirmation" &&
                                  index === 3
                                ? "待确认"
                                : done
                                  ? "已完成"
                                  : task.stage === stage && active(task)
                                    ? "处理中"
                                    : "等待"}
                        </small>
                      </div>
                    </li>
                  );
                })}
              </ol>
              <div className="analysis-grid">
                <section className="recommendation card">
                  <div className="eyebrow">已保存的选型结论</div>
                  <span className="reactor-symbol">
                    <FlaskConical size={32} strokeWidth={1.3} />
                  </span>
                  <h2>
                    {names[state?.selected_reactor ?? ""] || "等待选型结论"}
                  </h2>
                  <p className="reactor-english">
                    {state?.selected_reactor
                      ? `${state.selected_reactor} Reactor`
                      : "Engineering rules"}
                  </p>
                  <div className="divider" />
                  <h3>
                    <ShieldCheck size={16} /> 选择依据
                  </h3>
                  <p className="reason">
                    {state?.selection_reason ||
                      "系统将根据已知信息匹配工程规则。"}
                  </p>
                  <div className="rule-note">LLM 提取信息 · 工程规则约束</div>
                </section>
                <section className="card context-card">
                  <div className="card-section-title">
                    <h2>反应描述</h2>
                    <span>原始输入</span>
                  </div>
                  <p className="original-query">{state?.user_query}</p>
                  <div className="divider" />
                  <div className="card-section-title">
                    <h3>参数检查</h3>
                    <span>
                      {state?.validation_passed
                        ? "已通过"
                        : task.status === "needs_input"
                          ? "发现缺项"
                          : "待核验"}
                    </span>
                  </div>
                  {state?.missing_parameters?.length ? (
                    <ul className="missing-list">
                      {state.missing_parameters.map((value) => (
                        <li key={value}>{readable(value)}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="muted">
                      {state?.validation_passed
                        ? "所需参数已齐全。请核对下方参数后确认运行。"
                        : "分析完成后，将在这里列出需要补充的信息。"}
                    </p>
                  )}
                  {state?.error && (
                    <div className="error-banner">{readable(state.error)}</div>
                  )}
                </section>
              </div>
              {ready && (
                <section className="card parameters-card">
                  <div className="card-section-title">
                    <div>
                      <h2>
                        {task.status === "completed"
                          ? "调整参数 · 新建修订"
                          : "确认模拟参数"}
                      </h2>
                      <p>单位与参数将再次由 Python 后端校验。</p>
                    </div>
                    <span className="outline-chip">人工确认</span>
                  </div>
                  <Parameters
                    key={task.id}
                    info={state?.reaction_info ?? {}}
                    inputs={state?.simulation_inputs ?? {}}
                    reactor={state?.selected_reactor}
                    busy={busy}
                    onRun={async (info, inputs) => {
                      await action(() =>
                        api.run(
                          task.id,
                          info,
                          inputs,
                          key(JSON.stringify({ id: task.id, info, inputs })),
                        ),
                      );
                    }}
                  />
                </section>
              )}
              {state?.final_answer && (
                <section className="card result-card">
                  <div className="card-section-title">
                    <div>
                      <h2>分析说明</h2>
                      <p>
                        {state.simulation_results?.source === "mock"
                          ? "Mock 调用链已完成，没有真实收敛、组成或能耗数据。"
                          : "根据工程规则与当前执行状态生成。"}
                      </p>
                    </div>
                    <button className="secondary" onClick={download}>
                      <Download size={15} /> 导出记录
                    </button>
                  </div>
                  <div className="result-text">
                    {readable(state.final_answer)}
                  </div>
                </section>
              )}
              {["interrupted", "pending"].includes(task.status) && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => void action(() => api.resume(task.id))}
                >
                  <RefreshCw size={16} /> 恢复任务
                </button>
              )}
              {task.status === "completed" &&
                state?.explanation_status === "degraded" && (
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => void action(() => api.explain(task.id))}
                  >
                    <RefreshCw size={16} /> 重新生成解释
                  </button>
                )}
              {task.status === "outcome_unknown" && (
                <div className="error-banner">
                  执行结果需要人工核对，系统已禁止自动重跑。
                </div>
              )}
              <details className="execution-details">
                <summary>执行详情与模型调用记录</summary>
                <dl>
                  <dt>任务编号</dt>
                  <dd>{task.id}</dd>
                  <dt>当前阶段</dt>
                  <dd>{currentStage(task, stageLabels, stages)}</dd>
                  <dt>模型降级顺序</dt>
                  <dd>本地 → DeepSeek → 硅基流动</dd>
                </dl>
                {state?.llm_trace?.length ? (
                  <div className="trace-list">
                    {state.llm_trace.map((trace, index) => (
                      <div key={index}>
                        <strong>{trace.provider}</strong>
                        <span>{trace.model}</span>
                        <span>{trace.status}</span>
                        <small>{trace.duration_ms ?? "—"} ms</small>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="muted">
                    此任务暂无在线模型调用记录。结构化示例使用规则说明。
                  </p>
                )}
              </details>
            </>
          )}
          <footer className="workspace-footer">
            反应工程工作台 <span>工程判断需结合物性适用性与实际工况复核</span>
          </footer>
        </main>
      </div>
      {about && (
        <div className="modal-backdrop" onClick={() => setAbout(false)}>
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="mode-title"
            className="modal"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              ref={closeButton}
              className="icon-button modal-close"
              aria-label="关闭模式说明"
              onClick={() => setAbout(false)}
            >
              <X size={20} />
            </button>
            <span className="soft-icon">
              <FlaskConical size={26} />
            </span>
            <h2 id="mode-title">当前运行模式：Mock</h2>
            <p>
              页面连接真实 Python
              服务，执行真实选型规则、参数校验和任务持久化。模拟部分使用 Mock
              控制器验证调用链。
            </p>
            <p>
              真实 HYSYS 仅已验证连接至活动案例的
              Flowsheet。反应器创建与真实计算仍需在考试机逐项验证。
            </p>
            <p className="muted">
              退出登录不会终止已提交任务；会话有效期为8小时。
            </p>
          </section>
        </div>
      )}
    </div>
  );
}
