"""
情节规划子 Agent v2 — 流式支持
负责：初始章节规划 + 每3章动态追加
"""
from __future__ import annotations
import json, logging, re
from typing import AsyncGenerator, Optional
from pathlib import Path
import yaml

from core.novel_models import (
    NovelSession, NovelOutline, ChapterOutline
)
from core.llm import LLMClient

log = logging.getLogger(__name__)
_YAML_PATH = Path(__file__).parent / "novel_prompts.yaml"


def _load_yaml() -> dict:
    try:
        return yaml.safe_load(_YAML_PATH.read_text("utf-8"))
    except Exception:
        return {}


def _worldview_summary(session: NovelSession) -> str:
    if not session.worldview:
        return session.collected_info.model_dump_json()
    wv = session.worldview
    return (
        f"《{wv.title}》\n"
        f"类型：{wv.genre} / 主题：{wv.core_theme}\n"
        f"主角：{wv.protagonist.name if wv.protagonist else '未知'} — {wv.protagonist.motivation if wv.protagonist else ''}\n"
        f"核心矛盾：{wv.core_conflict}\n"
        f"开篇钩子：{wv.story_hook}"
    )


class OutlinePlanner:
    def __init__(self, llm_cfg: dict):
        self.llm_cfg = llm_cfg
        self.llm = LLMClient(llm_cfg)

    async def plan_initial(self, session: NovelSession) -> tuple[NovelOutline, str]:
        """非流式生成初始6章大纲"""
        cfg = _load_yaml()
        system = cfg.get("outline", {}).get("initial_plan_system", "")
        system = system.replace("{worldview_summary}", _worldview_summary(session))
        user = "请为这部小说规划前6章的故事大纲。"

        raw = await self.llm.chat(system, user)
        raw_str = raw if isinstance(raw, str) else ""
        outline = self._parse_outline(raw_str)
        reply = self._format_outline_reply(outline)
        return outline, reply

    async def plan_initial_stream(self, session: NovelSession) -> AsyncGenerator[dict, None]:
        """
        流式生成初始大纲
        yield: {"type": "chunk", "content": "..."} 格式化章节内容
               {"type": "done", "outline": {...}, "reply": "..."}
        """
        cfg = _load_yaml()
        system = cfg.get("outline", {}).get("initial_plan_system", "")
        system = system.replace("{worldview_summary}", _worldview_summary(session))
        user = "请为这部小说规划前6章的故事大纲。"

        stream = await self.llm.chat(system, user, stream=True)
        if isinstance(stream, str):
            yield {"type": "chunk", "content": stream}
            outline = self._parse_outline(stream)
        else:
            raw_chunks = []
            async for chunk in stream:
                raw_chunks.append(chunk)
                # 实时格式化章节信息
                text = self._format_outline_chunk(chunk, raw_chunks)
                if text:
                    yield {"type": "chunk", "content": text}

            raw = "".join(raw_chunks)
            outline = self._parse_outline(raw)

        reply = self._format_outline_reply(outline)
        yield {"type": "done", "outline": outline.model_dump(), "reply": reply}

    def _format_outline_chunk(self, chunk: str, raw_chunks: list) -> str:
        """将 JSON chunk 格式化为可读文本"""
        full = "".join(raw_chunks).strip()
        # 检测到新章节时输出
        if '"title"' in chunk and '"chapter_num"' in full[-200:]:
            try:
                title_match = re.search(r'"title"\s*:\s*"([^"]+)"', chunk)
                num_match = re.search(r'"chapter_num"\s*:\s*(\d+)', full[-300:])
                if title_match and num_match:
                    return f"\n**第{num_match.group(1)}章 · {title_match.group(1)}**\n"
            except Exception:
                pass
        return ""

    async def append_chapters(
        self, session: NovelSession, start: int, end: int
    ) -> tuple[list[ChapterOutline], str]:
        """动态追加章节规划"""
        cfg = _load_yaml()
        system = cfg.get("outline", {}).get("dynamic_update_system", "")

        completed_summary = "\n".join(
            f"第{c.chapter_num}章《{c.title}》：{c.summary[:50]}…"
            for c in (session.outline.chapters if session.outline else [])
            if c.status == "done"
        )

        system = (
            system.replace("{completed_chapters_summary}", completed_summary)
                  .replace("{current_chapter}", str(session.current_chapter_num))
                  .replace("{trigger_chapter}", str(session.current_chapter_num))
                  .replace("{next_start}", str(start))
                  .replace("{next_end}", str(end))
        )

        user = f"请规划第{start}到第{end}章的大纲，延续已完成章节的故事走向。"
        raw = await self.llm.chat(system, user)
        raw_str = raw if isinstance(raw, str) else ""

        try:
            clean = re.sub(r"```json\s*|\s*```", "", raw_str).strip()
            data  = json.loads(clean)
            chapters_data = data if isinstance(data, list) else data.get("chapters", [])
            chapters = [ChapterOutline(**c) for c in chapters_data]
        except Exception as e:
            log.error(f"Outline append parse error: {e}")
            chapters = [
                ChapterOutline(chapter_num=i, title=f"第{i}章", summary="（大纲待规划）")
                for i in range(start, end + 1)
            ]

        update_text = f"第{start}-{end}章大纲已追加。"
        return chapters, update_text

    async def revise_outline(self, session: NovelSession, user_feedback: str) -> str:
        """根据用户反馈修改大纲"""
        if not session.outline:
            return "请先生成大纲。"

        system = (
            "你是小说编剧，根据用户反馈修改章节大纲。\n"
            "只修改用户指出的部分，保持整体结构一致。\n"
            "输出完整修改后的大纲 JSON（格式同初始大纲）。"
        )
        user = (
            f"当前大纲：\n{session.outline.model_dump_json(indent=2)[:2000]}\n\n"
            f"用户意见：{user_feedback}"
        )

        raw = await self.llm.chat(system, user)
        raw_str = raw if isinstance(raw, str) else ""
        updated = self._parse_outline(raw_str)
        session.outline = updated
        return f"好的，已更新大纲！\n\n{self._format_outline_reply(updated)}"

    def _format_outline_reply(self, outline: NovelOutline) -> str:
        lines = ["## 📋 故事大纲\n"]

        if outline.hook:
            lines.append(f"**开篇钩子**：{outline.hook}\n")
        if outline.overall_arc:
            lines.append(f"**情感主线**：{outline.overall_arc}\n")

        lines.append("---")
        for ch in outline.chapters:
            lines.append(f"\n**第{ch.chapter_num}章 · {ch.title}**")
            lines.append(f"{ch.summary}")
            if ch.emotional_arc:
                lines.append(f"_情绪：{ch.emotional_arc}_")
            if ch.foreshadowing:
                lines.append(f"伏笔：{ch.foreshadowing}")
            if ch.ending_hook:
                lines.append(f"章末：{ch.ending_hook}")

        lines.append(f"\n---\n共规划 **{len(outline.chapters)}章**，预计 **{outline.planned_total_chapters}章**完结。")
        lines.append("\n满意的话说「开始写作」，或告诉我需要调整的章节。")
        return "\n".join(lines)

    def _parse_outline(self, raw: str) -> NovelOutline:
        try:
            clean = re.sub(r"```json\s*|\s*```", "", raw).strip()
            data  = json.loads(clean)
            chapters = [
                ChapterOutline.model_validate(c)
                for c in (data.get("chapters") or [])
                if isinstance(c, dict)
            ]
            return NovelOutline(
                hook=data.get("hook", ""),
                overall_arc=data.get("overall_arc", ""),
                chapters=chapters,
                planned_total_chapters=data.get("planned_total_chapters", 12),
            )
        except Exception as e:
            log.error(f"Outline parse error: {e}")
            return NovelOutline(chapters=[
                ChapterOutline(chapter_num=i, title=f"第{i}章", summary="待规划")
                for i in range(1, 7)
            ])
