"""
小说写作主 Agent v3 — 流式支持
核心改变：
  - 支持流式输出（AsyncGenerator）
  - chat_stream() 返回 SSE 事件流
  - 保持 chat() 非流式兼容
"""
from __future__ import annotations
import logging
from typing import AsyncGenerator, Optional

from core.novel_models import (
    NovelSession, NovelPhase, MessageRole,
    NovelChatRequest, NovelChatResponse,
    CollectedInfo, Worldview, WorldSetting, WorldCharacter, NovelOutline, ChapterOutline,
)
from core.novel_store import session_save, session_get
from agents.worldview_builder import WorldviewBuilder
from agents.outline_planner import OutlinePlanner
from agents.chapter_writer import ChapterWriter

log = logging.getLogger(__name__)

# 确认 / 继续 / 下一章 关键词
_YES_WORDS   = {"好的","确认","没问题","可以","继续","✓","ok","OK","是","确定","好","行","不错"}
_NEXT_WORDS  = {"下一章","写下一章","继续写","开始下一章"}
_WRITE_WORDS = {"开始写作","开始","写吧","好了","start","go","写"}

# 用户 idea 充分性阈值
_IDEA_SUFFICIENT_LEN = 30


def _assess_idea_richness(msg: str) -> dict:
    genres = ["科幻","奇幻","玄幻","悬疑","惊悚","言情","都市","武侠","仙侠",
              "历史","架空","日常","轻小说","穿越","重生","末世","赛博"]
    char_kw = ["主角","主人公","他","她","男主","女主","我","一个人","少年","少女",
               "男人","女人","侦探","程序员","医生","学生","将军","皇帝"]
    conflict_kw = ["但是","然而","却","发现","遭遇","面对","卷入","被迫","陷入",
                   "秘密","真相","复仇","救","找","逃","追","争","战","死"]

    has_genre     = any(g in msg for g in genres)
    has_character = any(c in msg for c in char_kw)
    has_conflict  = any(c in msg for c in conflict_kw)
    is_long       = len(msg) >= _IDEA_SUFFICIENT_LEN

    rich = is_long and sum([has_genre, has_character, has_conflict]) >= 2

    return {
        "rich": rich,
        "has_genre": has_genre,
        "has_character": has_character,
        "has_conflict": has_conflict,
        "length": len(msg),
    }


class NovelAgent:
    def __init__(self, llm_cfg: dict):
        self.llm_cfg           = llm_cfg
        self.worldview_builder = WorldviewBuilder(llm_cfg)
        self.outline_planner   = OutlinePlanner(llm_cfg)
        self.chapter_writer    = ChapterWriter(llm_cfg)

    def _rebuild_worldview(self, wv_data: dict) -> Worldview:
        """从流式事件数据中重建 Worldview 对象"""
        try:
            ws = WorldSetting.model_validate(wv_data.get("world_setting") or {})
            proto_data = wv_data.get("protagonist") or {}
            protagonist = WorldCharacter.model_validate(proto_data) if proto_data else None
            supporting = [
                WorldCharacter.model_validate(c)
                for c in (wv_data.get("supporting_characters") or [])
            ]
            return Worldview(
                title=wv_data.get("title", ""),
                genre=wv_data.get("genre", ""),
                core_theme=wv_data.get("core_theme", ""),
                world_setting=ws,
                protagonist=protagonist,
                supporting_characters=supporting,
                core_conflict=wv_data.get("core_conflict", ""),
                story_hook=wv_data.get("story_hook", ""),
                writing_style=wv_data.get("writing_style", ""),
            )
        except Exception as e:
            log.error(f"Worldview rebuild error: {e}")
            return Worldview(production_notes=str(wv_data)[:1000])

    def _rebuild_outline(self, outline_data: dict) -> NovelOutline:
        """从流式事件数据中重建 NovelOutline 对象"""
        try:
            chapters = [
                ChapterOutline.model_validate(c)
                for c in (outline_data.get("chapters") or [])
            ]
            return NovelOutline(
                hook=outline_data.get("hook", ""),
                overall_arc=outline_data.get("overall_arc", ""),
                chapters=chapters,
                planned_total_chapters=outline_data.get("planned_total_chapters", 12),
            )
        except Exception as e:
            log.error(f"Outline rebuild error: {e}")
            return NovelOutline()

    async def chat(self, req: NovelChatRequest) -> NovelChatResponse:
        """非流式对话（兼容接口）"""
        session = self._get_or_create_session(req)
        session.add_message(MessageRole.USER, req.message)
        reply, phase_data = await self._route(session, req.message)
        session.add_message(MessageRole.ASSISTANT, reply,
                            metadata={"phase_data": phase_data or {}})
        session_save(session)

        return NovelChatResponse(
            session_id=session.session_id,
            reply=reply,
            phase=session.phase.value,
            phase_data=phase_data,
        )

    async def chat_stream(self, req: NovelChatRequest) -> AsyncGenerator[dict, None]:
        """
        流式对话接口
        yield 格式:
          {"type": "chunk", "content": "..."}           — 逐字内容
          {"type": "phase", "phase": "...", "phase_data": {...}} — 阶段变化
          {"type": "done", "session_id": "...", "phase": "..."}  — 完成
          {"type": "error", "message": "..."}           — 错误
        """
        try:
            session = self._get_or_create_session(req)
            session.add_message(MessageRole.USER, req.message)

            # 发送当前阶段
            yield {"type": "phase", "phase": session.phase.value}

            # 流式处理
            full_reply = ""
            phase_data = None

            async for event in self._route_stream(session, req.message):
                yield event
                if event["type"] == "chunk":
                    full_reply += event.get("content", "")
                elif event["type"] == "phase":
                    phase_data = event.get("phase_data")

            # 保存会话
            session.add_message(MessageRole.ASSISTANT, full_reply,
                                metadata={"phase_data": phase_data or {}})
            session_save(session)

            yield {
                "type": "done",
                "session_id": session.session_id,
                "phase": session.phase.value,
                "phase_data": phase_data,
            }
        except Exception as e:
            log.exception("chat_stream error")
            yield {"type": "error", "message": str(e)}

    def _get_or_create_session(self, req: NovelChatRequest) -> NovelSession:
        session = None
        if req.session_id:
            session = session_get(req.session_id)
        if not session:
            session = NovelSession()
            log.info(f"New session: {session.session_id}")
        return session

    async def _route(self, session: NovelSession, user_msg: str) -> tuple[str, Optional[dict]]:
        """非流式路由（保持兼容）"""
        phase = session.phase

        if phase == NovelPhase.INIT:
            return await self._handle_init(session, user_msg)
        if phase == NovelPhase.COLLECTING:
            return await self._handle_collecting(session, user_msg)
        if phase == NovelPhase.WORLDVIEW_BUILDING:
            return await self._handle_worldview_building(session, user_msg)
        if phase == NovelPhase.WORLDVIEW_REVIEW:
            return await self._handle_worldview_review(session, user_msg)
        if phase in (NovelPhase.WORLDVIEW_CONFIRMED, NovelPhase.OUTLINE_PLANNING):
            return await self._handle_outline_planning(session, user_msg)
        if phase == NovelPhase.OUTLINE_REVIEW:
            return await self._handle_outline_review(session, user_msg)
        if phase in (NovelPhase.OUTLINE_CONFIRMED, NovelPhase.CHAPTER_PREPARING):
            return await self._handle_chapter_start(session, user_msg)
        if phase == NovelPhase.CHAPTER_WRITING:
            return await self._handle_chapter_writing(session, user_msg)
        if phase == NovelPhase.CHAPTER_DONE:
            return await self._handle_chapter_done(session, user_msg)

        return "抱歉，我有点迷失了方向。您能告诉我现在想做什么吗？", None

    async def _route_stream(self, session: NovelSession, user_msg: str) -> AsyncGenerator[dict, None]:
        """流式路由"""
        phase = session.phase

        if phase == NovelPhase.INIT:
            async for e in self._handle_init_stream(session, user_msg):
                yield e
            return
        if phase == NovelPhase.COLLECTING:
            async for e in self._handle_collecting_stream(session, user_msg):
                yield e
            return
        if phase == NovelPhase.WORLDVIEW_BUILDING:
            async for e in self._handle_worldview_stream(session, user_msg):
                yield e
            return
        if phase == NovelPhase.WORLDVIEW_REVIEW:
            async for e in self._handle_worldview_review_stream(session, user_msg):
                yield e
            return
        if phase in (NovelPhase.WORLDVIEW_CONFIRMED, NovelPhase.OUTLINE_PLANNING):
            async for e in self._handle_outline_stream(session, user_msg):
                yield e
            return
        if phase == NovelPhase.OUTLINE_REVIEW:
            async for e in self._handle_outline_review_stream(session, user_msg):
                yield e
            return
        if phase in (NovelPhase.OUTLINE_CONFIRMED, NovelPhase.CHAPTER_PREPARING):
            async for e in self._handle_chapter_start_stream(session, user_msg):
                yield e
            return
        if phase == NovelPhase.CHAPTER_WRITING:
            async for e in self._handle_chapter_writing_stream(session, user_msg):
                yield e
            return
        if phase == NovelPhase.CHAPTER_DONE:
            async for e in self._handle_chapter_done_stream(session, user_msg):
                yield e
            return

        yield {"type": "chunk", "content": "抱歉，我有点迷失了方向。您能告诉我现在想做什么吗？"}

    # ────────────────────────────────────────────────────────
    #  INIT
    # ────────────────────────────────────────────────────────

    async def _handle_init(self, session: NovelSession, user_msg: str) -> tuple[str, Optional[dict]]:
        assessment = _assess_idea_richness(user_msg)
        session.collected_info.extra_notes = user_msg

        if assessment["rich"]:
            session.phase = NovelPhase.WORLDVIEW_BUILDING
            worldview, reply = await self.worldview_builder.build_worldview(session)
            session.worldview = worldview
            if worldview.title:
                session.title = worldview.title
            session.phase = NovelPhase.WORLDVIEW_REVIEW
            session.log("直接从 idea 构建世界观（跳过收集）")
            return reply, {"worldview": worldview.model_dump()}
        else:
            session.phase = NovelPhase.COLLECTING
            reply = await self.worldview_builder.ask_single_missing(session, user_msg, assessment)
            return reply, None

    async def _handle_init_stream(self, session: NovelSession, user_msg: str) -> AsyncGenerator[dict, None]:
        assessment = _assess_idea_richness(user_msg)
        session.collected_info.extra_notes = user_msg

        if assessment["rich"]:
            session.phase = NovelPhase.WORLDVIEW_BUILDING
            yield {"type": "phase", "phase": session.phase.value}

            async for event in self.worldview_builder.build_worldview_stream(session):
                if event["type"] == "chunk":
                    yield event
                elif event["type"] == "done":
                    wv_data = event.get("worldview", {})
                    worldview = self._rebuild_worldview(wv_data)

                    session.worldview = worldview
                    if worldview.title:
                        session.title = worldview.title
                    session.phase = NovelPhase.WORLDVIEW_REVIEW
                    session.log("流式构建世界观完成")

                    yield {
                        "type": "phase",
                        "phase": session.phase.value,
                        "phase_data": {"worldview": wv_data},
                    }
        else:
            session.phase = NovelPhase.COLLECTING
            yield {"type": "phase", "phase": session.phase.value}
            reply = await self.worldview_builder.ask_single_missing(session, user_msg, assessment)
            yield {"type": "chunk", "content": reply}

    # ────────────────────────────────────────────────────────
    #  COLLECTING
    # ────────────────────────────────────────────────────────

    async def _handle_collecting(self, session: NovelSession, user_msg: str) -> tuple[str, Optional[dict]]:
        session.collected_info.extra_notes = (
            session.collected_info.extra_notes + "\n" + user_msg
        ).strip()

        user_turns = sum(1 for m in session.messages if m.role == MessageRole.USER)
        full_text = session.collected_info.extra_notes
        assessment = _assess_idea_richness(full_text)

        if assessment["rich"] or user_turns >= 3:
            session.phase = NovelPhase.WORLDVIEW_BUILDING
            worldview, reply = await self.worldview_builder.build_worldview(session)
            session.worldview = worldview
            if worldview.title:
                session.title = worldview.title
            session.phase = NovelPhase.WORLDVIEW_REVIEW
            session.log(f"世界观构建完成（轮次={user_turns}）")
            return reply, {"worldview": worldview.model_dump()}
        else:
            reply = await self.worldview_builder.ask_single_missing(session, user_msg, assessment)
            return reply, None

    async def _handle_collecting_stream(self, session: NovelSession, user_msg: str) -> AsyncGenerator[dict, None]:
        session.collected_info.extra_notes = (
            session.collected_info.extra_notes + "\n" + user_msg
        ).strip()

        user_turns = sum(1 for m in session.messages if m.role == MessageRole.USER)
        full_text = session.collected_info.extra_notes
        assessment = _assess_idea_richness(full_text)

        if assessment["rich"] or user_turns >= 3:
            session.phase = NovelPhase.WORLDVIEW_BUILDING
            yield {"type": "phase", "phase": session.phase.value}

            async for event in self.worldview_builder.build_worldview_stream(session):
                if event["type"] == "chunk":
                    yield event
                elif event["type"] == "done":
                    wv_data = event.get("worldview", {})
                    worldview = self._rebuild_worldview(wv_data)

                    session.worldview = worldview
                    if worldview.title:
                        session.title = worldview.title
                    session.phase = NovelPhase.WORLDVIEW_REVIEW
                    session.log(f"世界观构建完成（轮次={user_turns}）")
                    yield {"type": "phase", "phase": session.phase.value, "phase_data": {"worldview": wv_data}}
        else:
            reply = await self.worldview_builder.ask_single_missing(session, user_msg, assessment)
            yield {"type": "chunk", "content": reply}

    # ────────────────────────────────────────────────────────
    #  WORLDVIEW
    # ────────────────────────────────────────────────────────

    async def _handle_worldview_building(self, session: NovelSession, user_msg: str) -> tuple[str, Optional[dict]]:
        session.phase = NovelPhase.WORLDVIEW_REVIEW
        worldview, reply = await self.worldview_builder.build_worldview(session)
        session.worldview = worldview
        if worldview.title:
            session.title = worldview.title
        session.log(f"世界观构建完成：{worldview.title}")
        return reply, {"worldview": worldview.model_dump()}

    async def _handle_worldview_stream(self, session: NovelSession, user_msg: str) -> AsyncGenerator[dict, None]:
        session.phase = NovelPhase.WORLDVIEW_REVIEW
        yield {"type": "phase", "phase": session.phase.value}

        async for event in self.worldview_builder.build_worldview_stream(session):
            if event["type"] == "chunk":
                yield event
            elif event["type"] == "done":
                wv_data = event.get("worldview", {})
                worldview = self._rebuild_worldview(wv_data)

                session.worldview = worldview
                if worldview.title:
                    session.title = worldview.title
                session.log(f"世界观构建完成：{worldview.title}")
                yield {"type": "phase", "phase": session.phase.value, "phase_data": {"worldview": wv_data}}

    async def _handle_worldview_review(self, session: NovelSession, user_msg: str) -> tuple[str, Optional[dict]]:
        if not any(w in user_msg for w in _YES_WORDS):
            reply = await self.worldview_builder.revise_worldview(session, user_msg)
            return reply, {"worldview": session.worldview.model_dump() if session.worldview else {}}

        session.phase = NovelPhase.WORLDVIEW_CONFIRMED
        session.log("用户确认世界观")
        session.phase = NovelPhase.OUTLINE_PLANNING
        return await self._handle_outline_planning(session, "")

    async def _handle_worldview_review_stream(self, session: NovelSession, user_msg: str) -> AsyncGenerator[dict, None]:
        if not any(w in user_msg for w in _YES_WORDS):
            reply = await self.worldview_builder.revise_worldview(session, user_msg)
            yield {"type": "chunk", "content": reply}
            yield {"type": "phase", "phase": session.phase.value, "phase_data": {"worldview": session.worldview.model_dump() if session.worldview else {}}}
            return

        session.phase = NovelPhase.WORLDVIEW_CONFIRMED
        session.log("用户确认世界观")
        session.phase = NovelPhase.OUTLINE_PLANNING
        yield {"type": "phase", "phase": session.phase.value}

        async for e in self._handle_outline_stream(session, ""):
            yield e

    # ────────────────────────────────────────────────────────
    #  OUTLINE
    # ────────────────────────────────────────────────────────

    async def _handle_outline_planning(self, session: NovelSession, user_msg: str) -> tuple[str, Optional[dict]]:
        session.phase = NovelPhase.OUTLINE_REVIEW
        outline, reply = await self.outline_planner.plan_initial(session)
        session.outline = outline
        session.log(f"初始大纲规划完成：{len(outline.chapters)} 章")
        return reply, {"outline": outline.model_dump()}

    async def _handle_outline_stream(self, session: NovelSession, user_msg: str) -> AsyncGenerator[dict, None]:
        session.phase = NovelPhase.OUTLINE_REVIEW
        yield {"type": "phase", "phase": session.phase.value}

        async for event in self.outline_planner.plan_initial_stream(session):
            if event["type"] == "chunk":
                yield event
            elif event["type"] == "done":
                outline_data = event.get("outline", {})
                outline = self._rebuild_outline(outline_data)

                session.outline = outline
                session.log(f"初始大纲规划完成：{len(outline.chapters)} 章")
                yield {"type": "phase", "phase": session.phase.value, "phase_data": {"outline": outline_data}}

    async def _handle_outline_review(self, session: NovelSession, user_msg: str) -> tuple[str, Optional[dict]]:
        if not any(w in user_msg for w in (_YES_WORDS | _WRITE_WORDS)):
            reply = await self.outline_planner.revise_outline(session, user_msg)
            return reply, {"outline": session.outline.model_dump() if session.outline else {}}

        session.phase = NovelPhase.OUTLINE_CONFIRMED
        session.log("用户确认大纲")
        session.current_chapter_num = 1
        session.phase = NovelPhase.CHAPTER_PREPARING
        return await self._handle_chapter_start(session, "")

    async def _handle_outline_review_stream(self, session: NovelSession, user_msg: str) -> AsyncGenerator[dict, None]:
        if not any(w in user_msg for w in (_YES_WORDS | _WRITE_WORDS)):
            reply = await self.outline_planner.revise_outline(session, user_msg)
            yield {"type": "chunk", "content": reply}
            yield {"type": "phase", "phase": session.phase.value, "phase_data": {"outline": session.outline.model_dump() if session.outline else {}}}
            return

        session.phase = NovelPhase.OUTLINE_CONFIRMED
        session.log("用户确认大纲")
        session.current_chapter_num = 1
        session.phase = NovelPhase.CHAPTER_PREPARING
        yield {"type": "phase", "phase": session.phase.value}

        async for e in self._handle_chapter_start_stream(session, ""):
            yield e

    # ────────────────────────────────────────────────────────
    #  CHAPTER
    # ────────────────────────────────────────────────────────

    async def _handle_chapter_start(self, session: NovelSession, user_msg: str) -> tuple[str, Optional[dict]]:
        chapter, reply = await self.chapter_writer.prepare_chapter(session)
        session.chapters.append(chapter)
        session.current_chapter_num = chapter.chapter_num
        session.current_scene_id = 1
        session.phase = NovelPhase.CHAPTER_WRITING
        session.log(f"第{chapter.chapter_num}章场景分解完成：{len(chapter.scenes)} 个")
        return reply, {"chapter": chapter.model_dump(), "scene_id": 1}

    async def _handle_chapter_start_stream(self, session: NovelSession, user_msg: str) -> AsyncGenerator[dict, None]:
        chapter, reply = await self.chapter_writer.prepare_chapter(session)
        session.chapters.append(chapter)
        session.current_chapter_num = chapter.chapter_num
        session.current_scene_id = 1
        session.phase = NovelPhase.CHAPTER_WRITING
        session.log(f"第{chapter.chapter_num}章场景分解完成：{len(chapter.scenes)} 个")

        yield {"type": "chunk", "content": reply}
        yield {"type": "phase", "phase": session.phase.value, "phase_data": {"chapter": chapter.model_dump(), "scene_id": 1}}

    async def _handle_chapter_writing(self, session: NovelSession, user_msg: str) -> tuple[str, Optional[dict]]:
        chapter = session.current_chapter
        if not chapter:
            return "找不到当前章节，请重新开始。", None

        current_scene = next(
            (s for s in chapter.scenes if s.scene_id == session.current_scene_id), None
        )

        if current_scene and current_scene.status == "done" and not any(w in user_msg for w in _YES_WORDS):
            reply = await self.chapter_writer.revise_scene(session, current_scene, user_msg)
            return reply, {"scene_id": current_scene.scene_id}

        if current_scene and current_scene.status == "writing":
            current_scene.status = "done"

        next_scene = next((s for s in chapter.scenes if s.status == "pending"), None)

        if next_scene:
            session.current_scene_id = next_scene.scene_id
            next_scene.status = "writing"
            reply = await self.chapter_writer.write_scene(session, next_scene)
            return reply, {"scene_id": next_scene.scene_id, "chapter": chapter.model_dump()}
        else:
            return await self._finish_chapter(session)

    async def _handle_chapter_writing_stream(self, session: NovelSession, user_msg: str) -> AsyncGenerator[dict, None]:
        chapter = session.current_chapter
        if not chapter:
            yield {"type": "chunk", "content": "找不到当前章节，请重新开始。"}
            return

        current_scene = next(
            (s for s in chapter.scenes if s.scene_id == session.current_scene_id), None
        )

        if current_scene and current_scene.status == "done" and not any(w in user_msg for w in _YES_WORDS):
            reply = await self.chapter_writer.revise_scene(session, current_scene, user_msg)
            yield {"type": "chunk", "content": reply}
            yield {"type": "phase", "phase": session.phase.value, "phase_data": {"scene_id": current_scene.scene_id}}
            return

        if current_scene and current_scene.status == "writing":
            current_scene.status = "done"

        next_scene = next((s for s in chapter.scenes if s.status == "pending"), None)

        if next_scene:
            session.current_scene_id = next_scene.scene_id
            next_scene.status = "writing"

            # 流式写场景
            async for event in self.chapter_writer.write_scene_stream(session, next_scene):
                if event["type"] == "chunk":
                    yield event
                elif event["type"] == "done":
                    yield {
                        "type": "phase",
                        "phase": session.phase.value,
                        "phase_data": {"scene_id": next_scene.scene_id, "chapter": chapter.model_dump()},
                    }
        else:
            reply, phase_data = await self._finish_chapter(session)
            yield {"type": "chunk", "content": reply}
            if phase_data:
                yield {"type": "phase", "phase": session.phase.value, "phase_data": phase_data}

    async def _finish_chapter(self, session: NovelSession) -> tuple[str, Optional[dict]]:
        chapter = session.current_chapter
        if not chapter:
            return "章节完成！", None

        chapter.full_content = "\n\n".join(s.content for s in chapter.scenes if s.content)
        chapter.word_count   = len(chapter.full_content)
        chapter.status       = "done"

        if session.outline:
            for ch_outline in session.outline.chapters:
                if ch_outline.chapter_num == chapter.chapter_num:
                    ch_outline.actual_word_count = chapter.word_count
                    ch_outline.status = "done"

        # 自动质量评审（异步，不阻塞）
        review_info = ""
        try:
            from agents.quality_reviewer import QualityReviewer
            reviewer = QualityReviewer(self.llm_cfg)
            wv_text = ""
            if session.worldview:
                wv_text = f"{session.worldview.genre} | {session.worldview.core_theme}"
            prev_ending = ""
            if len(session.chapters) > 1:
                prev_ch = session.chapters[-2]
                if prev_ch.full_content:
                    prev_ending = prev_ch.full_content[-300:]

            review = await reviewer.review_chapter(
                chapter_content=chapter.full_content,
                chapter_num=chapter.chapter_num,
                chapter_title=chapter.title,
                worldview_text=wv_text,
                prev_chapter_ending=prev_ending,
            )
            chapter.review_score = review.overall_score
            chapter.review_data  = review.to_dict()
            review_info = f"\n📝 **质量评分：{review.overall_score}/10 ({review.grade})**"
            if review.suggestions:
                review_info += f"\n💡 建议：{review.suggestions[0]}"
            session.log(f"第{chapter.chapter_num}章质量评审完成：{review.overall_score}/10")
        except Exception as e:
            log.warning(f"Auto review failed: {e}")

        completed_count = sum(1 for c in session.chapters if c.status == "done")
        update_msg = ""
        if completed_count > 0 and completed_count % 3 == 0 and session.outline:
            next_start = completed_count + 1
            next_end   = completed_count + 3
            new_chapters, _ = await OutlinePlanner(self.llm_cfg).append_chapters(
                session, next_start, next_end
            )
            session.outline.chapters.extend(new_chapters)
            update_msg = f"\n\n📊 **大纲动态更新**：第{next_start}-{next_end}章规划已追加！"
            session.log(f"动态大纲更新：第{next_start}-{next_end}章")

        session.phase = NovelPhase.CHAPTER_DONE
        session.log(f"第{chapter.chapter_num}章完成，共{chapter.word_count}字")

        reply = (
            f"🎉 第{chapter.chapter_num}章《{chapter.title}》创作完成！\n"
            f"共{len(chapter.scenes)}个场景，约**{chapter.word_count}字**。{review_info}{update_msg}\n\n"
            "输入「下一章」继续创作，或告诉我需要修改的地方。"
        )
        return reply, {"chapter": chapter.model_dump(), "completed": completed_count}

    async def _handle_chapter_done(self, session: NovelSession, user_msg: str) -> tuple[str, Optional[dict]]:
        if any(w in user_msg for w in _NEXT_WORDS):
            next_num = session.current_chapter_num + 1
            session.current_chapter_num = next_num
            session.phase = NovelPhase.CHAPTER_PREPARING

            if session.outline and not any(c.chapter_num == next_num for c in session.outline.chapters):
                new_chs, _ = await OutlinePlanner(self.llm_cfg).append_chapters(
                    session, next_num, next_num + 2
                )
                session.outline.chapters.extend(new_chs)

            return await self._handle_chapter_start(session, user_msg)
        else:
            return (
                "收到！您想对这章做什么修改呢？\n"
                "您也可以说「下一章」继续创作。",
                None
            )

    async def _handle_chapter_done_stream(self, session: NovelSession, user_msg: str) -> AsyncGenerator[dict, None]:
        if any(w in user_msg for w in _NEXT_WORDS):
            next_num = session.current_chapter_num + 1
            session.current_chapter_num = next_num
            session.phase = NovelPhase.CHAPTER_PREPARING
            yield {"type": "phase", "phase": session.phase.value}

            if session.outline and not any(c.chapter_num == next_num for c in session.outline.chapters):
                new_chs, _ = await OutlinePlanner(self.llm_cfg).append_chapters(
                    session, next_num, next_num + 2
                )
                session.outline.chapters.extend(new_chs)

            async for e in self._handle_chapter_start_stream(session, user_msg):
                yield e
        else:
            yield {"type": "chunk", "content": "收到！您想对这章做什么修改呢？\n您也可以说「下一章」继续创作。"}
