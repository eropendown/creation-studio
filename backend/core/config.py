from pathlib import Path

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # LLM
    openai_api_key:    str = ""
    openai_base_url:   str = "https://api.openai.com/v1"
    openai_model:      str = "gpt-4o-mini"
    deepseek_api_key:  str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model:    str = "deepseek-chat"

    # ComfyUI
    comfyui_url:           str = "http://127.0.0.1:8188"
    comfyui_workflow_path: str = "core/comfyui_workflow.json"
    character_ref_image:   str = ""  # 角色参考图路径（IP-Adapter 用）

    # TTS
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"

    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent
    output_dir: Path = BASE_DIR / "outputs"
    upload_dir: Path = BASE_DIR / "uploads"

    output_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)


    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()