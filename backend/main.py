"""漫剧 + 小说写作 多智能体 API v6"""
import asyncio, logging, shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from core.models import *
from core.config_store import get_config, save_config, reset_config
from core.outline_store import (
    outline_save, outline_get, outline_list,
    outline_delete, outline_summary_list,
)
from core.novel_models import NovelChatRequest, NovelChatResponse, NovelSessionSummary
from core.novel_store import session_get, session_save, session_summary_list, session_delete
from core.ws_manager import manager
from agents.outline_gen import generate_outline, import_novel
from agents.pipeline_agents import run_voice_actor, run_video_editor
from agents.novel_agent import NovelAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger(__name__)
OUTPUT_DIR = "outputs"
UPLOAD_DIR = "uploads"
_JOBS: dict[str, PipelineState] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    for d in [OUTPUT_DIR, UPLOAD_DIR, "data", "data/outlines", "data/novel_sessions"]:
        Path(d).mkdir(parents=True, exist_ok=True)
    log.info("Server ready — v6 (manga + novel)")
    yield

app = FastAPI(title="创作工作室·多智能体系统", version="6.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# ════════════════════════════════════════════════════════
#  配置 API
# ════════════════════════════════════════════════════════

@app.get("/api/config", response_model=SystemConfig)
async def api_get_config(): return get_config()

@app.post("/api/config", response_model=SystemConfig)
async def api_save_config(req: SaveConfigRequest): return save_config(req.config)

@app.post("/api/config/reset", response_model=SystemConfig)
async def api_reset_config(): return reset_config()


# ════════════════════════════════════════════════════════
#  漫剧大纲 API
# ════════════════════════════════════════════════════════

@app.post("/api/outline", response_model=OutlineResponse)
async def api_create_outline(req: OutlineRequest):
    cfg  = req.config or get_config()
    glog = []
    try:
        outline = await generate_outline(
            genre=req.genre, synopsis=req.synopsis, style=req.style,
            scene_count=req.scene_count, cfg=cfg, glog=glog,
        )
        outline_save(outline)
        return OutlineResponse(outline=outline, message=f"✓ 大纲已生成：{outline.title}")
    except Exception as e:
        log.exception("Outline generation failed")
        raise HTTPException(500, f"大纲生成失败: {e}")


@app.post("/api/outline/novel", response_model=OutlineResponse)
async def api_novel_import(req: NovelImportRequest):
    cfg = req.config or get_config()
    try:
        outline = await import_novel(req, cfg)
        outline_save(outline)
        return OutlineResponse(outline=outline, message=f"✓ 小说导入完成：{outline.title}")
    except Exception as e:
        log.exception("Novel import failed")
        raise HTTPException(500, f"小说导入失败: {e}")


@app.post("/api/outline/novel/upload", response_model=OutlineResponse)
async def api_novel_upload(
    file:        UploadFile = File(...),
    novel_title: str        = Form(default=""),
    style:       str        = Form(default="古风仙侠"),
    scene_count: int        = Form(default=10),
    focus_range: str        = Form(default=""),
):
    if not file.filename.endswith((".txt", ".md", ".text")):
        raise HTTPException(400, "仅支持 .txt / .md 文本文件")
    content = await file.read()
    try:
        novel_text = content.decode("utf-8")
    except UnicodeDecodeError:
        novel_text = content.decode("gbk", errors="replace")

    cfg = get_config()
    req = NovelImportRequest(
        novel_text=novel_text, novel_title=novel_title or file.filename,
        style=style, scene_count=scene_count, focus_range=focus_range,
    )
    outline = await import_novel(req, cfg)
    outline_save(outline)
    return OutlineResponse(outline=outline, message=f"✓ 文件「{file.filename}」导入完成：{outline.title}")


@app.get("/api/outline/{oid}")
async def api_get_outline(oid: str):
    o = outline_get(oid)
    if not o: raise HTTPException(404, "Not found")
    return o.model_dump()


@app.put("/api/outline/{oid}", response_model=OutlineResponse)
async def api_update_outline(oid: str, body: dict):
    o = outline_get(oid)
    if not o: raise HTTPException(404, "Not found")
    updated = ScriptOutline(**{**o.model_dump(), **body})
    outline_save(updated)
    return OutlineResponse(outline=updated, message="大纲已更新")


@app.get("/api/outlines")
async def api_list_outlines():
    return outline_summary_list()


@app.delete("/api/outline/{oid}")
async def api_delete_outline(oid: str):
    ok = outline_delete(oid)
    if not ok: raise HTTPException(404, "Not found")
    return {"ok": True, "deleted": oid}


@app.post("/api/outline/{oid}/scene/{sid}/image")
async def api_upload_scene_image(oid: str, sid: int, file: UploadFile = File(...)):
    o = outline_get(oid)
    if not o: raise HTTPException(404, "Outline not found")
    sc = next((s for s in o.scene_breakdown if s.scene_id == sid), None)
    if not sc: raise HTTPException(404, f"Scene {sid} not found")

    ext      = Path(file.filename).suffix or ".png"
    save_dir = Path(UPLOAD_DIR) / oid
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"scene_{sid:02d}{ext}"
    content   = await file.read()
    save_path.write_bytes(content)

    sc.image_path     = str(save_path)
    sc.image_url      = f"/uploads/{oid}/scene_{sid:02d}{ext}"
    sc.image_uploaded = True
    sc.status         = "image_uploaded"
    outline_save(o)
    return {"ok": True, "image_url": sc.image_url, "scene_id": sid}


@app.post("/api/outline/{oid}/scene/{sid}/image-url")
async def api_scene_image_url(oid: str, sid: int, req: ImageUploadRequest):
    o  = outline_get(oid)
    if not o: raise HTTPException(404, "Not found")
    sc = next((s for s in o.scene_breakdown if s.scene_id == sid), None)
    if not sc: raise HTTPException(404, f"Scene {sid} not found")
    sc.image_url      = req.image_url
    sc.image_uploaded = True
    sc.status         = "image_uploaded"
    outline_save(o)
    return {"ok": True, "scene_id": sid}


# ════════════════════════════════════════════════════════
#  漫剧生成流水线 API
# ════════════════════════════════════════════════════════

async def _run_pipeline(job_id: str, outline: ScriptOutline, cfg: SystemConfig):
    state          = _JOBS[job_id]
    state.outline  = outline
    state.config   = cfg

    async def push(s=None):
        obj = s or state
        await manager.broadcast(obj.job_id, {"type": "state_update", **obj.ws_payload()})

    try:
        await run_voice_actor(state, push, cfg, OUTPUT_DIR)
        state.overall_progress = 60
        await push()
        await run_video_editor(state, push, cfg, OUTPUT_DIR)
    except Exception as e:
        log.exception(f"Pipeline error: {e}")
        state.overall_status  = "error"
        state.error_message   = str(e)
        await push()


@app.post("/api/generate", response_model=GenerateResponse)
async def api_generate(req: GenerateRequest, bg: BackgroundTasks):
    outline = outline_get(req.outline_id)
    if not outline: raise HTTPException(404, f"Outline {req.outline_id} not found")
    cfg = req.config or get_config()

    state = PipelineState()
    state.overall_status = "running"
    _JOBS[state.job_id]  = state
    outline.outline_status = "generating"
    outline_save(outline)

    bg.add_task(_run_pipeline, state.job_id, outline, cfg)
    return GenerateResponse(
        job_id=state.job_id,
        message=f"正在生成「{outline.title}」…",
        ws_url=f"ws://localhost:8000/ws/{state.job_id}",
    )


@app.get("/api/jobs")
async def api_jobs():
    return {"jobs": [
        {"job_id": s.job_id, "title": s.outline.title if s.outline else "", "status": s.overall_status, "progress": s.overall_progress}
        for s in _JOBS.values()
    ]}


@app.get("/api/jobs/{jid}")
async def api_job(jid: str):
    s = _JOBS.get(jid)
    if not s: raise HTTPException(404, "Not found")
    return s.ws_payload()


@app.get("/api/jobs/{jid}/download")
async def api_download(jid: str):
    s = _JOBS.get(jid)
    if not s or not s.final_video_url: raise HTTPException(404, "Video not ready")
    p = Path(OUTPUT_DIR) / jid / "final.mp4"
    if not p.exists(): raise HTTPException(404, "File missing")
    return FileResponse(str(p), media_type="video/mp4", filename=f"manga_{jid}.mp4")


# ════════════════════════════════════════════════════════
#  小说写作 Agent API  (NEW)
# ════════════════════════════════════════════════════════

def _get_novel_agent() -> NovelAgent:
    cfg = get_config()
    llm_cfg = {
        "provider":    cfg.llm.provider,
        "api_key":     cfg.llm.api_key,
        "base_url":    cfg.llm.base_url,
        "model":       cfg.llm.model,
        "temperature": cfg.llm.temperature,
        "max_tokens":  cfg.llm.max_tokens,
    }
    return NovelAgent(llm_cfg)


# ── 灵感服务 ──────────────────────────────────────────────

class InspirationRequest(BaseModel):
    idea:  str = Field(..., min_length=3, description="用户的小说创意描述")
    genre: str = ""


@app.post("/api/novel/chat", response_model=NovelChatResponse)
async def api_novel_chat(req: NovelChatRequest):
    """
    小说写作对话接口（非流式）
    - session_id 为空时自动创建新会话
    - 返回 AI 回复 + 当前阶段 + 阶段数据
    """
    try:
        agent = _get_novel_agent()
        return await agent.chat(req)
    except Exception as e:
        log.exception("Novel chat failed")
        raise HTTPException(500, f"小说创作失败: {e}")


@app.post("/api/novel/chat/stream")
async def api_novel_chat_stream(req: NovelChatRequest):
    """
    小说写作对话接口（流式 SSE）
    返回 Server-Sent Events 流
    """
    from fastapi.responses import StreamingResponse
    import json

    async def event_stream():
        try:
            agent = _get_novel_agent()
            async for event in agent.chat_stream(req):
                # SSE 格式: data: {...}\n\n
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            log.exception("Novel chat stream failed")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/novel/inspiration")
async def api_novel_inspiration(req: InspirationRequest):
    """
    灵感引擎：根据创意返回参考作品卡片。
    完全独立于对话会话，不影响写作流程。
    带 30 分钟缓存，相同 idea 不重复调用 LLM。
    """
    try:
        from agents.inspiration_engine import InspirationEngine
        cfg = get_config()
        llm_cfg = {
            "provider": cfg.llm.provider,
            "api_key":  cfg.llm.api_key,
            "base_url": cfg.llm.base_url,
            "model":    cfg.llm.model,
        }
        engine = InspirationEngine(llm_cfg)
        result = await engine.get_inspiration(req.idea)
        return result.to_dict()
    except Exception as e:
        log.exception("Inspiration engine failed")
        raise HTTPException(500, f"灵感引擎失败: {e}")


@app.get("/api/novel/sessions")
async def api_novel_sessions():
    """列出所有小说会话（摘要）"""
    return session_summary_list()


@app.get("/api/novel/sessions/{sid}")
async def api_novel_session(sid: str):
    s = session_get(sid)
    if not s: raise HTTPException(404, "Session not found")
    return s.model_dump()


@app.delete("/api/novel/sessions/{sid}")
async def api_novel_delete_session(sid: str):
    ok = session_delete(sid)
    if not ok: raise HTTPException(404, "Not found")
    return {"ok": True}


@app.get("/api/novel/sessions/{sid}/export")
async def api_novel_export(sid: str):
    """导出小说全文（Markdown 格式）"""
    s = session_get(sid)
    if not s: raise HTTPException(404, "Session not found")

    lines = [f"# {s.title or '未命名小说'}\n"]
    if s.worldview:
        lines.append(f"> {s.worldview.core_theme}\n")

    for ch in sorted(s.chapters, key=lambda c: c.chapter_num):
        lines.append(f"\n## 第{ch.chapter_num}章 {ch.title}\n")
        if ch.full_content:
            lines.append(ch.full_content)
        else:
            for sc in ch.scenes:
                if sc.content:
                    lines.append(sc.content)

    content = "\n".join(lines)
    total_words = sum(c.word_count for c in s.chapters)

    # 写入临时文件
    export_path = Path("outputs") / f"novel_{sid}.md"
    export_path.write_text(content, "utf-8")

    return FileResponse(
        str(export_path),
        media_type="text/markdown",
        filename=f"{s.title or 'novel'}_{sid}.md",
        headers={"X-Total-Words": str(total_words)}
    )


# ════════════════════════════════════════════════════════
#  小说 → 漫剧 直通导入  (NEW)
# ════════════════════════════════════════════════════════

class NovelToMangaRequest(BaseModel):
    session_id:  str
    style:       str = "古风仙侠"
    scene_count: int = Field(default=10, ge=3, le=30)
    focus_range: str = ""   # 可选：指定重点改编的章节范围，如"第1-3章"


@app.post("/api/novel/sessions/{sid}/to-manga", response_model=OutlineResponse)
async def api_novel_to_manga(sid: str, req: NovelToMangaRequest):
    """
    将小说会话直接导入为漫剧大纲。
    自动提取：
      - 标题、类型、人物、世界观 → 基础信息
      - 所有已完成章节的正文    → 作为小说原文输入
    """
    s = session_get(sid)
    if not s:
        raise HTTPException(404, "小说会话不存在")

    # 收集正文
    full_text_parts = []
    for ch in sorted(s.chapters, key=lambda c: c.chapter_num):
        if ch.full_content:
            full_text_parts.append(f"【第{ch.chapter_num}章 {ch.title}】\n{ch.full_content}")
        else:
            for sc in ch.scenes:
                if sc.content:
                    full_text_parts.append(sc.content)

    if not full_text_parts:
        raise HTTPException(400, "该小说会话暂无已完成的章节内容，请先完成至少一章的创作")

    novel_text = "\n\n".join(full_text_parts)

    # 构建导入请求，带入世界观信息
    wv = s.worldview
    novel_title = s.title or (wv.title if wv else "未命名小说")
    extra_notes = ""
    if wv:
        extra_notes = (
            f"【世界观背景】{wv.world_setting.era} · {wv.world_setting.atmosphere}\n"
            f"【核心冲突】{wv.core_conflict}\n"
            f"【主角】{wv.protagonist.name if wv.protagonist else ''}"
        )

    cfg = get_config()
    import_req = NovelImportRequest(
        novel_text=novel_text + ("\n\n" + extra_notes if extra_notes else ""),
        novel_title=novel_title,
        style=req.style,
        scene_count=req.scene_count,
        focus_range=req.focus_range,
    )

    try:
        outline = await import_novel(import_req, cfg)
        outline.source_type  = "novel"
        outline.source_title = novel_title
        outline_save(outline)
        log.info(f"Novel→Manga import: session={sid} → outline={outline.outline_id}")
        return OutlineResponse(
            outline=outline,
            message=f"✓ 《{novel_title}》已导入为漫剧大纲，共{outline.total_scenes}个分镜"
        )
    except Exception as e:
        log.exception("Novel to manga import failed")
        raise HTTPException(500, f"导入失败: {e}")


# ════════════════════════════════════════════════════════
#  工具调用独立测试接口（可选，供调试）
# ════════════════════════════════════════════════════════

class ToolCallRequest(BaseModel):
    tool:  str   # web_search | python_exec | knowledge_check
    query: str


@app.post("/api/tools/call")
async def api_tool_call(req: ToolCallRequest):
    """直接测试工具调用"""
    from agents.agent_tools import AgentToolkit
    cfg = get_config()
    llm_cfg = {
        "provider": cfg.llm.provider,
        "api_key":  cfg.llm.api_key,
        "base_url": cfg.llm.base_url,
        "model":    cfg.llm.model,
    }
    toolkit = AgentToolkit(llm_cfg)
    result  = await toolkit.call(req.tool, req.query)
    return {
        "tool":    result.tool,
        "success": result.success,
        "summary": result.summary,
        "content": result.content,
    }


# ════════════════════════════════════════════════════════
#  WebSocket
# ════════════════════════════════════════════════════════

@app.websocket("/ws/{jid}")
async def ws_manga(ws: WebSocket, jid: str):
    """漫剧任务进度推送"""
    await manager.connect(jid, ws)
    try:
        s = _JOBS.get(jid)
        if s: await ws.send_json({"type": "state_update", **s.ws_payload()})
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=25)
                if msg == "ping": await ws.send_text("pong")
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.debug(f"WS manga: {e}")
    finally:
        await manager.disconnect(jid, ws)


# ════════════════════════════════════════════════════════
#  健康检查
# ════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {
        "status":  "ok",
        "version": "6.0.0",
        "modules": ["manga", "novel"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)