from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from gsa.agent.orchestrator import Orchestrator
from gsa.agent.schema import Plan
from gsa.security.redaction import redact_secrets
from gsa.workflows import (
    execute_issue_branch,
    execute_push_pr,
    execute_safe_commit,
    get_environment,
    get_trace,
    plan_issue_branch,
    plan_pr_readiness,
    plan_push_pr,
    plan_safe_commit,
)
from gsa.workflows.trace_store import list_traces


class PlanRequest(BaseModel):
    user_input: str
    use_llm: bool = True


class ExecuteRequest(BaseModel):
    plan: Plan
    trace_id: str
    confirmed: bool = False


class IndexBuildRequest(BaseModel):
    include_globs: Optional[list[str]] = None
    exclude_globs: Optional[list[str]] = None
    chunk_size: int = 800
    overlap: int = 100
    dry_run: bool = True


class SafeCommitPlanRequest(BaseModel):
    selected_paths: Optional[list[str]] = None
    message: Optional[str] = None


class SafeCommitExecuteRequest(BaseModel):
    trace_id: str
    confirmed: bool = False
    selected_paths: Optional[list[str]] = None
    message: Optional[str] = None


class IssueBranchPlanRequest(BaseModel):
    issue: str


class IssueBranchExecuteRequest(BaseModel):
    trace_id: str
    confirmed: bool = False


class PushPrPlanRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    draft: bool = True


class PushPrExecuteRequest(BaseModel):
    trace_id: str
    confirmed: bool = False
    title: Optional[str] = None
    body: Optional[str] = None
    draft: bool = True


class PrReadinessRequest(BaseModel):
    pr: Optional[str] = None


app = FastAPI(title="Git Safety Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _workspace() -> str:
    return app.state.workspace


def _redacted(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return redact_secrets(value)


@app.on_event("startup")
def startup():
    workspace = os.environ.get("GSA_WORKSPACE", os.getcwd())
    app.state.workspace = workspace
    app.state.orchestrator = Orchestrator(workspace)


@app.post("/plan")
def plan(req: PlanRequest) -> Dict[str, Any]:
    orch: Orchestrator = app.state.orchestrator
    orch.use_llm = req.use_llm
    result = orch.plan(req.user_input)
    return _redacted(result.model_dump())


@app.post("/execute")
def execute(req: ExecuteRequest) -> Dict[str, Any]:
    orch: Orchestrator = app.state.orchestrator
    return _redacted(orch.execute(req.plan, trace_id=req.trace_id, confirmed=req.confirmed))


@app.post("/index/build")
def index_build(req: IndexBuildRequest) -> Dict[str, Any]:
    orch: Orchestrator = app.state.orchestrator
    return _redacted(orch.mcp.call_tool(
        "index_build",
        {
            "include_globs": req.include_globs,
            "exclude_globs": req.exclude_globs,
            "chunk_size": req.chunk_size,
            "overlap": req.overlap,
            "dry_run": req.dry_run,
        },
    ))


@app.post("/memory/clear")
def memory_clear() -> Dict[str, Any]:
    orch: Orchestrator = app.state.orchestrator
    orch.memory.clear()
    return {"ok": True}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/environment")
def api_environment() -> Dict[str, Any]:
    return _redacted(get_environment(_workspace()))


@app.get("/api/traces")
def api_traces(limit: int = 25) -> list[Dict[str, Any]]:
    return _redacted(list_traces(_workspace(), limit=limit))


@app.get("/api/traces/{trace_id}")
def api_trace(trace_id: str) -> Dict[str, Any]:
    trace = get_trace(_workspace(), trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="trace not found")
    return _redacted(trace)


@app.post("/api/workflows/safe-commit/plan")
def api_safe_commit_plan(req: SafeCommitPlanRequest) -> Dict[str, Any]:
    return _redacted(plan_safe_commit(_workspace(), selected_paths=req.selected_paths, message=req.message))


@app.post("/api/workflows/safe-commit/execute")
def api_safe_commit_execute(req: SafeCommitExecuteRequest) -> Dict[str, Any]:
    return _redacted(
        execute_safe_commit(
            _workspace(),
            trace_id=req.trace_id,
            confirmed=req.confirmed,
            selected_paths=req.selected_paths,
            message=req.message,
        )
    )


@app.post("/api/workflows/issue-branch/plan")
def api_issue_branch_plan(req: IssueBranchPlanRequest) -> Dict[str, Any]:
    return _redacted(plan_issue_branch(_workspace(), issue=req.issue))


@app.post("/api/workflows/issue-branch/execute")
def api_issue_branch_execute(req: IssueBranchExecuteRequest) -> Dict[str, Any]:
    return _redacted(execute_issue_branch(_workspace(), trace_id=req.trace_id, confirmed=req.confirmed))


@app.post("/api/workflows/push-pr/plan")
def api_push_pr_plan(req: PushPrPlanRequest) -> Dict[str, Any]:
    return _redacted(plan_push_pr(_workspace(), title=req.title, body=req.body, draft=req.draft))


@app.post("/api/workflows/push-pr/execute")
def api_push_pr_execute(req: PushPrExecuteRequest) -> Dict[str, Any]:
    return _redacted(
        execute_push_pr(
            _workspace(),
            trace_id=req.trace_id,
            confirmed=req.confirmed,
            title=req.title,
            body=req.body,
            draft=req.draft,
        )
    )


@app.post("/api/workflows/pr-readiness")
def api_pr_readiness(req: PrReadinessRequest) -> Dict[str, Any]:
    return _redacted(plan_pr_readiness(_workspace(), pr=req.pr))
