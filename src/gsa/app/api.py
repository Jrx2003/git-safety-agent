from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import FastAPI
from pydantic import BaseModel

from gsa.agent.orchestrator import Orchestrator
from gsa.agent.schema import Plan


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


app = FastAPI(title="Git Safety Agent")


@app.on_event("startup")
def startup():
    workspace = os.environ.get("GSA_WORKSPACE", os.getcwd())
    app.state.orchestrator = Orchestrator(workspace)


@app.post("/plan")
def plan(req: PlanRequest) -> Dict[str, Any]:
    orch: Orchestrator = app.state.orchestrator
    orch.use_llm = req.use_llm
    result = orch.plan(req.user_input)
    return result.model_dump()


@app.post("/execute")
def execute(req: ExecuteRequest) -> Dict[str, Any]:
    orch: Orchestrator = app.state.orchestrator
    return orch.execute(req.plan, trace_id=req.trace_id, confirmed=req.confirmed)


@app.post("/index/build")
def index_build(req: IndexBuildRequest) -> Dict[str, Any]:
    orch: Orchestrator = app.state.orchestrator
    return orch.mcp.call_tool(
        "index_build",
        {
            "include_globs": req.include_globs,
            "exclude_globs": req.exclude_globs,
            "chunk_size": req.chunk_size,
            "overlap": req.overlap,
            "dry_run": req.dry_run,
        },
    )


@app.post("/memory/clear")
def memory_clear() -> Dict[str, Any]:
    orch: Orchestrator = app.state.orchestrator
    orch.memory.clear()
    return {"ok": True}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}
