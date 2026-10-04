import { useState } from "react";
import {
  ArrowRight,
  Eye,
  EyeOff,
  FlaskConical,
  LockKeyhole,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { api } from "./api";
import type { User } from "./types";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`brand ${compact ? "compact" : ""}`}>
      <span className="brand-icon">
        <FlaskConical size={23} strokeWidth={1.6} />
      </span>
      <div>
        <strong>反应工程工作台</strong>
        <small>HYSYS REACTOR INTELLIGENCE</small>
      </div>
    </div>
  );
}
export default function Login({
  onLogin,
  connectionError,
}: {
  onLogin: (user: User) => void;
  connectionError: string;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(connectionError);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      onLogin(await api.login(username.trim(), password));
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-page">
      <section className="login-story">
        <Brand />
        <div className="story-body">
          <div className="eyebrow light">
            <span /> ENGINEERING, WITH CLARITY
          </div>
          <h1>
            让反应器选择，
            <br />
            <em>有据可循。</em>
          </h1>
          <p>
            从一段反应描述，到清晰的工程判断。
            <br />
            把语言理解、选型依据与模拟过程，连接在一起。
          </p>
          <div className="process-art" aria-hidden="true">
            <span className="art-kicker">REACTION → REASONING → RESULT</span>
            <div className="art-pipeline">
              <div className="feed-dot" />
              <span className="pipe-line" />
              <div className="vessel">
                <i />
                <i />
                <b>R–01</b>
                <span />
              </div>
              <span className="pipe-line" />
              <div className="result-dot" />
            </div>
            <div className="art-labels">
              <span>反应条件</span>
              <span>工程规则</span>
              <span>可解释结果</span>
            </div>
          </div>
          <div className="story-values">
            <span>
              <ShieldCheck size={17} /> 规则约束选型
            </span>
            <span>
              <LockKeyhole size={17} /> 任务独立保存
            </span>
          </div>
        </div>
        <footer>PYTHON ENGINE · LANGGRAPH WORKFLOW</footer>
      </section>
      <section className="login-form-panel">
        <div className="login-top-note">HYSYS · 工程分析平台</div>
        <form className="login-form" onSubmit={submit}>
          <span className="form-tag">工作空间 / SIGN IN</span>
          <h2>欢迎回来</h2>
          <p className="muted">登录后，继续你的反应工程分析。</p>
          <label htmlFor="username">账号</label>
          <div className="input-icon">
            <UserRound size={18} />
            <input
              id="username"
              name="username"
              autoComplete="username"
              placeholder="输入管理员分配的账号"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              maxLength={64}
            />
          </div>
          <label htmlFor="password">密码</label>
          <div className="input-icon">
            <LockKeyhole size={18} />
            <input
              id="password"
              name="password"
              type={visible ? "text" : "password"}
              autoComplete="current-password"
              placeholder="输入登录密码"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              maxLength={256}
            />
            <button
              type="button"
              className="icon-button"
              aria-label={visible ? "隐藏密码" : "显示密码"}
              onClick={() => setVisible(!visible)}
            >
              {visible ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
          {error && (
            <div className="error-banner" role="alert">
              {error}
            </div>
          )}
          <button className="primary login-submit" disabled={busy}>
            {busy ? (
              <>
                <span className="spinner" /> 正在登录
              </>
            ) : (
              <>
                进入工作台 <ArrowRight size={18} />
              </>
            )}
          </button>
          <p className="login-help">
            <ShieldCheck size={16} /> 账号由管理员分配，不开放自助注册。
          </p>
        </form>
        <footer>退出登录不会中止已提交的后台任务。</footer>
      </section>
    </main>
  );
}
