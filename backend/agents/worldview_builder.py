"""
世界观构建子 Agent v3 — 流式支持
支持流式返回世界观构建过程
"""
from __future__ import annotations
import json, logging, re
from typing import AsyncGenerator, Optional
import yaml
from pathlib import Path

from core.novel_models import NovelSession, Worldview, WorldSetting, WorldCharacter
from core.llm import LLMClient

log = logging.getLogger(__name__)

_YAML_PATH = Path(__file__).parent / "novel_prompts.yaml"
_cfg: dict = {}


def _load_cfg() -> dict:
    global _cfg
    if not _cfg:
        try:
            _cfg = yaml.safe_load(_YAML_PATH.read_text("utf-8"))
        except Exception as e:
            log.error(f"Failed to load novel_prompts.yaml: {e}")
            _cfg = {}
    return _cfg


class WorldviewBuilder:
    def __init__(self, llm_cfg: dict):
        self.llm_cfg = llm_cfg
        self.llm = LLMClient(llm_cfg)

    async def ask_single_missing(self, session: NovelSession, user_msg: str, assessment: dict) -> str:
        notes = session.collected_info.extra_notes or user_msg
        ack = "听起来很有意思！" if len(notes) > 10 else ""

        if not assessment["has_character"]:
            return (
                f"{ack}我对故事的核心冲突/背景有了大致感觉，"
                "再告诉我**主角**是什么样的人？\n\n"
                "不需要完整介绍——一个让您最着迷的特质就够了，"
                "比如：他的职业、一个性格矛盾点、或者一个独特的能力。"
            )
        elif not assessment["has_genre"]:
            return (
                f"{ack}主角很吸引人！这个故事整体**偏向哪种类型**？\n\n"
                "科幻 · 悬疑 · 言情 · 武侠仙侠 · 奇幻 · 历史 · 都市\n\n"
                "（也可以是混合风格，比如：科幻+悬疑）"
            )
        else:
            return (
                f"{ack}好的，我已经基本了解了！\n\n"
                "最后一个问题：**故事的核心矛盾**是什么？\n"
                "即主角最终需要面对/解决/承受的那件事——一句话就够。"
            )

    async def build_worldview(self, session: NovelSession) -> tuple[Worldview, str]:
        """非流式构建世界观"""
        full_idea = self._collect_user_texts(session)
        system, user_content = self._build_prompt(full_idea)
        raw = await self.llm.chat(system, user_content)
        worldview = self._parse_worldview(raw if isinstance(raw, str) else "")
        reply = self._format_worldview_reply(worldview)
        return worldview, reply

    async def build_worldview_stream(self, session: NovelSession) -> AsyncGenerator[dict, None]:
        """
        流式构建世界观
        yield 格式: {"type": "chunk", "content": "..."} 逐字输出格式化文本
                    {"type": "done", "worldview": {...}, "reply": "..."} 完成
        """
        full_idea = self._collect_user_texts(session)
        system, user_content = self._build_prompt(full_idea)

        # 流式获取 LLM 响应
        stream = await self.llm.chat(system, user_content, stream=True)
        if isinstance(stream, str):
            # 非流式 fallback
            yield {"type": "chunk", "content": stream}
            worldview = self._parse_worldview(stream)
        else:
            # 流式收集原始 JSON
            raw_chunks = []
            display_chunks = []
            in_json = False

            async for chunk in stream:
                raw_chunks.append(chunk)

                # 尝试实时格式化为可读文本
                text = self._format_chunk_for_display(chunk, display_chunks)
                if text:
                    yield {"type": "chunk", "content": text}

            raw = "".join(raw_chunks)
            worldview = self._parse_worldview(raw)

        reply = self._format_worldview_reply(worldview)
        yield {"type": "done", "worldview": worldview.model_dump(), "reply": reply}

    def _collect_user_texts(self, session: NovelSession) -> str:
        user_texts = [m.content for m in session.messages if m.role.value == "user"]
        return "\n".join(user_texts)

    def _build_prompt(self, full_idea: str) -> tuple[str, str]:
        system = _load_cfg().get("worldview", {}).get("build_system", "")
        user_content = (
            f"以下是用户提供的所有创作想法（可能是一段完整描述，也可能是多轮对话积累）：\n\n"
            f"---\n{full_idea}\n---\n\n"
            "请根据以上内容，尽可能完整地提取和推断世界观要素。\n"
            "对于用户未明确说明的字段，根据整体风格合理推断，不要留空。\n"
            "直接输出 JSON，不含其他文字。"
        )
        return system, user_content

    def _format_chunk_for_display(self, chunk: str, display_chunks: list) -> str:
        """将 JSON chunk 转换为可读文本片段"""
        display_chunks.append(chunk)
        full = "".join(display_chunks).strip()

        # 如果还在 JSON 标记之前，跳过
        if full in ("", "{", '{"', "```", "```json"):
            return ""

        # 尝试提取部分关键字段实时显示
        try:
            # 简单的实时提取
            title_match = re.search(r'"title"\s*:\s*"([^"]*)', full)
            if title_match and len(display_chunks) <= 3:
                return f"📖 **标题**: {title_match.group(1)}\n"
        except Exception:
            pass

        return ""

    async def revise_worldview(self, session: NovelSession, user_feedback: str) -> str:
        if not session.worldview:
            return "请先生成世界观。"

        system = (
            "你是小说创作助手，根据用户反馈修改世界观文档。\n"
            "只修改用户指出的部分，保留其余内容不变。\n"
            "输出完整修改后的世界观 JSON，不含其他文字。"
        )
        user_content = (
            f"当前世界观：\n{session.worldview.model_dump_json(indent=2)}\n\n"
            f"用户修改意见：{user_feedback}"
        )
        raw = await self.llm.chat(system, user_content)
        raw_str = raw if isinstance(raw, str) else ""
        updated = self._parse_worldview(raw_str)
        session.worldview = updated
        return f"好的，已根据您的意见更新！\n\n{self._format_worldview_reply(updated)}"

    def _format_worldview_reply(self, wv: Worldview) -> str:
        lines = [f"## 📖 《{wv.title}》世界观设定\n"]
        lines.append(f"**类型**：{wv.genre}　**主题**：{wv.core_theme}")
        lines.append(f"**文风**：{wv.writing_style}　**篇幅**：{wv.target_length}\n")

        ws = wv.world_setting
        if ws.era or ws.geography:
            lines.append("### 🌍 世界背景")
            if ws.era:            lines.append(f"- **时代**：{ws.era}")
            if ws.geography:      lines.append(f"- **地理**：{ws.geography}")
            if ws.special_rules:  lines.append(f"- **特殊设定**：{ws.special_rules}")
            if ws.atmosphere:     lines.append(f"- **基调**：{ws.atmosphere}")
            lines.append("")

        if wv.protagonist:
            p = wv.protagonist
            lines.append(f"### 🧑 主角：{p.name}（{p.age}）")
            if p.background:   lines.append(f"- 背景：{p.background}")
            if p.personality:  lines.append(f"- 性格：{p.personality}")
            if p.ability:      lines.append(f"- 能力：{p.ability}")
            if p.motivation:   lines.append(f"- 动机：{p.motivation}")
            lines.append("")

        if wv.supporting_characters:
            lines.append("### 👥 配角")
            for c in wv.supporting_characters[:3]:
                lines.append(f"- **{c.name}**（{c.role}）：{c.description}")
            lines.append("")

        if wv.core_conflict:
            lines.append(f"### ⚡ 核心矛盾\n{wv.core_conflict}\n")

        if wv.story_hook:
            lines.append(f"### 🪝 开篇钩子\n{wv.story_hook}\n")

        lines.append("---")
        lines.append("以上是完整的世界观设定。**确认无误吗？**\n（告诉我需要修改的地方，或直接回复「确认」进入情节规划）")
        return "\n".join(lines)

    def _parse_worldview(self, raw: str) -> Worldview:
        try:
            clean = re.sub(r"```json\s*|\s*```", "", raw).strip()
            data  = json.loads(clean)
            ws    = WorldSetting.model_validate(data.get("world_setting") or {})
            proto_data  = data.get("protagonist") or {}
            protagonist = WorldCharacter.model_validate(proto_data) if proto_data else None
            supporting  = [
                WorldCharacter.model_validate(c)
                for c in (data.get("supporting_characters") or [])
                if isinstance(c, dict)
            ]
            return Worldview(
                title=data.get("title", ""),
                genre=data.get("genre", ""),
                core_theme=data.get("core_theme", ""),
                world_setting=ws,
                protagonist=protagonist,
                supporting_characters=supporting,
                core_conflict=data.get("core_conflict", ""),
                story_hook=data.get("story_hook", ""),
                themes=data.get("themes") or [],
                writing_style=data.get("writing_style", ""),
                target_length=data.get("target_length", ""),
                production_notes=data.get("production_notes", ""),
            )
        except Exception as e:
            log.error(f"Worldview parse error: {e}\nRaw: {raw[:300]}")
            return Worldview(production_notes=raw[:1000])
