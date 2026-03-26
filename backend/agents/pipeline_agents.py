"""
Pipeline Agents v5 — 仅配音 + 剪辑
图像生成已移出，由用户手动生成并上传
"""
import asyncio, json, logging, math, struct, time, wave
from pathlib import Path
from typing import Callable
from core.models import PipelineState, AgentStatus, SceneItem, SystemConfig

log = logging.getLogger(__name__)

def _ag(state, name): return state.agents[name]
def _done(ag, msg):   ag.status, ag.finished_at, ag.message, ag.progress = AgentStatus.DONE,  time.time(), msg, 100
def _err(ag, msg):    ag.status, ag.finished_at, ag.message              = AgentStatus.ERROR, time.time(), msg


# ══════════════════════════════════════════════════
#  VOICE ACTOR
# ══════════════════════════════════════════════════

_VOICE_MAP = {
    "震惊":"nova","愤怒":"onyx","柔情":"shimmer","紧张":"nova",
    "释然":"alloy","悲伤":"shimmer","喜悦":"echo","坚定":"onyx","迷茫":"alloy",
}

def _mock_wav(text: str, out: str) -> float:
    dur = max(1.5, len(text) / 4.0)
    sr  = 22050; n = int(sr * dur)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(out, "w") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        for i in range(n):
            t    = i / sr
            fade = min(t / .08, 1.0, (dur - t) / .08)
            v    = .6 * math.sin(2*math.pi*180*t) + .3 * math.sin(2*math.pi*360*t)
            v   *= (.7 + .3 * math.sin(2*math.pi*3.5*t))
            wf.writeframes(struct.pack("<h", int(fade * 8500 * v)))
    return dur

async def _openai_tts(sc: SceneItem, out: str, cfg) -> float:
    from openai import AsyncOpenAI
    voice  = _VOICE_MAP.get(sc.emotion, cfg.voice_id)
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
        ext = "wav" if tts.provider == "mock" else "mp3"
        out = str(Path(output_dir) / state.job_id / f"audio_{sc.scene_id:02d}.{ext}")
        try:
            if   tts.provider == "mock":       dur = await asyncio.get_event_loop().run_in_executor(None, _mock_wav, sc.narration, out); await asyncio.sleep(.2)
            elif tts.provider == "openai":     dur = await _openai_tts(sc, out, tts)
            elif tts.provider == "elevenlabs": dur = await _elevenlabs_tts(sc, out, tts)
            else: raise ValueError(f"Unknown TTS: {tts.provider}")
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
#  VIDEO EDITOR
# ══════════════════════════════════════════════════

def _moviepy(state: PipelineState, out_path: str, vid_cfg):
    import os
    from moviepy.editor import (
        ImageClip, AudioFileClip, TextClip,
        CompositeVideoClip, concatenate_videoclips
    )
    clips = []
    for sc in state.outline.scene_breakdown:
        if not sc.image_path or not os.path.exists(sc.image_path): continue
        if not sc.audio_path or not os.path.exists(sc.audio_path): continue
        try:
            audio = AudioFileClip(sc.audio_path)
            dur   = audio.duration
            video = ImageClip(sc.image_path).set_duration(dur).set_audio(audio)
            if vid_cfg.subtitle_enabled and sc.narration:
                try:
                    txt = TextClip(
                        sc.narration, fontsize=vid_cfg.subtitle_font_size,
                        color="white", bg_color="rgba(0,0,0,0.55)",
                        font="DejaVu-Sans", method="caption",
                        size=(video.w - 40, None),
                    ).set_duration(dur).set_position(("center", video.h - 70))
                    video = CompositeVideoClip([video, txt])
                except Exception as e:
                    log.warning(f"Subtitle creation failed for scene {sc.scene_id}: {e}")
            clips.append(video)
        except Exception as e:
            log.error(f"Clip {sc.scene_id}: {e}")
    if not clips: raise ValueError("No valid clips")
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
        aud_ok  = sc.audio_path and os.path.exists(sc.audio_path)
        dur_us  = int((sc.audio_duration or sc.duration_estimate) * US)

        sv = _uuid.uuid4().hex; mv = _uuid.uuid4().hex; ma = _uuid.uuid4().hex
        if img_ok:
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