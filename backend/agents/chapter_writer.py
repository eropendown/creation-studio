"""
章节创作子 Agent v3 — 流式支持
支持流式返回场景内容
"""
from __future__ import annotations
import json, logging, re
from pathlib import Path
from typing import AsyncGenerator, Optional
import yaml

from core.novel_models import NovelSession, Chapter, SceneTask, ChapterOutline
from core.llm import LLMClient
from agents.agent_tools import AgentToolkit, ToolResult

log = logging.getLogger(__name__)
_YAML_PATH = Path(__file__).parent / "novel_prompts.yaml"


def _load_yaml() -> dict:
    try:
        return yaml.safe_load(_YAML_PATH.read_text("utf-8"))
    except Exception:
        return {}


def _worldview_constraints(session: NovelSession) -> str:
    if not session.worldview:
        return ""
    wv = session.worldview
    lines = [f"世界观：{wv.genre}风格，{wv.world_setting.era}"]
    if wv.protagonist:
        lines.append(f"主角：{wv.protagonist.name}，文风：{wv.writing_style}")
    if wv.world_setting.special_rules:
        lines.append(f"特殊规则：{wv.world_setting.special_rules}")
    return "\n".join(lines)


def _prev_ending(session: NovelSession) -> str:
    chapter = session.current_chapter
    if not chapter:
        return "（这是第一章第一场景，请设计一个强开篇）"

    current_scene_id = session.current_scene_id
    prev_scene = next(
        (s for s in chapter.scenes if s.scene_id == current_scene_id - 1 and s.content),
        None
    )
    if prev_scene and prev_scene.ending_line:
        return prev_scene.ending_line
    if prev_scene and prev_scene.content:
        sentences = [s.strip() for s in re.split(r'[。！？\n]', prev_scene.content) if s.strip()]
        return "。".join(sentences[-2:]) + "。" if sentences else ""

    if len(session.chapters) > 1:
        prev_chapter = session.chapters[-2]
        if prev_chapter.full_content:
            return prev_chapter.full_content[-200:]

    return "（故事开端）"


class ChapterWriter:
    def __init__(self, llm_cfg: dict):
        self.llm_cfg = llm_cfg
        self.llm = LLMClient(llm_cfg)
        self.toolkit = AgentToolkit(llm_cfg)

    async def prepare_chapter(self, session: NovelSession) -> tuple[Chapter, str]:
        """分解章节为场景任务列表"""
        chapter_num = session.current_chapter_num
        cfg_yaml = _load_yaml()

        chapter_outline = None
        if session.outline:
            chapter_outline = next(
                (c for c in session.outline.chapters if c.chapter_num == chapter_num),
                None
            )

        ch_title = chapter_outline.title if chapter_outline else f"第{chapter_num}章"

        system = cfg_yaml.get("writing", {}).get("chapter_start_system", "")
        system = (
            system.replace("{chapter_num}", str(chapter_num))
                  .replace("{chapter_title}", ch_title)
                  .replace("{worldview_summary}", _worldview_constraints(session))
                  .replace("{chapter_outline}", chapter_outline.model_dump_json() if chapter_outline else "")
                  .replace("{previous_ending}", _prev_ending(session))
                  .replace("{scene_count}", "6")
        )

        user = f"请将第{chapter_num}章《{ch_title}》分解为创作场景。"
        raw = await self.llm.chat(system, user)
        raw_str = raw if isinstance(raw, str) else ""
        scenes = self._parse_scenes(raw_str)

        chapter = Chapter(chapter_num=chapter_num, title=ch_title, scenes=scenes)
        reply = self._format_scene_list(chapter)
        return chapter, reply

    async def write_scene(self, session: NovelSession, scene: SceneTask) -> str:
        """非流式创作单个场景"""
        system, user = self._build_scene_prompt(session, scene)
        content = await self.llm.chat(system, user)
        content_str = content if isinstance(content, str) else ""
        return self._finalize_scene(session, scene, content_str)

    async def write_scene_stream(self, session: NovelSession, scene: SceneTask) -> AsyncGenerator[dict, None]:
        """
        流式创作单个场景
        yield: {"type": "chunk", "content": "..."} 逐字输出
               {"type": "done", "content": "...", "scene_id": N}
        """
        # 工具调用阶段（非流式）
        tool_context, tool_log = await self._run_tools(session, scene)
        if tool_log:
            yield {"type": "chunk", "content": f"\n> 🔧 工具辅助：{' · '.join(tool_log)}\n\n"}

        # 流式写作
        system, user = self._build_scene_prompt(session, scene, tool_context)
        stream = await self.llm.chat(system, user, stream=True)

        if isinstance(stream, str):
            yield {"type": "chunk", "content": stream}
            content = stream
        else:
            content_chunks = []
            async for chunk in stream:
                content_chunks.append(chunk)
                yield {"type": "chunk", "content": chunk}
            content = "".join(content_chunks)

        # 完成场景
        final_content = self._finalize_scene(session, scene, content)
        yield {"type": "done", "content": final_content, "scene_id": scene.scene_id}

    async def _run_tools(self, session: NovelSession, scene: SceneTask) -> tuple[str, list[str]]:
        """执行工具调用，返回上下文和日志"""
        tool_context = ""
        tool_log = []
        wv_notes = _worldview_constraints(session)

        suggested_calls = AgentToolkit.needs_tools(scene.goal, wv_notes)
        if suggested_calls:
            log.info(f"Scene {scene.scene_id} triggers {len(suggested_calls)} tool call(s)")
            results = await self.toolkit.call_multiple(suggested_calls)
            for r in results:
                tool_context += r.to_context_block() + "\n\n"
                tool_log.append(f"{r.summary[:60]}" if r.success else f"{r.summary[:60]}")
            session.log(f"场景{scene.scene_id}工具调用：{'; '.join(tool_log)}")

        return tool_context, tool_log

    def _build_scene_prompt(self, session: NovelSession, scene: SceneTask, tool_context: str = "") -> tuple[str, str]:
        """构建场景写作提示"""
        chapter = session.current_chapter
        ch_num = chapter.chapter_num if chapter else session.current_chapter_num

        cfg_yaml = _load_yaml()
        writing_style = session.worldview.writing_style if session.worldview else "简洁有力，短句为主"
        genre = session.collected_info.genre or "现代"

        system = cfg_yaml.get("writing", {}).get("scene_write_system", "")
        system = (
            system.replace("{writing_style}", writing_style)
                  .replace("{genre}", genre)
                  .replace("{chapter_num}", str(ch_num))
                  .replace("{scene_id}", str(scene.scene_id))
                  .replace("{scene_title}", scene.title)
                  .replace("{scene_location}", scene.location)
                  .replace("{scene_time}", scene.time)
                  .replace("{scene_goal}", scene.goal)
                  .replace("{word_count_target}", str(scene.word_count_target))
                  .replace("{worldview_constraints}", _worldview_constraints(session))
                  .replace("{prev_scene_ending}", _prev_ending(session))
        )

        if tool_context:
            system += f"\n\n{tool_context}"

        user = f"请写第{ch_num}章第{scene.scene_id}个场景：{scene.title}"
        return system, user

    def _finalize_scene(self, session: NovelSession, scene: SceneTask, content: str) -> str:
        """完成场景保存和格式化"""
        scene.content = content
        scene.actual_word_count = len(content)
        scene.status = "done"
        sentences = [s.strip() for s in re.split(r'[。！？]', content) if s.strip()]
        scene.ending_line = sentences[-1] + "。" if sentences else ""

        cfg_yaml = _load_yaml()
        done_prompt = cfg_yaml.get("writing", {}).get("scene_done_prompt", "")
        done_msg = (
            done_prompt
            .replace("{scene_id}", str(scene.scene_id))
            .replace("{word_count}", str(len(content)))
        )

        return f"\n\n---\n{done_msg}"

    async def revise_scene(self, session: NovelSession, scene: SceneTask, feedback: str) -> str:
        """根据用户反馈修改场景"""
        tool_context = ""
        suggested_calls = AgentToolkit.needs_tools(feedback)
        if suggested_calls:
            results = await self.toolkit.call_multiple(suggested_calls)
            for r in results:
                tool_context += r.to_context_block() + "\n\n"

        system = (
            "你是小说创作者，根据用户反馈修改场景内容。\n"
            f"原始内容：\n{scene.content[:1000]}\n\n"
            f"用户意见：{feedback}\n\n"
        )
        if tool_context:
            system += f"参考资料（请遵循）：\n{tool_context}\n\n"
        system += "请重写这个场景，保持风格一致，字数相近。直接输出正文。"

        content = await self.llm.chat(system, "请修改这个场景。")
        content_str = content if isinstance(content, str) else ""
        scene.content = content_str
        scene.actual_word_count = len(content_str)
        sentences = [s.strip() for s in re.split(r'[。！？]', content_str) if s.strip()]
        scene.ending_line = sentences[-1] + "。" if sentences else ""

        return f"{content_str}\n\n---\n✅ 场景已修改（约{len(content_str)}字）\n满意的话回复「继续」写下一个场景。"

    def _format_scene_list(self, chapter: Chapter) -> str:
        lines = [
            f"## ✍️ 第{chapter.chapter_num}章《{chapter.title}》",
            f"已分解为 **{len(chapter.scenes)}** 个场景：\n"
        ]
        for s in chapter.scenes:
            chars_str = "、".join(s.characters) if s.characters else "—"
            tool_hint = ""
            if AgentToolkit.needs_tools(s.goal):
                tool_hint = " 🔧"
            lines.append(
                f"**场景{s.scene_id}**：{s.title}{tool_hint}\n"
                f"  📍 {s.location} · ⏰ {s.time} · 👤 {chars_str}\n"
                f"  🎯 {s.goal}\n"
                f"  📝 目标{s.word_count_target}字\n"
            )
        lines.append("---")
        lines.append("场景分解完成！标有 🔧 的场景将在写作时自动调用工具辅助核查。\n\n现在开始写**第一个场景**...")
        return "\n".join(lines)

    def _parse_scenes(self, raw: str) -> list[SceneTask]:
        try:
            clean = re.sub(r"```json\s*|\s*```", "", raw).strip()
            data = json.loads(clean)
            scenes_data = data.get("scenes", data) if isinstance(data, dict) else data
            result = []
            for i, s in enumerate(scenes_data):
                if not isinstance(s, dict):
                    continue
                scene = SceneTask.model_validate({**s, "scene_id": s.get("scene_id", i + 1)})
                result.append(scene)
            return result
        except Exception as e:
            log.error(f"Scene parse error: {e}")
            return [
                SceneTask(scene_id=i+1, title=f"场景{i+1}", goal="待写", word_count_target=400)
                for i in range(5)
            ]
