from __future__ import annotations

import fnmatch
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS

from gsa.llm.llm_client import LLMClient, LLMKeyMissing, load_config
from gsa.safety.policy import PolicyError, deny_if_sensitive, ensure_in_workspace


TEXT_EXTS = {".py", ".md", ".txt", ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg"}


class SimpleHashEmbeddings(Embeddings):
    """无外部依赖的简易 Embeddings（仅用于 demo）。"""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _embed(self, text: str) -> List[float]:
        vec = np.zeros(self.dim, dtype=np.float32)
        for token in text.split():
            h = hash(token) % self.dim
            vec[h] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.astype(float).tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed(text)


class IndexTool:
    """LangChain 索引/搜索/总结。"""

    def __init__(self, workspace: str):
        self.workspace = workspace
        self.index_dir = os.path.join(workspace, ".gsa", "index")
        self.meta_path = os.path.join(workspace, ".gsa", "index_meta.json")
        self.embeddings = SimpleHashEmbeddings()

    def _safe_path(self, path: str) -> str:
        target = ensure_in_workspace(self.workspace, path)
        deny_if_sensitive(target)
        return target

    def _load_documents(self, include_globs: List[str], exclude_globs: List[str]) -> List[Document]:
        docs: List[Document] = []
        for pattern in include_globs:
            loader = DirectoryLoader(
                self.workspace,
                glob=pattern,
                loader_cls=TextLoader,
                loader_kwargs={"autodetect_encoding": True},
                silent_errors=True,
            )
            for doc in loader.load():
                path = doc.metadata.get("source", "")
                ext = os.path.splitext(path)[1].lower()
                if ext and ext not in TEXT_EXTS:
                    continue
                try:
                    deny_if_sensitive(path)
                except PolicyError:
                    continue
                if any(fnmatch.fnmatch(path, g) for g in exclude_globs):
                    continue
                docs.append(doc)
        return docs

    def build(
        self,
        include_globs: Optional[List[str]] = None,
        exclude_globs: Optional[List[str]] = None,
        chunk_size: int = 800,
        overlap: int = 100,
        dry_run: bool = True,
    ) -> Dict[str, object]:
        include_globs = include_globs or ["**/*"]
        exclude_globs = exclude_globs or ["**/.git/**", "**/.gsa/**", "**/node_modules/**"]
        _ = self._safe_path(self.workspace)
        docs = self._load_documents(include_globs, exclude_globs)
        splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
        chunks = splitter.split_documents(docs)
        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "docs": len(docs),
                "chunks": len(chunks),
            }
        if not chunks:
            return {"ok": False, "error": "未找到可索引文本"}
        os.makedirs(self.index_dir, exist_ok=True)
        vs = FAISS.from_documents(chunks, self.embeddings)
        vs.save_local(self.index_dir)
        meta = {
            "docs": len(docs),
            "chunks": len(chunks),
            "chunk_size": chunk_size,
            "overlap": overlap,
            "built_at": datetime.now().isoformat(timespec="seconds"),
        }
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return {"ok": True, **meta}

    def status(self, dry_run: bool = True) -> Dict[str, object]:
        if not os.path.exists(self.meta_path):
            return {"ok": False, "error": "索引不存在"}
        with open(self.meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        return {"ok": True, **meta}

    def _load_vectorstore(self) -> Optional[FAISS]:
        if not os.path.exists(self.index_dir):
            return None
        return FAISS.load_local(self.index_dir, self.embeddings, allow_dangerous_deserialization=True)

    def search(self, query: str, top_k: int = 5, dry_run: bool = True) -> Dict[str, object]:
        vs = self._load_vectorstore()
        if not vs:
            return {"ok": False, "error": "索引不存在"}
        docs = vs.similarity_search(query, k=top_k)
        results = [
            {
                "source": d.metadata.get("source"),
                "preview": d.page_content[:200],
            }
            for d in docs
        ]
        return {"ok": True, "results": results}

    def repo_summarize(self, dry_run: bool = True) -> Dict[str, object]:
        vs = self._load_vectorstore()
        if not vs:
            return {"ok": False, "error": "索引不存在"}
        docs = vs.similarity_search("项目功能概览", k=6)
        snippets = "\n".join([d.page_content[:300] for d in docs])
        summary = self._llm_or_rule_summary(snippets)
        return {"ok": True, "summary": summary}

    def organize_suggestions(self, dry_run: bool = True) -> Dict[str, object]:
        vs = self._load_vectorstore()
        if not vs:
            return {"ok": False, "error": "索引不存在"}
        docs = vs.similarity_search("目录结构 与 文件整理 建议", k=6)
        snippets = "\n".join([d.page_content[:300] for d in docs])
        suggestions = self._llm_or_rule_suggestions(snippets)
        return {"ok": True, "suggestions": suggestions}

    def qa(self, query: str, top_k: int = 6, dry_run: bool = True) -> Dict[str, object]:
        vs = self._load_vectorstore()
        if not vs:
            return {"ok": False, "error": "索引不存在"}
        docs = vs.similarity_search(query, k=top_k)
        context = "\n".join([f"[{i+1}] {d.page_content}" for i, d in enumerate(docs)])
        answer = self._llm_or_rule_qa(query, context)
        sources = []
        snippets = []
        for d in docs:
            src = d.metadata.get("source") or ""
            if src and src not in sources:
                sources.append(src)
            text = d.page_content or ""
            if len(text) > 2000:
                cut = text.rfind("\n", 0, 2000)
                if cut < 400:
                    cut = 2000
                text = text[:cut] + "\n...<片段截断>"
            snippets.append({"source": src, "content": text})
        return {"ok": True, "answer": answer, "sources": sources, "snippets": snippets}

    def _llm_or_rule_summary(self, context: str) -> str:
        client = LLMClient(load_config(self.workspace))
        prompt = (
            "根据以下仓库片段，输出中文功能概览（不超过 120 字）：\n" + context
        )
        try:
            return client.chat_text(
                [
                    {"role": "system", "content": "你是仓库分析助手"},
                    {"role": "user", "content": prompt},
                ]
            )
        except LLMKeyMissing:
            return "未配置 API Key，使用规则摘要：该仓库包含若干源码与配置文件，可先查看 README 与主要模块。"
        except Exception:
            return "摘要失败，请检查索引与配置。"

    def _llm_or_rule_suggestions(self, context: str) -> str:
        client = LLMClient(load_config(self.workspace))
        prompt = (
            "根据以下仓库片段，给出中文文件整理建议（不超过 5 条）：\n" + context
        )
        try:
            return client.chat_text(
                [
                    {"role": "system", "content": "你是代码库整理顾问"},
                    {"role": "user", "content": prompt},
                ]
            )
        except LLMKeyMissing:
            return "未配置 API Key，规则建议：按模块归档、清理重复文件、补齐 README 与文档目录。"
        except Exception:
            return "建议生成失败，请检查索引与配置。"

    def _llm_or_rule_qa(self, query: str, context: str) -> str:
        client = LLMClient(load_config(self.workspace))
        prompt = (
            "你是仓库问答助手。仅基于给定片段回答，不要编造。\n"
            "如果回答包含代码，请使用 Markdown 代码块并保留换行与缩进。\n"
            f"问题：{query}\n"
            "片段：\n"
            f"{context}\n"
            "若片段不足以回答，请明确说明无法回答。"
        )
        try:
            return client.chat_text(
                [
                    {"role": "system", "content": "你是仓库问答助手"},
                    {"role": "user", "content": prompt},
                ]
            )
        except LLMKeyMissing:
            return "未配置 API Key，无法生成回答。"
        except Exception:
            return "问答失败，请检查索引与配置。"
