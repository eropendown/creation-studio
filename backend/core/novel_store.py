"""小说会话持久化（JSON 文件 + 内存缓存）"""
import json, logging, time
from pathlib import Path
from typing import Optional
from core.novel_models import NovelSession

log = logging.getLogger(__name__)
_DIR = Path("data/novel_sessions")
_cache: dict[str, NovelSession] = {}


def _path(sid: str) -> Path:
    return _DIR / f"{sid}.json"


def session_save(s: NovelSession) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    s.updated_at = time.time()
    _cache[s.session_id] = s
    try:
        _path(s.session_id).write_text(s.model_dump_json(indent=2), "utf-8")
    except Exception as e:
        log.error(f"Session save error: {e}")


def session_get(sid: str) -> Optional[NovelSession]:
    if sid in _cache:
        return _cache[sid]
    p = _path(sid)
    if p.exists():
        try:
            s = NovelSession(**json.loads(p.read_text("utf-8")))
            _cache[s.session_id] = s
            return s
        except Exception as e:
            log.error(f"Session load error {sid}: {e}")
    return None


def session_list() -> list[NovelSession]:
    _DIR.mkdir(parents=True, exist_ok=True)
    for p in _DIR.glob("*.json"):
        sid = p.stem
        if sid not in _cache:
            try:
                s = NovelSession(**json.loads(p.read_text("utf-8")))
                _cache[s.session_id] = s
            except Exception as e:
                log.warning(f"Skip broken session {sid}: {e}")
    result = list(_cache.values())
    result.sort(key=lambda s: s.updated_at, reverse=True)
    return result


def session_delete(sid: str) -> bool:
    existed = sid in _cache
    _cache.pop(sid, None)
    p = _path(sid)
    if p.exists():
        p.unlink()
        existed = True
    return existed


def session_summary_list() -> list[dict]:
    return [s.summary() for s in session_list()]
