import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";

type WorkflowStatus = "ready" | "blocked" | "needs_input";

type RiskItem = {
  level: "low" | "medium" | "high";
  message: string;
  blocking: boolean;
  recommended_action?: string;
};

type CommandPreview = {
  command: string;
  description: string;
  destructive: boolean;
};

type WorkflowPlan = {
  trace_id: string;
  workflow_type: string;
  status: WorkflowStatus;
  summary: string;
  risks: RiskItem[];
  command_preview: CommandPreview[];
  requires_confirmation: boolean;
  data: Record<string, any>;
};

type WorkflowResult = {
  trace_id: string;
  ok: boolean;
  summary: string;
  executed_commands: string[];
  github_urls: string[];
  errors: string[];
  next_actions: string[];
  data: Record<string, any>;
};

type Environment = {
  workspace: string;
  git: {
    is_repo: boolean;
    repo_root: string;
    branch: string;
    dirty: boolean;
    changed_count: number;
    remote_url: string;
    upstream: string;
    ahead: number;
    behind: number;
  };
  github: {
    gh_available: boolean;
    authenticated: boolean;
    message: string;
  };
  llm: {
    configured: boolean;
    model: string;
    base_url: string;
    provider_label: string;
  };
  recent_traces: TraceSummary[];
};

type TraceSummary = {
  trace_id: string;
  updated_at: string;
  latest_event: string;
  workflow_type: string;
  summary: string;
  ok?: boolean;
  status?: string;
};

const API_BASE = import.meta.env.VITE_GSA_API_BASE || "http://127.0.0.1:8000";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {})
    }
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data?.detail || `API ${response.status}`);
  }
  return data as T;
}

const nav = [
  ["overview", "Overview"],
  ["safe-commit", "Safe Commit"],
  ["issue-branch", "Issue Branch"],
  ["push-pr", "Push & Draft PR"],
  ["pr-readiness", "PR Readiness"],
  ["trace", "Trace"]
] as const;

type ViewId = (typeof nav)[number][0];

export default function App() {
  const [view, setView] = useState<ViewId>("overview");
  const [env, setEnv] = useState<Environment | null>(null);
  const [envError, setEnvError] = useState("");
  const [busyEnv, setBusyEnv] = useState(false);
  const [activePlan, setActivePlan] = useState<WorkflowPlan | null>(null);
  const [activeResult, setActiveResult] = useState<WorkflowResult | null>(null);

  async function refreshEnv() {
    setBusyEnv(true);
    setEnvError("");
    try {
      setEnv(await api<Environment>("/api/environment"));
    } catch (error) {
      setEnvError(String(error));
    } finally {
      setBusyEnv(false);
    }
  }

  useEffect(() => {
    refreshEnv();
  }, []);

  const viewNode = useMemo(() => {
    const shared = {
      onPlan: setActivePlan,
      onResult: (result: WorkflowResult | null) => {
        setActiveResult(result);
        refreshEnv();
      }
    };
    if (view === "safe-commit") return <SafeCommit {...shared} />;
    if (view === "issue-branch") return <IssueBranch {...shared} />;
    if (view === "push-pr") return <PushDraftPr {...shared} />;
    if (view === "pr-readiness") return <PrReadiness {...shared} />;
    if (view === "trace") return <TraceView onPlan={setActivePlan} onResult={setActiveResult} />;
    return <Overview env={env} loading={busyEnv} error={envError} onRefresh={refreshEnv} />;
  }, [view, env, busyEnv, envError]);

  return (
    <div className="app">
      <header className="topbar" aria-busy={busyEnv}>
        <div>
          <p className="eyebrow">Git Safety Agent</p>
          <h1>GitHub 协作安全工作台</h1>
        </div>
        <div className="status-strip" aria-label="环境状态">
          <StatusPill label="Repo" value={env?.git.is_repo ? env.git.branch || "repo" : "非 Git 仓库"} tone={env?.git.is_repo ? "good" : "bad"} />
          <StatusPill label="Dirty" value={env?.git.dirty ? `${env.git.changed_count} files` : "干净"} tone={env?.git.dirty ? "warn" : "good"} />
          <StatusPill label="GitHub" value={env?.github.authenticated ? "已登录" : env?.github.gh_available ? "未登录" : "缺 gh"} tone={env?.github.authenticated ? "good" : "warn"} />
          <StatusPill label="LLM" value={env?.llm.configured ? "已配置" : "未配置"} tone={env?.llm.configured ? "good" : "neutral"} />
        </div>
      </header>
      {envError ? <div className="banner error" role="alert">{envError}</div> : null}
      <div className="layout">
        <nav className="sidebar" aria-label="工作流导航">
          {nav.map(([id, label]) => (
            <button
              key={id}
              className={view === id ? "nav-button active" : "nav-button"}
              type="button"
              aria-current={view === id ? "page" : undefined}
              onClick={() => setView(id)}
            >
              {label}
            </button>
          ))}
        </nav>
        <main className="main-panel">{viewNode}</main>
        <Inspector plan={activePlan} result={activeResult} />
      </div>
    </div>
  );
}

function StatusPill({ label, value, tone }: { label: string; value: string; tone: "good" | "warn" | "bad" | "neutral" }) {
  return (
    <div className={`pill ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Section({ title, children, busy = false }: { title: string; children: ReactNode; busy?: boolean }) {
  return (
    <section className="section" aria-busy={busy}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function Alert({ children }: { children: ReactNode }) {
  return (
    <div className="banner error" role="alert">
      {children}
    </div>
  );
}

function Overview({ env, loading, error, onRefresh }: { env: Environment | null; loading: boolean; error: string; onRefresh: () => void }) {
  const suggestions = [];
  if (!env?.git.is_repo) suggestions.push(["初始化 Git", "git init"]);
  if (env?.git.is_repo && !env.github.gh_available) suggestions.push(["安装 GitHub CLI", "brew install gh"]);
  if (env?.github.gh_available && !env.github.authenticated) suggestions.push(["登录 GitHub CLI", "gh auth login"]);
  if (!env?.llm.configured) suggestions.push(["配置可选 LLM 文案辅助", "在 .env 中设置 BIGMODEL_API_KEY 或 ZAI_API_KEY"]);
  if (env?.git.is_repo && env.github.authenticated && !env.git.dirty) suggestions.push(["开始 Issue 分支", "选择 Issue Branch 工作流"]);
  if (env?.git.dirty) suggestions.push(["检查本地改动", "选择 Safe Commit 工作流"]);

  return (
    <Section title="Overview" busy={loading}>
      {error ? <Alert>{error}</Alert> : null}
      <button className="secondary" type="button" onClick={onRefresh}>刷新环境状态</button>
      <div className="grid two">
        <div className="panel">
          <h3>Repo 状态</h3>
          <dl className="meta">
            <dt>Workspace</dt><dd>{env?.workspace || "读取中"}</dd>
            <dt>Repo</dt><dd>{env?.git.is_repo ? "可操作" : "阻塞：非 Git 仓库"}</dd>
            <dt>Branch</dt><dd>{env?.git.branch || "无"}</dd>
            <dt>Changes</dt><dd>{env?.git.dirty ? `${env.git.changed_count} 个文件` : "无未提交改动"}</dd>
            <dt>Upstream</dt><dd>{env?.git.upstream || "未设置"}</dd>
            <dt>Ahead / Behind</dt><dd>{env ? `${env.git.ahead} / ${env.git.behind}` : "读取中"}</dd>
          </dl>
        </div>
        <div className="panel">
          <h3>环境缺失提示</h3>
          <ul className="action-list">
            {suggestions.map(([title, command]) => (
              <li key={title}>
                <strong>{title}</strong>
                <code>{command}</code>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Section>
  );
}

function SafeCommit({ onPlan, onResult }: { onPlan: (plan: WorkflowPlan) => void; onResult: (result: WorkflowResult | null) => void }) {
  const [message, setMessage] = useState("");
  const [paths, setPaths] = useState<string[]>([]);
  const [plan, setPlan] = useState<WorkflowPlan | null>(null);
  const [result, setResult] = useState<WorkflowResult | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [dirtyPlan, setDirtyPlan] = useState(false);

  async function generatePlan(event?: FormEvent) {
    event?.preventDefault();
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const next = await api<WorkflowPlan>("/api/workflows/safe-commit/plan", {
        method: "POST",
        body: JSON.stringify({ selected_paths: paths.length ? paths : undefined, message: message || undefined })
      });
      setPlan(next);
      onPlan(next);
      setPaths(next.data.selected_paths || []);
      setDirtyPlan(false);
      setConfirmed(false);
    } catch (error) {
      setError(String(error));
    } finally {
      setBusy(false);
    }
  }

  async function execute() {
    if (!plan) return;
    setBusy(true);
    setError("");
    try {
      const next = await api<WorkflowResult>("/api/workflows/safe-commit/execute", {
        method: "POST",
        body: JSON.stringify({ trace_id: plan.trace_id, confirmed, selected_paths: paths, message: message || undefined })
      });
      setResult(next);
      onResult(next);
    } catch (error) {
      setError(String(error));
    } finally {
      setBusy(false);
    }
  }

  const files = (plan?.data.files || []) as Array<Record<string, any>>;
  const staged = files.filter((file) => file.staged);
  const unstaged = files.filter((file) => file.unstaged);
  const canExecute = Boolean(plan && plan.status === "ready" && confirmed && !dirtyPlan && !busy);

  return (
    <Section title="Safe Commit" busy={busy}>
      {error ? <Alert>{error}</Alert> : null}
      <form className="form" onSubmit={generatePlan}>
        <label htmlFor="commit-message">Commit message</label>
        <input id="commit-message" value={message} onChange={(event) => { setMessage(event.target.value); setDirtyPlan(Boolean(plan)); }} placeholder="Update GitHub workflow safety" />
        <button type="submit">生成提交计划</button>
      </form>
      {plan ? (
        <>
          <StatusBlock plan={plan} dirtyPlan={dirtyPlan} />
          <div className="grid two">
            <FileGroup title="Staged files" files={staged} selected={paths} onChange={(next) => { setPaths(next); setDirtyPlan(true); }} />
            <FileGroup title="Unstaged files" files={unstaged} selected={paths} onChange={(next) => { setPaths(next); setDirtyPlan(true); }} />
          </div>
          <details>
            <summary>展开 diff summary</summary>
            <pre className="diff">{plan.data.diff_summary || plan.data.staged_diff_summary || "无 diff 输出"}</pre>
          </details>
          <label className="confirm-row">
            <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
            我已检查文件、风险和命令预览，确认执行本地 commit
          </label>
          <button className="danger" type="button" disabled={!canExecute} onClick={execute}>执行提交</button>
          {dirtyPlan ? <p className="hint">输入或文件选择已变化，请重新生成提交计划。</p> : null}
        </>
      ) : (
        <p className="empty">先生成计划以查看 changed files、风险和 dry-run 命令。</p>
      )}
      {result ? <ResultBlock result={result} /> : null}
    </Section>
  );
}

function FileGroup({ title, files, selected, onChange }: { title: string; files: Array<Record<string, any>>; selected: string[]; onChange: (paths: string[]) => void }) {
  return (
    <div className="panel">
      <h3>{title}</h3>
      {files.length ? (
        <ul className="file-list">
          {files.map((file) => {
            const path = String(file.path);
            const checked = selected.includes(path);
            return (
              <li key={`${title}-${path}`}>
                <label>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(event) => {
                      onChange(event.target.checked ? [...selected, path] : selected.filter((item) => item !== path));
                    }}
                  />
                  <span>{path}</span>
                  <small>{file.raw}</small>
                </label>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="empty">无文件</p>
      )}
    </div>
  );
}

function IssueBranch({ onPlan, onResult }: { onPlan: (plan: WorkflowPlan) => void; onResult: (result: WorkflowResult | null) => void }) {
  const [issue, setIssue] = useState("");
  const [plan, setPlan] = useState<WorkflowPlan | null>(null);
  const [result, setResult] = useState<WorkflowResult | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [dirtyPlan, setDirtyPlan] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function generatePlan(event?: FormEvent) {
    event?.preventDefault();
    setBusy(true);
    setError("");
    try {
      const next = await api<WorkflowPlan>("/api/workflows/issue-branch/plan", {
        method: "POST",
        body: JSON.stringify({ issue })
      });
      setPlan(next);
      onPlan(next);
      setDirtyPlan(false);
      setConfirmed(false);
    } catch (error) {
      setError(String(error));
    } finally {
      setBusy(false);
    }
  }

  async function execute() {
    if (!plan) return;
    setBusy(true);
    setError("");
    try {
      const next = await api<WorkflowResult>("/api/workflows/issue-branch/execute", {
        method: "POST",
        body: JSON.stringify({ trace_id: plan.trace_id, confirmed })
      });
      setResult(next);
      onResult(next);
    } catch (error) {
      setError(String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section title="Issue Branch" busy={busy}>
      {error ? <Alert>{error}</Alert> : null}
      <form className="form" onSubmit={generatePlan}>
        <label htmlFor="issue-input">Issue number or URL</label>
        <input id="issue-input" value={issue} onChange={(event) => { setIssue(event.target.value); setDirtyPlan(Boolean(plan)); }} placeholder="123 or https://github.com/org/repo/issues/123" />
        <button type="submit" disabled={!issue.trim()}>生成分支计划</button>
      </form>
      {plan ? (
        <>
          <StatusBlock plan={plan} dirtyPlan={dirtyPlan} />
          <div className="panel">
            <h3>Branch preview</h3>
            <dl className="meta">
              <dt>Issue</dt><dd>{plan.data.issue?.title || plan.data.issue_input}</dd>
              <dt>Branch</dt><dd>{plan.data.branch}</dd>
              <dt>Base</dt><dd>{plan.data.base}</dd>
            </dl>
          </div>
          <label className="confirm-row">
            <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
            我确认基于该 issue 创建本地分支
          </label>
          <button className="danger" type="button" disabled={!(plan.status === "ready" && confirmed && !dirtyPlan && !busy)} onClick={execute}>创建分支</button>
        </>
      ) : <p className="empty">输入 issue 后生成计划。</p>}
      {result ? <ResultBlock result={result} /> : null}
    </Section>
  );
}

function PushDraftPr({ onPlan, onResult }: { onPlan: (plan: WorkflowPlan) => void; onResult: (result: WorkflowResult | null) => void }) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [plan, setPlan] = useState<WorkflowPlan | null>(null);
  const [result, setResult] = useState<WorkflowResult | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [dirtyPlan, setDirtyPlan] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function generatePlan(event?: FormEvent) {
    event?.preventDefault();
    setBusy(true);
    setError("");
    try {
      const next = await api<WorkflowPlan>("/api/workflows/push-pr/plan", {
        method: "POST",
        body: JSON.stringify({ title: title || undefined, body: body || undefined, draft: true })
      });
      setPlan(next);
      setTitle(next.data.title || title);
      setBody(next.data.body || body);
      onPlan(next);
      setDirtyPlan(false);
      setConfirmed(false);
    } catch (error) {
      setError(String(error));
    } finally {
      setBusy(false);
    }
  }

  async function execute() {
    if (!plan) return;
    setBusy(true);
    setError("");
    try {
      const next = await api<WorkflowResult>("/api/workflows/push-pr/execute", {
        method: "POST",
        body: JSON.stringify({ trace_id: plan.trace_id, confirmed, title, body, draft: true })
      });
      setResult(next);
      onResult(next);
    } catch (error) {
      setError(String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section title="Push & Draft PR" busy={busy}>
      {error ? <Alert>{error}</Alert> : null}
      <form className="form" onSubmit={generatePlan}>
        <label htmlFor="pr-title">PR title</label>
        <input id="pr-title" value={title} onChange={(event) => { setTitle(event.target.value); setDirtyPlan(Boolean(plan)); }} placeholder="Draft PR title" />
        <label htmlFor="pr-body">PR body</label>
        <textarea id="pr-body" value={body} onChange={(event) => { setBody(event.target.value); setDirtyPlan(Boolean(plan)); }} rows={6} placeholder="PR body" />
        <button type="submit">生成 Push + Draft PR 计划</button>
      </form>
      {plan ? (
        <>
          <StatusBlock plan={plan} dirtyPlan={dirtyPlan} />
          <div className="panel">
            <h3>Branch 状态</h3>
            <dl className="meta">
              <dt>Branch</dt><dd>{plan.data.branch}</dd>
              <dt>Upstream</dt><dd>{plan.data.ahead_behind?.upstream || "未设置"}</dd>
              <dt>Ahead / Behind</dt><dd>{plan.data.ahead_behind ? `${plan.data.ahead_behind.ahead} / ${plan.data.ahead_behind.behind}` : "无"}</dd>
              <dt>Existing PR</dt><dd>{plan.data.existing_prs?.length ? plan.data.existing_prs[0].url : "未发现"}</dd>
            </dl>
          </div>
          <label className="confirm-row">
            <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
            我确认 push 当前分支并创建 Draft PR
          </label>
          <button className="danger" type="button" disabled={!(plan.status === "ready" && confirmed && !dirtyPlan && !busy)} onClick={execute}>创建 Draft PR</button>
        </>
      ) : <p className="empty">生成计划后会检查保护分支、未提交改动、upstream 和已有 PR。</p>}
      {result ? <ResultBlock result={result} /> : null}
    </Section>
  );
}

function PrReadiness({ onPlan, onResult }: { onPlan: (plan: WorkflowPlan) => void; onResult: (result: WorkflowResult | null) => void }) {
  const [pr, setPr] = useState("");
  const [plan, setPlan] = useState<WorkflowPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function runCheck(event?: FormEvent) {
    event?.preventDefault();
    setBusy(true);
    setError("");
    onResult(null);
    try {
      const next = await api<WorkflowPlan>("/api/workflows/pr-readiness", {
        method: "POST",
        body: JSON.stringify({ pr: pr || undefined })
      });
      setPlan(next);
      onPlan(next);
    } catch (error) {
      setError(String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section title="PR Readiness" busy={busy}>
      {error ? <Alert>{error}</Alert> : null}
      <form className="form" onSubmit={runCheck}>
        <label htmlFor="pr-input">PR number or URL</label>
        <input id="pr-input" value={pr} onChange={(event) => setPr(event.target.value)} placeholder="留空表示当前分支 PR" />
        <button type="submit">检查 PR Readiness</button>
      </form>
      {plan ? (
        <>
          <StatusBlock plan={plan} dirtyPlan={false} />
          <div className="grid two">
            <div className="panel">
              <h3>Checks</h3>
              <ul className="action-list">
                {(plan.data.checks || []).map((check: any) => (
                  <li key={`${check.name}-${check.state}`}>
                    <strong>{check.name}</strong>
                    <span>{check.state || check.bucket || "unknown"}</span>
                  </li>
                ))}
                {!(plan.data.checks || []).length ? <li>无 check 数据</li> : null}
              </ul>
            </div>
            <div className="panel">
              <h3>Next actions</h3>
              <dl className="meta compact">
                <dt>Unresolved threads</dt>
                <dd>{plan.data.unresolved_review_threads ?? "未知"}</dd>
              </dl>
              <ul className="action-list">
                {(plan.data.next_actions || []).map((item: string) => <li key={item}>{item}</li>)}
                {!(plan.data.next_actions || []).length ? <li>无后续动作</li> : null}
              </ul>
            </div>
          </div>
        </>
      ) : <p className="empty">读取当前分支或指定 PR 的 CI、review 和本地状态。</p>}
    </Section>
  );
}

function TraceView({ onPlan, onResult }: { onPlan: (plan: WorkflowPlan | null) => void; onResult: (result: WorkflowResult | null) => void }) {
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [selected, setSelected] = useState("");
  const [trace, setTrace] = useState<Record<string, any> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function loadList() {
    setBusy(true);
    setError("");
    try {
      setTraces(await api<TraceSummary[]>("/api/traces"));
    } catch (error) {
      setError(String(error));
    } finally {
      setBusy(false);
    }
  }

  async function loadTrace(id: string) {
    setSelected(id);
    setBusy(true);
    setError("");
    try {
      const next = await api<Record<string, any>>(`/api/traces/${id}`);
      setTrace(next);
      const events = next.events || [];
      const latest = events[events.length - 1]?.payload;
      if (latest?.command_preview) onPlan(latest as WorkflowPlan);
      if (latest?.executed_commands) onResult(latest as WorkflowResult);
    } catch (error) {
      setError(String(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    loadList();
  }, []);

  return (
    <Section title="Trace" busy={busy}>
      {error ? <Alert>{error}</Alert> : null}
      <button className="secondary" type="button" onClick={loadList}>刷新 trace 列表</button>
      <div className="grid two">
        <div className="panel">
          <h3>最近 workflow trace</h3>
          <ul className="trace-list">
            {traces.map((item) => (
              <li key={item.trace_id}>
                <button className={selected === item.trace_id ? "link-button active" : "link-button"} type="button" onClick={() => loadTrace(item.trace_id)}>
                  <span>{item.workflow_type || item.latest_event}</span>
                  <small>{item.summary || item.trace_id}</small>
                </button>
              </li>
            ))}
            {!traces.length ? <li className="empty">暂无 trace</li> : null}
          </ul>
        </div>
        <div className="panel">
          <h3>Trace detail</h3>
          {trace ? <pre className="log">{JSON.stringify(trace, null, 2)}</pre> : <p className="empty">选择一个 trace 查看脱敏后的输入、命令和结果。</p>}
        </div>
      </div>
    </Section>
  );
}

function StatusBlock({ plan, dirtyPlan }: { plan: WorkflowPlan; dirtyPlan: boolean }) {
  const text = plan.status === "ready" ? "Ready" : plan.status === "blocked" ? "Blocked" : "Needs input";
  return (
    <div className={`status-block ${plan.status}`}>
      <strong>{text}</strong>
      <span>{plan.summary}</span>
      {dirtyPlan ? <span>当前表单已变化，需要重新生成 plan。</span> : null}
    </div>
  );
}

function ResultBlock({ result }: { result: WorkflowResult }) {
  return (
    <div className={result.ok ? "result ok" : "result fail"} role={result.ok ? "status" : "alert"}>
      <h3>{result.ok ? "执行成功" : "执行失败"}</h3>
      <p>{result.summary}</p>
      {result.github_urls.map((url) => <a key={url} href={url} target="_blank" rel="noreferrer">{url}</a>)}
      {result.errors.length ? <ul>{result.errors.map((error) => <li key={error}>{error}</li>)}</ul> : null}
    </div>
  );
}

function Inspector({ plan, result }: { plan: WorkflowPlan | null; result: WorkflowResult | null }) {
  return (
    <aside className="inspector" aria-label="风险、命令和执行结果">
      <section>
        <h2>Risks</h2>
        {plan?.risks.length ? (
          <ul className="risk-list">
            {plan.risks.map((risk, index) => (
              <li key={`${risk.message}-${index}`} className={risk.blocking ? "blocking" : ""}>
                <strong>{risk.blocking ? "阻塞" : risk.level}</strong>
                <span>{risk.message}</span>
                {risk.recommended_action ? <small>{risk.recommended_action}</small> : null}
              </li>
            ))}
          </ul>
        ) : <p className="empty">无风险数据</p>}
      </section>
      <section>
        <h2>Command preview</h2>
        {plan?.command_preview.length ? plan.command_preview.map((item) => (
          <div className="command" key={item.command}>
            <code>{item.command}</code>
            <small>{item.description}</small>
          </div>
        )) : <p className="empty">尚未生成计划</p>}
      </section>
      <section>
        <h2>Result</h2>
        {result ? <ResultBlock result={result} /> : <p className="empty">尚未执行</p>}
      </section>
    </aside>
  );
}
