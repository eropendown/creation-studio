"""配置持久化（JSON 文件 + 内存缓存）"""
import json, logging, time
from pathlib import Path
from core.models import SystemConfig

log = logging.getLogger(__name__)
_PATH  = Path("data/system_config.json")
_cache: SystemConfig | None = None

def get_config() -> SystemConfig:
    global _cache
    if _cache: return _cache
    try:
        if _PATH.exists():
            _cache = SystemConfig(**json.loads(_PATH.read_text("utf-8")))
            return _cache
    except Exception as e:
        log.warning(f"Config load: {e}")
    _cache = SystemConfig()
    return _cache

def save_config(cfg: SystemConfig) -> SystemConfig:
    global _cache
    cfg.updated_at = time.time()
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(cfg.model_dump_json(indent=2), "utf-8")
    _cache = cfg
    log.info("Config saved")
    return cfg

def reset_config() -> SystemConfig:
    global _cache
    _cache = SystemConfig()
    save_config(_cache)
    return _cache