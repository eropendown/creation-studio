"""
环境变量配置（pydantic-settings）
通过 .env 文件或环境变量注入
注：config_store.py 是配置持久化层，用于运行时读写
    config.py    是环境变量加载层，用于启动时注入 .env
"""
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # LLM
    openai_api_key:     str = ""
    openai_base_url:    str = "https://api.openai.com/v1"
    openai_model:       str = "gpt-4o-mini"
    deepseek_api_key:   str = ""
    deepseek_base_url:  str = "https://api.deepseek.com/v1"
    deepseek_model:     str = "deepseek-chat"

    # 火山引擎 TTS
    volcengine_tts_app_id:      str = ""
    volcengine_tts_access_key:  str = ""
    volcengine_tts_secret_key:  str = ""
    volcengine_tts_cluster:     str = "volcano_tts"

    # ElevenLabs
    elevenlabs_api_key:  str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"

    # 火山引擎视频生成
    volcengine_video_api_key:  str = ""
    volcengine_video_model:    str = "seedance-2.0"

    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
