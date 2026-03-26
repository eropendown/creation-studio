"""大纲持久化存储（每条大纲独立 JSON 文件 + 内存缓存）"""
import json, logging, time
from pathlib import Path
from typing import Optional
from core.models import ScriptOutline

log = logging.getLogger(__name__)
_DIR = Path("data/outlines")
_cache: dict[str, ScriptOutline] = {}


def _path(oid: str) -> Path:
    return _DIR / f"{oid}.json"


def outline_save(o: ScriptOutline) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    _cache[o.outline_id] = o
    try:
        _path(o.outline_id).write_text(o.model_dump_json(indent=2), "utf-8")
        log.info(f"Outline saved: {o.outline_id} 《{o.title}》")
    except Exception as e:
        log.error(f"Outline save error: {e}")


def outline_get(oid: str) -> Optional[ScriptOutline]:
    if oid in _cache:
        return _cache[oid]
    p = _path(oid)
    if p.exists():
        try:
            o = ScriptOutline(**json.loads(p.read_text("utf-8")))
            _cache[o.outline_id] = o
            return o
        except Exception as e:
            log.error(f"Outline load error {oid}: {e}")
    return None


def outline_list() -> list[ScriptOutline]:
    """返回所有大纲，按创建时间倒序"""
    _DIR.mkdir(parents=True, exist_ok=True)
    result: list[ScriptOutline] = []

    # 从文件加载（不在缓存中的）
    for p in _DIR.glob("*.json"):
        oid = p.stem
        if oid not in _cache:
            try:
                o = ScriptOutline(**json.loads(p.read_text("utf-8")))
                _cache[o.outline_id] = o
            except Exception as e:
                log.warning(f"Skip broken outline {oid}: {e}")

    result = list(_cache.values())
    result.sort(key=lambda o: o.created_at, reverse=True)
    return result


def outline_delete(oid: str) -> bool:
    _cache.pop(oid, None)
    p = _path(oid)
    if p.exists():
        p.unlink()
        log.info(f"Outline deleted: {oid}")
        return True
    return False


def outline_summary_list() -> list[dict]:
    """轻量摘要列表，用于前端历史面板（不含 scene_breakdown 全量数据）"""
    return [
        {
            "outline_id":   o.outline_id,
            "title":        o.title,
            "source_type":  o.source_type,
            "source_title": o.source_title,
            "style":        o.style,
            "genre":        o.genre,
            "total_scenes": o.total_scenes,
            "estimated_duration": o.estimated_duration,
            "outline_status": o.outline_status,
            "images_done":  sum(1 for s in o.scene_breakdown if s.image_uploaded),
            "created_at":   o.created_at,
        }
        for o in outline_list()
    ]