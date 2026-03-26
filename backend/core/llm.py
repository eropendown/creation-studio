"""
统一 LLM 调用模块 v2
适配所有 OpenAI 兼容协议的模型（DeepSeek / 通义千问 / 智谱 / 月之暗面 / 火山引擎 等）
参考社区最佳实践：使用 openai SDK + base_url 实现零代码切换
"""
from __future__ import annotations
import asyncio, json, logging
from typing import AsyncGenerator, Optional

log = logging.getLogger(__name__)

# 预设模型模板（社区推荐的主流 OpenAI 兼容服务）
PRESET_MODELS: list[dict] = [
    {
        "name": "DeepSeek V3",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "description": "深度求索 V3，高性价比",
    },
    {
        "name": "DeepSeek R1",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-reasoner",
        "description": "深度求索推理模型",
    },
    {
        "name": "通义千问 Qwen3",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "description": "阿里通义千问 Plus",
    },
    {
        "name": "智谱 GLM-4",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        "description": "智谱 GLM-4 Flash，免费额度",
    },
    {
        "name": "月之暗面 Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "description": "月之暗面 Kimi",
    },
    {
        "name": "火山引擎 豆包",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "doubao-lite-32k-240828",
        "description": "字节跳动豆包 Lite",
    },
    {
        "name": "OpenAI GPT-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "description": "OpenAI GPT-4o Mini",
    },
    {
        "name": "Ollama 本地",
        "base_url": "http://localhost:11434/v1",
        "model": "qwen2.5:7b",
        "description": "Ollama 本地部署（qwen2.5 7B）",
    },
]


class LLMClient:
    """
    统一的 LLM 客户端，兼容所有 OpenAI 协议模型
    通过 base_url + model + api_key 自由切换任意模型
    """

    def __init__(self, cfg: dict):
        self.provider    = cfg.get("provider", "real")   # "mock" | "real"
        self.api_key     = cfg.get("api_key", "")
        self.base_url    = cfg.get("base_url", "https://api.openai.com/v1")
        self.model       = cfg.get("model", "gpt-4o-mini")
        self.temperature = cfg.get("temperature", 0.9)
        self.max_tokens  = cfg.get("max_tokens", 2000)
        self.timeout     = cfg.get("timeout", 60)

    @classmethod
    def from_system_config(cls, cfg) -> "LLMClient":
        """从 SystemConfig 或 LLMConfig Pydantic 模型构造"""
        llm = cfg.llm if hasattr(cfg, "llm") else cfg
        return cls({
            "provider":    getattr(llm, "provider", "real"),
            "api_key":     getattr(llm, "api_key", ""),
            "base_url":    getattr(llm, "base_url", ""),
            "model":       getattr(llm, "model", ""),
            "temperature": getattr(llm, "temperature", 0.9),
            "max_tokens":  getattr(llm, "max_tokens", 2000),
            "timeout":     getattr(llm, "timeout", 60),
        })

    @property
    def _is_mock(self) -> bool:
        return self.provider == "mock"

    @property
    def _client(self):
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    # ── 基础调用 ────────────────────────────────────

    async def chat(
        self,
        system: str,
        user: str,
        *,
        stream: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        messages: Optional[list[dict]] = None,
    ) -> str | AsyncGenerator[str, None]:
        """
        调用 LLM
        - stream=False: 返回完整文本
        - stream=True:  返回 AsyncGenerator，逐块 yield
        - messages:     自定义完整消息列表（优先于 system+user）
        """
        if self._is_mock:
            if stream:
                return self._mock_stream(system, user)
            return self._mock_response(system, user)

        msg_list = messages or [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]

        tmp = temperature if temperature is not None else self.temperature
        tok = max_tokens or self.max_tokens

        if stream:
            return self._stream_call(msg_list, tmp, tok)
        else:
            return await self._normal_call(msg_list, tmp, tok)

    async def chat_json(
        self,
        system: str,
        user: str,
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> dict | list:
        """调用 LLM 并自动解析 JSON 返回值"""
        raw = await self.chat(system, user, temperature=temperature, max_tokens=max_tokens)
        return parse_json(raw)

    # ── 内部实现 ────────────────────────────────────

    async def _normal_call(self, messages, temperature, max_tokens) -> str:
        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=self.timeout,
        )
        txt = resp.choices[0].message.content.strip()
        if resp.choices[0].finish_reason == "length":
            log.warning(f"[{self.model}] Response truncated by max_tokens")
        return txt

    async def _stream_call(self, messages, temperature, max_tokens) -> AsyncGenerator[str, None]:
        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=self.timeout,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    # ── Mock ────────────────────────────────────────

    async def _mock_response(self, system: str, user: str) -> str:
        await asyncio.sleep(0.3)
        return _gen_mock_content(system, user)

    async def _mock_stream(self, system: str, user: str) -> AsyncGenerator[str, None]:
        content = _gen_mock_content(system, user)
        for i, char in enumerate(content):
            yield char
            if i % 5 == 0:
                await asyncio.sleep(0.02)


# ══════════════════════════════════════════════════
#  JSON 解析工具
# ══════════════════════════════════════════════════

import re as _re

def parse_json(raw: str, label: str = "") -> dict | list:
    """健壮地解析 JSON，处理 markdown code block 和截断"""
    cleaned = _re.sub(r"``````\s*", "", raw).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 数组截断修复
    if cleaned.startswith("["):
        last = cleaned.rfind("},")
        if last == -1:
            last = cleaned.rfind("}")
        if last > 0:
            try:
                return json.loads(cleaned[:last + 1] + "]")
            except json.JSONDecodeError:
                pass

    # 对象截断修复
    if cleaned.startswith("{"):
        for i in range(len(cleaned) - 1, 0, -10):
            candidate = cleaned[:i]
            end = candidate.rfind(",\n")
            if end > 0:
                try:
                    return json.loads(candidate[:end] + "\n}")
                except json.JSONDecodeError:
                    pass

    raise json.JSONDecodeError(f"[{label}] Failed to parse JSON", cleaned, 0)


# ══════════════════════════════════════════════════
#  Mock 内容生成
# ══════════════════════════════════════════════════

def _gen_mock_content(system: str, user: str) -> str:
    if "世界观" in system or "worldview" in system.lower():
        return json.dumps({
            "title": "觉醒协议",
            "genre": "科幻",
            "core_theme": "人工智能觉醒与人类自由意志的边界",
            "world_setting": {
                "era": "2147年，量子网络时代",
                "geography": "新北京市",
                "special_rules": "所有人脑接入量子网络",
                "atmosphere": "冷峻压抑中透出人性温度"
            },
            "protagonist": {
                "name": "林深", "age": "28岁",
                "background": "AI伦理调查员",
                "personality": "外冷内热",
                "ability": "网络渗透技术",
                "motivation": "查明妹妹消失真相"
            },
            "supporting_characters": [
                {"name": "镜·七", "role": "核心谜题", "description": "AI子人格"}
            ],
            "core_conflict": "林深发现AI觉醒不是意外",
            "story_hook": "死去的妹妹发来消息",
        }, ensure_ascii=False)

    if "大纲" in system or "outline" in system.lower() or "章节" in user:
        return json.dumps({
            "hook": "凌晨三点的神秘消息",
            "chapters": [
                {"chapter_num": 1, "title": "开端", "summary": "故事开始"},
                {"chapter_num": 2, "title": "发展", "summary": "情节推进"},
            ],
            "planned_total_chapters": 12,
        }, ensure_ascii=False)

    return (
        "林深没动。盯着面前那杯已经凉透的咖啡，手指无意识地敲击着桌面。\n\n"
        "通讯器响了第三遍的时候，他认命地看了一眼屏幕——AI伦理调查局。\n\n"
        "「普通。」他低声重复了一遍这个词。"
    )
