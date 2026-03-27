"""
Pipeline Agents v7 — 配音 + 视频生成 + 剪辑
- TTS: edge_tts(默认免费) | openai | elevenlabs | volcengine
- 视频: 支持用户上传视频、火山引擎 Seedance AI 生成
- 剪辑: 剪映草稿 / MoviePy 合成
"""
import asyncio, base64, json, logging, math, os, struct, time, wave
from pathlib import Path
from typing import Callable
from core.models import PipelineState, AgentStatus, SceneItem, SystemConfig

log = logging.getLogger(__name__)

def _ag(state, name): return state.agents[name]
def _done(ag, msg):   ag.status, ag.finished_at, ag.message, ag.progress = AgentStatus.DONE,  time.time(), msg, 100
def _err(ag, msg):    ag.status, ag.finished_at, ag.message              = AgentStatus.ERROR, time.time(), msg


# ══════════════════════════════════════════════════
#  TTS 配音
# ══════════════════════════════════════════════════

# edge-tts 情绪→音色映表（中文神经网络音色）
_EDGE_VOICE_MAP = {
    "震惊": "zh-CN-YunxiNeural",     # 元气男声
    "愤怒": "zh-CN-YunjianNeural",   # 沉稳男声
    "柔情": "zh-CN-XiaoyiNeural",    # 温柔女声
    "紧张": "zh-CN-YunxiNeural",
    "释然": "zh-CN-XiaochenNeural",  # 成熟知性女声
    "悲伤": "zh-CN-XiaohanNeural",   # 温暖女声
    "喜悦": "zh-CN-XiaoxiaoNeural",  # 活泼女声
    "坚定": "zh-CN-YunjianNeural",
    "迷茫": "zh-CN-XiaoyiNeural",
}

# OpenAI 情绪→音色映表
_OPENAI_VOICE_MAP = {
    "震惊":"nova","愤怒":"onyx","柔情":"shimmer","紧张":"nova",
    "释然":"alloy","悲伤":"shimmer","喜悦":"echo","坚定":"onyx","迷茫":"alloy",
}


async def _edge_tts(sc: SceneItem, out: str, cfg) -> float:
    """edge-tts — 免费 Microsoft Edge 中文神经网络语音（GitHub 15k+ stars）"""
    import edge_tts
    voice = _EDGE_VOICE_MAP.get(sc.emotion, cfg.voice_id or "zh-CN-YunxiNeural")
    rate  = f"+{int((cfg.speed - 1.0) * 100)}%" if cfg.speed != 1.0 else "+0%"

    communicate = edge_tts.Communicate(sc.narration, voice, rate=rate)
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    await communicate.save(out)
    return max(Path(out).stat().st_size / (128_000 / 8), 1.0)


async def _openai_tts(sc: SceneItem, out: str, cfg) -> float:
    from openai import AsyncOpenAI
    voice  = _OPENAI_VOICE_MAP.get(sc.emotion, cfg.voice_id)
    client = AsyncOpenAI(api_key=cfg.api_key)
    resp   = await client.audio.speech.create(
        model=cfg.model, voice=voice, input=sc.narration,
        response_format="mp3", speed=cfg.speed,
    )
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(resp.content)
    return max(Path(out).stat().st_size / (128_000/8), 1.0)


async def _elevenlabs_tts(sc: SceneItem, out: str, cfg) -> float:
    import httpx
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{cfg.voice_id}",
            headers={"xi-api-key": cfg.api_key},
            json={"text": sc.narration, "model_id": "eleven_multilingual_v2",
                  "voice_settings": {"stability": .55, "similarity_boost": .8}},
        )
        r.raise_for_status()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(r.content)
    return max(len(r.content) / (128_000/8), 1.0)


async def _volcengine_tts(sc: SceneItem, out: str, cfg) -> float:
    """火山引擎 TTS — 字节跳动语音合成服务"""
    import httpx
    app_id     = cfg.volcengine_app_id
    access_key = cfg.volcengine_access_key
    secret_key = cfg.volcengine_secret_key
    cluster    = cfg.volcengine_cluster or "volcano_tts"

    if not all([app_id, access_key, secret_key]):
        raise ValueError("火山引擎 TTS 需要配置 app_id / access_key / secret_key")

    # 火山引擎 TTS WebSocket RESTful 接口
    url = "https://openspeech.bytedance.com/api/v1/tts"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer;{access_key}",
    }
    body = {
        "app": {"appid": app_id, "token": access_key, "cluster": cluster},
        "user": {"uid": "comic_studio"},
        "audio": {
            "voice_type": cfg.voice_id or "zh_female_shuangkuaisisi_moon_bigtts",
            "encoding": "mp3",
            "speed_ratio": cfg.speed,
        },
        "request": {
            "reqid": str(time.time()),
            "operation": "query",
            "text": sc.narration,
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

    if data.get("code") != 0:
        raise ValueError(f"火山引擎 TTS 错误: {data.get('message', 'unknown')}")

    audio_b64 = data.get("data", "")
    audio_bytes = base64.b64decode(audio_b64)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(audio_bytes)
    return max(len(audio_bytes) / (128_000 / 8), 1.0)


async def run_voice_actor(
    state: PipelineState, push: Callable, cfg: SystemConfig, output_dir: str
) -> PipelineState:
    ag = _ag(state, "voice_actor")
    ag.status, ag.started_at, ag.progress, ag.message = AgentStatus.RUNNING, time.time(), 0, "生成配音..."
    await push(state)

    scenes = state.outline.scene_breakdown
    total  = len(scenes)
    tts    = cfg.tts

    async def proc(sc: SceneItem):
        ext = "mp3"
        out = str(Path(output_dir) / state.job_id / f"audio_{sc.scene_id:02d}.{ext}")
        try:
            if   tts.provider == "edge_tts":   dur = await _edge_tts(sc, out, tts)
            elif tts.provider == "openai":     dur = await _openai_tts(sc, out, tts)
            elif tts.provider == "elevenlabs": dur = await _elevenlabs_tts(sc, out, tts)
            elif tts.provider == "volcengine": dur = await _volcengine_tts(sc, out, tts)
            else: raise ValueError(f"未知 TTS 提供商: {tts.provider}")
            sc.audio_path     = out
            sc.audio_duration = dur
            sc.audio_uploaded = True
        except Exception as e:
            log.error(f"TTS scene {sc.scene_id}: {e}")
            sc.error_msg = str(e)

    try:
        done  = 0
        tasks = [asyncio.create_task(proc(s)) for s in scenes]
        for t in asyncio.as_completed(tasks):
            await t; done += 1
            ag.progress = int(done / total * 100)
            ag.message  = f"配音 {done}/{total}"
            await push(state)
        _done(ag, f"✓ {total} 个完成")
        state.overall_progress = 60
        await push(state)
        return state
    except Exception as e:
        _err(ag, f"✗ {e}"); raise


# ══════════════════════════════════════════════════
#  火山引擎 Seedance 视频生成
# ══════════════════════════════════════════════════

async def run_video_generator(
    state: PipelineState, push: Callable, cfg: SystemConfig, output_dir: str
) -> PipelineState:
    """对每个分镜场景，用火山引擎 Seedance 生成短视频片段"""
    ag = _ag(state, "video_gen")
    vid_cfg = cfg.video

    if not vid_cfg.volcengine_api_key:
        ag.status = AgentStatus.IDLE
        ag.message = "跳过（未配置火山引擎 API Key）"
        await push(state)
        return state

    ag.status, ag.started_at, ag.progress, ag.message = AgentStatus.RUNNING, time.time(), 0, "AI 视频生成中..."
    await push(state)

    import httpx
    scenes = [s for s in state.outline.scene_breakdown if not s.video_uploaded]
    total  = len(scenes)
    if total == 0:
        _done(ag, "✓ 全部已有视频")
        await push(state)
        return state

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {vid_cfg.volcengine_api_key}",
    }

    async def gen_video(sc: SceneItem):
        """提交视频生成任务并轮询等待结果"""
        prompt = sc.visual_description or sc.narration
        if not prompt:
            return

        body = {
            "model": vid_cfg.volcengine_model or "seedance-2.0",
            "content": [{"type": "text", "text": prompt}],
        }
        # 如果有图片，作为首帧参考
        if sc.image_path and os.path.exists(sc.image_path):
            img_b64 = base64.b64encode(Path(sc.image_path).read_bytes()).decode()
            body["content"].insert(0, {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_b64}"},
            })

        async with httpx.AsyncClient(timeout=60) as client:
            # 提交任务
            resp = await client.post(vid_cfg.volcengine_base_url, headers=headers, json=body)
            resp.raise_for_status()
            task_data = resp.json()
            task_id = task_data.get("id", "")
            if not task_id:
                log.error(f"No task_id returned for scene {sc.scene_id}")
                return

            sc.video_task_id = task_id
            sc.video_status  = "generating"
            state.volcengine_tasks[str(sc.scene_id)] = task_id

            # 轮询任务状态（最多 10 分钟）
            poll_url = f"{vid_cfg.volcengine_base_url}/{task_id}"
            for _ in range(60):
                await asyncio.sleep(10)
                poll_resp = await client.get(poll_url, headers=headers)
                poll_data = poll_resp.json()
                status = poll_data.get("status", "")

                if status == "succeeded":
                    # 获取视频 URL
                    result = poll_data.get("result", {})
                    video_url = ""
                    if isinstance(result, list):
                        for item in result:
                            if item.get("type") == "video_url":
                                video_url = item.get("video_url", {}).get("url", "")
                                break
                    elif isinstance(result, dict):
                        video_url = result.get("video_url", "")

                    if video_url:
                        # 下载视频
                        vid_resp = await client.get(video_url)
                        vid_path = str(Path(output_dir) / state.job_id / f"video_{sc.scene_id:02d}.mp4")
                        Path(vid_path).parent.mkdir(parents=True, exist_ok=True)
                        Path(vid_path).write_bytes(vid_resp.content)
                        sc.video_path    = vid_path
                        sc.video_url     = f"/outputs/{state.job_id}/video_{sc.scene_id:02d}.mp4"
                        sc.video_uploaded = True
                        sc.video_status  = "done"
                    break
                elif status == "failed":
                    sc.video_status = "error"
                    sc.error_msg = poll_data.get("error", {}).get("message", "视频生成失败")
                    break

    try:
        done  = 0
        tasks = [asyncio.create_task(gen_video(s)) for s in scenes]
        for t in asyncio.as_completed(tasks):
            await t; done += 1
            ag.progress = int(done / total * 100)
            ag.message  = f"视频生成 {done}/{total}"
            await push(state)
        _done(ag, f"✓ {total} 个视频完成")
        state.overall_progress = 80
        await push(state)
        return state
    except Exception as e:
        _err(ag, f"✗ {e}"); raise


# ══════════════════════════════════════════════════
#  VIDEO EDITOR
# ══════════════════════════════════════════════════

def _moviepy(state: PipelineState, out_path: str, vid_cfg):
    import os
    from moviepy.editor import (
        VideoFileClip, ImageClip, AudioFileClip, TextClip,
        CompositeVideoClip, concatenate_videoclips
    )
    clips = []
    for sc in state.outline.scene_breakdown:
        has_video = sc.video_path and os.path.exists(sc.video_path)
        has_image = sc.image_path and os.path.exists(sc.image_path)
        has_audio = sc.audio_path and os.path.exists(sc.audio_path)

        if not has_video and not has_image:
            continue

        try:
            if has_video:
                # 使用 AI 生成的视频或用户上传的视频
                vc = VideoFileClip(sc.video_path)
                if has_audio:
                    audio = AudioFileClip(sc.audio_path)
                    dur   = max(vc.duration, audio.duration)
                    vc = vc.set_duration(dur).set_audio(audio)
                else:
                    dur = vc.duration
            else:
                # 使用图片 + 音频合成
                audio = AudioFileClip(sc.audio_path) if has_audio else None
                dur   = audio.duration if audio else sc.duration_estimate
                vc    = ImageClip(sc.image_path).set_duration(dur)
                if audio:
                    vc = vc.set_audio(audio)

            if vid_cfg.subtitle_enabled and sc.narration:
                try:
                    txt = TextClip(
                        sc.narration, fontsize=vid_cfg.subtitle_font_size,
                        color="white", bg_color="rgba(0,0,0,0.55)",
                        font="DejaVu-Sans", method="caption",
                        size=(vc.w - 40, None),
                    ).set_duration(dur).set_position(("center", vc.h - 70))
                    vc = CompositeVideoClip([vc, txt])
                except Exception as e:
                    log.warning(f"Subtitle failed scene {sc.scene_id}: {e}")
            clips.append(vc)
        except Exception as e:
            log.error(f"Clip {sc.scene_id}: {e}")

    if not clips:
        raise ValueError("No valid clips")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    concatenate_videoclips(clips, method="compose").write_videofile(
        out_path, fps=vid_cfg.fps, codec="libx264", audio_codec="aac", logger=None
    )


def _jianying(state: PipelineState, output_dir: str, vid_cfg) -> str:
    import os, uuid as _uuid
    US       = 1_000_000
    draft_id = _uuid.uuid4().hex
    folder   = Path(output_dir) / state.job_id / "jianying_draft"
    folder.mkdir(parents=True, exist_ok=True)

    vsegs, asegs, tsegs, mvideos, maudios = [], [], [], [], []
    cur = 0
    for sc in state.outline.scene_breakdown:
        img_ok  = sc.image_path and os.path.exists(sc.image_path)
        vid_ok  = sc.video_path and os.path.exists(sc.video_path)
        aud_ok  = sc.audio_path and os.path.exists(sc.audio_path)
        dur_us  = int((sc.audio_duration or sc.duration_estimate) * US)

        sv = _uuid.uuid4().hex; mv = _uuid.uuid4().hex; ma = _uuid.uuid4().hex

        if vid_ok:
            # 优先使用视频素材
            vsegs.append({"id":sv,"material_id":mv,
                "target_timerange":{"start":cur,"duration":dur_us},
                "source_timerange":{"start":0,"duration":dur_us},
                "speed":1.0,"volume":1.0})
            mvideos.append({"id":mv,"type":"video","path":os.path.abspath(sc.video_path),"duration":dur_us})
        elif img_ok:
            vsegs.append({"id":sv,"material_id":mv,
                "target_timerange":{"start":cur,"duration":dur_us},
                "source_timerange":{"start":0,"duration":dur_us},
                "speed":1.0,"volume":1.0})
            mvideos.append({"id":mv,"type":"photo","path":os.path.abspath(sc.image_path),"duration":dur_us})

        if aud_ok:
            asegs.append({"id":_uuid.uuid4().hex,"material_id":ma,
                "target_timerange":{"start":cur,"duration":dur_us},
                "source_timerange":{"start":0,"duration":dur_us},"volume":1.0})
            maudios.append({"id":ma,"type":"audio","path":os.path.abspath(sc.audio_path),"duration":dur_us})
        if vid_cfg.subtitle_enabled and sc.narration:
            tsegs.append({"id":_uuid.uuid4().hex,"material_id":_uuid.uuid4().hex,
                "content":sc.narration,
                "target_timerange":{"start":cur,"duration":dur_us},
                "style":{"font_size":9.0,"color":"#FFFFFF","background_alpha":0.55,"alignment":1},
                "position":{"x":.5,"y":.88},"size":{"x":.9,"y":.08}})
        cur += dur_us

    content = {
        "version":"5.9.0","id":draft_id,
        "name":f"漫剧_{state.outline.title[:12]}","duration":cur,
        "canvas_config":{"width":1920,"height":1080},
        "timeline":{"tracks":[
            {"type":"video","segments":vsegs},
            {"type":"audio","segments":asegs},
            {"type":"text","segments":tsegs},
        ]},
        "materials":{"videos":mvideos,"audios":maudios},
    }
    meta = {"id":draft_id,"name":f"漫剧_{state.outline.title[:12]}",
            "create_time":int(time.time()),"duration":cur}

    (folder/"draft_content.json").write_text(
        json.dumps(content, ensure_ascii=False, indent=2), "utf-8")
    (folder/"draft_meta_info.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
    return str(folder)


async def run_video_editor(
    state: PipelineState, push: Callable, cfg: SystemConfig, output_dir: str
) -> PipelineState:
    ag = _ag(state, "video_editor")
    ag.status, ag.started_at, ag.progress, ag.message = AgentStatus.RUNNING, time.time(), 5, "准备合成..."
    await push(state)

    vid = cfg.video
    try:
        if vid.mode == "moviepy":
            ag.message, ag.progress = "MoviePy 合成中...", 20
            await push(state)
            out = str(Path(output_dir) / state.job_id / "final.mp4")
            await asyncio.get_event_loop().run_in_executor(None, _moviepy, state, out, vid)
            state.final_video_url = f"/outputs/{state.job_id}/final.mp4"
            ag.message = "MP4 合成完成"
        else:
            ag.message, ag.progress = "生成剪映草稿...", 40
            await push(state)
            await asyncio.sleep(.8)
            draft = await asyncio.get_event_loop().run_in_executor(
                None, _jianying, state, output_dir, vid)
            state.jianying_draft_dir = draft
            ag.message = "剪映草稿已就绪"

        for sc in state.outline.scene_breakdown:
            sc.status = "done"
        _done(ag, "✓ 合成完成")
        state.overall_status   = "done"
        state.overall_progress = 100
        await push(state)
        return state
    except Exception as e:
        _err(ag, f"✗ {e}")
        state.overall_status  = "error"
        state.error_message   = str(e)
        await push(state)
        raise
