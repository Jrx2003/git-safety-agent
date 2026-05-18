import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";

const env = {
  workspace: "/tmp/repo",
  git: {
    is_repo: true,
    repo_root: "/tmp/repo",
    branch: "feature/test",
    dirty: true,
    changed_count: 1,
    remote_url: "https://github.com/example/repo.git",
    upstream: "origin/feature/test",
    ahead: 0,
    behind: 0
  },
  github: {
    gh_available: true,
    authenticated: true,
    message: "Token=[REDACTED]"
  },
  llm: {
    configured: true,
    model: "glm-4.7",
    base_url: "https://api.z.ai/api/paas/v4/",
    provider_label: "OpenAI-compatible"
  },
  recent_traces: []
};

const safeCommitPlan = {
  trace_id: "trace-1",
  workflow_type: "safe_commit",
  status: "ready",
  summary: "提交计划已生成",
  risks: [],
  command_preview: [
    {
      command: "git add -- README.md",
      description: "暂存文件",
      destructive: false
    }
  ],
  requires_confirmation: true,
  data: {
    branch: "feature/test",
    files: [
      {
        path: "README.md",
        raw: " M README.md",
        staged: false,
        unstaged: true
      }
    ],
    selected_paths: ["README.md"],
    message: "Update README",
    diff_summary: "README.md | 1 +"
  }
};

describe("GSA workbench", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/api/workflows/safe-commit/plan")) {
          return new Response(JSON.stringify(safeCommitPlan), { status: 200 });
        }
        return new Response(JSON.stringify(env), { status: 200 });
      })
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  test("renders environment status without exposing secrets", async () => {
    render(<App />);

    expect(await screen.findByText("GitHub 协作安全工作台")).toBeInTheDocument();
    expect(screen.getByText("LLM")).toBeInTheDocument();
    expect(screen.getByText("已配置")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("api_key");
    expect(document.body.textContent).not.toContain("sk-");
  });

  test("safe commit execute stays disabled until ready plan is confirmed", async () => {
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Safe Commit" }));
    expect(screen.getByLabelText("Commit message")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "生成提交计划" }));

    const executeButton = await screen.findByRole("button", { name: "执行提交" });
    expect(executeButton).toBeDisabled();

    fireEvent.click(screen.getByLabelText("我已检查文件、风险和命令预览，确认执行本地 commit"));
    await waitFor(() => expect(executeButton).toBeEnabled());
  });
});
