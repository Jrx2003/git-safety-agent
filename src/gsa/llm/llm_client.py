from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import httpx
import yaml


GLM_MODEL = "glm-4.7"


@dataclass
class LLMConfig:
    api_key: str = ""
    model: str = GLM_MODEL
    max_tokens: int = 65536
    temperature: float = 1.0
    thinking_enabled: bool = True
    base_url: str = "https://api.z.ai/api/paas/v4/"
    timeout: float = 300.0
    connect_timeout: float = 8.0
    max_retries: int = 2


class LLMKeyMissing(RuntimeError):
    pass




def load_config(workspace: Optional[str] = None) -> LLMConfig:
    """从环境变量与 config.yaml 读取配置。"""
    api_key = os.environ.get("BIGMODEL_API_KEY", "") or os.environ.get("ZAI_API_KEY", "")
    env_base_url = os.environ.get("ZAI_BASE_URL", "") or os.environ.get("BIGMODEL_BASE_URL", "")
    config_paths = []
    if workspace:
        config_paths.append(os.path.join(workspace, "config.yaml"))
        config_paths.append(os.path.join(workspace, ".gsa", "config.yaml"))
    config_paths.append(os.path.expanduser("~/.gsa/config.yaml"))

    cfg = LLMConfig()
    if env_base_url:
        cfg.base_url = env_base_url

    for path in config_paths:
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                if data.get("BIGMODEL_API_KEY"):
                    api_key = str(data.get("BIGMODEL_API_KEY"))
                if data.get("GLM_MAX_TOKENS"):
                    cfg.max_tokens = int(data.get("GLM_MAX_TOKENS"))
                if data.get("GLM_TEMPERATURE"):
                    cfg.temperature = float(data.get("GLM_TEMPERATURE"))
                if data.get("GLM_THINKING_ENABLED") is not None:
                    cfg.thinking_enabled = bool(data.get("GLM_THINKING_ENABLED"))
                if data.get("GLM_BASE_URL"):
                    cfg.base_url = str(data.get("GLM_BASE_URL"))
                if data.get("GLM_TIMEOUT"):
                    cfg.timeout = float(data.get("GLM_TIMEOUT"))
                if data.get("GLM_CONNECT_TIMEOUT"):
                    cfg.connect_timeout = float(data.get("GLM_CONNECT_TIMEOUT"))
                if data.get("GLM_MAX_RETRIES") is not None:
                    cfg.max_retries = int(data.get("GLM_MAX_RETRIES"))
        except Exception:
            continue

    cfg.api_key = api_key
    return cfg


def _extract_content(response: Any) -> str:
    if response is None:
        return ""
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")
    if not choices:
        return ""
    first = choices[0]
    message = getattr(first, "message", None)
    if message is None and isinstance(first, dict):
        message = first.get("message", {})
    if isinstance(message, dict):
        return message.get("content", "") or ""
    return getattr(message, "content", "") or ""


class LLMClient:
    """GLM-4.7 客户端（基于 zai-sdk）。"""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self._client = None

    def _ensure_key(self) -> None:
        if not self.config.api_key:
            raise LLMKeyMissing(
                "缺少 BIGMODEL_API_KEY，请在环境变量或 config.yaml 中配置。"
            )

    def _get_client(self):
        if self._client is None:
            from zai import ZaiClient, ZhipuAiClient
            timeout = httpx.Timeout(timeout=self.config.timeout, connect=self.config.connect_timeout)
            ClientClass = ZhipuAiClient if "open.bigmodel.cn" in self.config.base_url else ZaiClient
            self._client = ClientClass(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=timeout,
                max_retries=self.config.max_retries,
            )
        return self._client

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Any:
        self._ensure_key()
        client = self._get_client()
        return client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=temperature if temperature is not None else self.config.temperature,
            max_tokens=max_tokens if max_tokens is not None else self.config.max_tokens,
            thinking={"type": "enabled"} if self.config.thinking_enabled else None,
        )

    def chat_text(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        resp = self.chat(messages, temperature=temperature, max_tokens=max_tokens)
        return _extract_content(resp)

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Iterable[str]:
        self._ensure_key()
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=temperature if temperature is not None else self.config.temperature,
            max_tokens=max_tokens if max_tokens is not None else self.config.max_tokens,
            thinking={"type": "enabled"} if self.config.thinking_enabled else None,
            stream=True,
        )
        for chunk in response:
            try:
                delta = chunk.choices[0].delta
                if getattr(delta, "content", None):
                    yield delta.content
            except Exception:
                continue
