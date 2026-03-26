"""
统一 LLM 流式调用模块
支持：
  - 流式生成（AsyncGenerator）
  - 非流式调用（兼容已有逻辑）
  - Mock 模式（测试用）
"""
from __future__ import annotations
import asyncio, json, logging
from typing import AsyncGenerator, Optional

log = logging.getLogger(__name__)


class LLMClient:
    """统一的 LLM 客户端，支持流式和非流式调用"""

    def __init__(self, cfg: dict):
        self.provider = cfg.get("provider", "mock")
        self.api_key = cfg.get("api_key", "")
        self.base_url = cfg.get("base_url", "https://api.openai.com/v1")
        self.model = cfg.get("model", "gpt-4o-mini")
        self.temperature = cfg.get("temperature", 0.9)
        self.max_tokens = cfg.get("max_tokens", 2000)
        self.timeout = cfg.get("timeout", 60)

    async def chat(
        self,
        system: str,
        user: str,
        *,
        stream: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str | AsyncGenerator[str, None]:
        """
        调用 LLM
        - stream=False: 返回完整文本
        - stream=True: 返回 AsyncGenerator[str, None]，逐块 yield
        """
        if self.provider == "mock":
            if stream:
                return self._mock_stream(system, user)
            return self._mock_response(system, user)

        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        if stream:
            return self._stream_call(client, messages, temperature, max_tokens)
        else:
            return await self._normal_call(client, messages, temperature, max_tokens)

    async def _normal_call(self, client, messages, temperature, max_tokens) -> str:
        resp = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature if temperature is not None else self.temperature,
            max_tokens=max_tokens or self.max_tokens,
            timeout=self.timeout,
        )
        return resp.choices[0].message.content.strip()

    async def _stream_call(
        self, client, messages, temperature, max_tokens
    ) -> AsyncGenerator[str, None]:
        stream = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature if temperature is not None else self.temperature,
            max_tokens=max_tokens or self.max_tokens,
            timeout=self.timeout,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    async def _mock_response(self, system: str, user: str) -> str:
        """Mock 模式非流式响应"""
        await asyncio.sleep(0.3)
        return _gen_mock_content(system, user)

    async def _mock_stream(self, system: str, user: str) -> AsyncGenerator[str, None]:
        """Mock 模式流式响应"""
        content = _gen_mock_content(system, user)
        # 模拟流式输出：每次输出几个字符
        words = list(content)
        for i, char in enumerate(words):
            yield char
            if i % 5 == 0:
                await asyncio.sleep(0.02)


def _gen_mock_content(system: str, user: str) -> str:
    """根据上下文生成 mock 内容"""
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

    # 默认：场景内容
    return (
        "林深没动。盯着面前那杯已经凉透的咖啡，手指无意识地敲击着桌面。\n\n"
        "通讯器响了第三遍的时候，他认命地看了一眼屏幕——AI伦理调查局。\n\n"
        "「普通。」他低声重复了一遍这个词。"
    )
