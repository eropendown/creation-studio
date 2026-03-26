"""
漫剧多智能体系统 · 数据模型 v5
新增：小说导入、手动图片上传
移除：自动图像生成（改为用户手动处理）
大纲生成：分批调用避免 token 截断
"""
from __future__ import annotations
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from enum import Enum
import uuid, time


# ════════════════════════════════════════════════════
#  配置
# ════════════════════════════════════════════════════

class LLMConfig(BaseModel):
    provider:    str   = "mock"
    api_key:     str   = ""
    base_url:    str   = "https://api.openai.com/v1"
    model:       str   = "gpt-4o-mini"
    temperature: float = 0.9
    # 单次最大 token；分批时每批 scene_count<=4 来保证不截断
    max_tokens:  int   = 4096
    timeout:     int   = 120

class TTSConfig(BaseModel):
    provider:  str   = "edge_tts"
    api_key:   str   = ""
    voice_id:  str   = "zh-CN-YunxiNeural"
    model:     str   = "tts-1"
    speed:     float = 1.0
    language:  str   = "zh"
    # 火山引擎 TTS 专属字段
    volcengine_app_id:      str = ""
    volcengine_access_key:  str = ""
    volcengine_secret_key:  str = ""
    volcengine_cluster:     str = "volcano_tts"

class VideoConfig(BaseModel):
    mode:               str  = "jianying"
    fps:                int  = 24
    resolution:         str  = "1920x1080"
    subtitle_enabled:   bool = True
    subtitle_font_size: int  = 32
    # 火山引擎视频生成（Seedance）
    volcengine_api_key:   str = ""
    volcengine_model:     str = "seedance-2.0"
    volcengine_base_url:  str = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"

class AgentPrompts(BaseModel):
    """全部可由前端编辑"""

    # 步骤1：分析小说 / 解析简介，提取基础信息
    analyze_system: str = (
        "你是资深漫剧编剧，擅长将小说/故事改编为短视频漫剧脚本。\n"
        "任务：仔细阅读输入文本，提取核心故事要素。\n"
        "【重要】必须输出完整 JSON，不要截断，不要省略任何字段。\n"
        "输出格式（纯 JSON，不含其他文字）：\n"
        '{"title":"","genre":"","core_conflict":"核心冲突（50字以上）","synopsis":"完整剧情简介（200字以上）",'
        '"characters":[{"name":"","role":"主角|配角|反派|导师","description":"性格特点（50字以上）",'
        '"appearance":"外貌描述（30字以上）","motivation":"行为动机（30字以上）"}],'
        '"plot_points":[{"order":1,"title":"节点标题","content":"详细情节（80字以上）","emotion":"情绪","importance":"high|medium|low"}],'
        '"themes":["主题"],"tone":"整体基调","production_notes":"改编备注"}'
    )

    # 步骤2：生成章节结构（起承转合）
    structure_system: str = (
        "你是专业漫剧结构编剧。\n"
        "根据故事分析，生成起承转合章节结构。\n"
        "【重要】每幕 description 必须 ≥ 150 字，key_events 每条 ≥ 40 字。\n"
        "输出纯 JSON（不含其他文字）：\n"
        '{"acts":[{"act":1,"title":"起·标题","description":"本幕详细情节（≥150字）",'
        '"emotional_arc":"情绪走向XX→XX→XX","key_events":["关键事件（≥40字）"],'
        '"character_focus":["角色名"],"scene_count_suggest":3}],'
        '"hook":"开篇黄金三秒钩子（吸引观众的第一句话，≥20字）",'
        '"climax_description":"高潮场景描述（≥100字）","ending_type":"结局类型",'
        '"total_duration_estimate":总秒数,"production_notes":"制作备注"}'
    )

    # 步骤3：分批生成分镜（每次最多4个，防止截断）
    scene_batch_system: str = (
        "你是专业漫剧分镜编剧，将故事情节转化为具体可执行的分镜脚本。\n"
        "【强制要求，违反则输出无效】：\n"
        "1. visual_description ≥ 60字：构图+光线+人物动作+表情+背景环境\n"
        "2. narration 15-35字：旁白/对白，直击情感，有画面感\n"
        "3. image_prompt 为英文：画风+构图+场景+人物+情绪+质量词，≥60词\n"
        "4. 每个字段必填，不允许空字符串\n"
        "5. 输出纯 JSON 数组，不含其他文字\n\n"
        "输出格式：\n"
        '[{"scene_id":1,"act":1,"title":"分镜标题(≤8字)",'
        '"visual_description":"≥60字完整画面描述",'
        '"narration":"旁白15-35字",'
        '"character_name":"主要角色",'
        '"emotion":"震惊|愤怒|柔情|紧张|释然|悲伤|喜悦|绝望|坚定|迷茫",'
        '"camera_shot":"具体镜头（俯拍全景/仰拍特写/近景特写/侧面中景/跟拍运镜/固定长镜/慢推镜头）",'
        '"duration_estimate":3.5,'
        '"image_prompt":"English SD prompt ≥60 words, style+composition+scene+character+emotion+quality suffix",'
        '"negative_prompt":"lowres, bad anatomy, bad hands, text, watermark, blurry, deformed, ugly"}]'
    )

    art_style_prefix: str = ""  # 追加到所有 image_prompt 前

class SystemConfig(BaseModel):
    config_version: str   = "5.0"
    llm:     LLMConfig    = Field(default_factory=LLMConfig)
    tts:     TTSConfig    = Field(default_factory=TTSConfig)
    video:   VideoConfig  = Field(default_factory=VideoConfig)
    prompts: AgentPrompts = Field(default_factory=AgentPrompts)
    updated_at: float     = Field(default_factory=time.time)


# ════════════════════════════════════════════════════
#  剧本大纲
# ════════════════════════════════════════════════════

class Character(BaseModel):
    name:        str = ""
    role:        str = ""
    description: str = ""
    appearance:  str = ""
    motivation:  str = ""

class PlotPoint(BaseModel):
    order:      int  = 0
    title:      str  = ""
    content:    str  = ""
    emotion:    str  = ""
    importance: str  = "medium"

class Act(BaseModel):
    act:                 int       = 1
    title:               str       = ""
    description:         str       = ""
    emotional_arc:       str       = ""
    key_events:          List[str] = []
    character_focus:     List[str] = []
    scene_count_suggest: int       = 3

class SceneItem(BaseModel):
    scene_id:           int   = 0
    act:                int   = 1
    title:              str   = ""
    visual_description: str   = ""
    narration:          str   = ""
    character_name:     str   = ""
    emotion:            str   = ""
    camera_shot:        str   = ""
    duration_estimate:  float = 3.5
    # 图像（用户手动生成后上传）
    image_prompt:       str   = ""   # SD 正向提示词，前端展示给用户
    negative_prompt:    str   = ""
    image_path:         str   = ""
    image_url:          str   = ""
    image_uploaded:     bool  = False
    # 音频
    audio_path:         str   = ""
    audio_duration:     float = 0.0
    audio_uploaded:     bool  = False
    # 视频（用户上传或系统生成）
    video_path:         str   = ""
    video_url:          str   = ""
    video_uploaded:     bool  = False
    video_task_id:      str   = ""   # 火山引擎异步任务 ID
    video_status:       str   = ""   # generating | done | error
    # 状态
    status:             str   = "pending"  # pending|prompt_ready|image_uploaded|voiced|done
    error_msg:          str   = ""

class ScriptOutline(BaseModel):
    outline_id:          str  = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    source_type:         str  = "manual"   # manual | novel
    source_title:        str  = ""
    source_excerpt:      str  = ""         # 原文摘要（前300字）
    title:               str  = ""
    genre:               str  = ""
    style:               str  = ""
    synopsis:            str  = ""
    core_conflict:       str  = ""
    themes:              List[str]     = []
    tone:                str  = ""
    production_notes:    str  = ""
    word_count_target:   int  = 1000
    word_count_estimate: int  = 0
    estimated_duration:  float = 0.0
    characters:          List[Character]  = []
    plot_points:         List[PlotPoint]  = []
    acts:                List[Act]        = []
    scene_breakdown:     List[SceneItem] = []
    total_scenes:        int  = 0
    tags:                List[str] = []
    hook:                str  = ""
    climax_scene:        int  = 0
    climax_description:  str  = ""
    ending_type:         str  = ""
    outline_status:      str  = "draft"
    generation_log:      List[str] = []
    created_at:          float = Field(default_factory=time.time)


# ════════════════════════════════════════════════════
#  Pipeline 状态
# ════════════════════════════════════════════════════

class AgentStatus(str, Enum):
    IDLE    = "idle"
    RUNNING = "running"
    DONE    = "done"
    ERROR   = "error"

class AgentInfo(BaseModel):
    name:         str
    display_name: str
    emoji:        str
    status:       AgentStatus = AgentStatus.IDLE
    message:      str  = ""
    progress:     int  = 0
    started_at:   Optional[float] = None
    finished_at:  Optional[float] = None

    @property
    def elapsed(self) -> Optional[float]:
        if not self.started_at: return None
        return round((self.finished_at or time.time()) - self.started_at, 1)

class PipelineState(BaseModel):
    job_id:    str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    outline:   Optional[ScriptOutline] = None
    config:    Optional[SystemConfig]  = None
    agents:    Dict[str, AgentInfo] = Field(default_factory=lambda: {
        "voice_actor":  AgentInfo(name="voice_actor",  display_name="配音智能体", emoji="🎙️"),
        "video_gen":    AgentInfo(name="video_gen",    display_name="视频生成",   emoji="🎥"),
        "video_editor": AgentInfo(name="video_editor", display_name="剪辑智能体", emoji="🎬"),
    })
    overall_status:     str   = "idle"
    overall_progress:   int   = 0
    error_message:      str   = ""
    created_at:         float = Field(default_factory=time.time)
    final_video_url:    str   = ""
    jianying_draft_dir: str   = ""
    # 火山引擎视频生成任务
    volcengine_tasks:   Dict[str, str] = Field(default_factory=dict)  # scene_id -> task_id

    def ws_payload(self) -> dict:
        return {
            "job_id":             self.job_id,
            "overall_status":     self.overall_status,
            "overall_progress":   self.overall_progress,
            "error_message":      self.error_message,
            "agents": {
                k: {"name":v.name,"display_name":v.display_name,"emoji":v.emoji,
                    "status":v.status.value,"message":v.message,"progress":v.progress,"elapsed":v.elapsed}
                for k,v in self.agents.items()
            },
            "outline":            self.outline.model_dump() if self.outline else None,
            "final_video_url":    self.final_video_url,
            "jianying_draft_dir": self.jianying_draft_dir,
        }


# ════════════════════════════════════════════════════
#  HTTP 模型
# ════════════════════════════════════════════════════

class OutlineRequest(BaseModel):
    genre:       str = Field(..., description="主题类型")
    synopsis:    str = Field(..., min_length=10)
    style:       str = Field(default="古风仙侠")
    scene_count: int = Field(default=8, ge=3, le=30)
    config:      Optional[SystemConfig] = None

class NovelImportRequest(BaseModel):
    novel_text:  str = Field(..., min_length=100)
    novel_title: str = Field(default="")
    style:       str = Field(default="古风仙侠")
    scene_count: int = Field(default=10, ge=3, le=30)
    focus_range: str = Field(default="", description="重点改编的章节/段落范围描述")
    config:      Optional[SystemConfig] = None

class ImageUploadRequest(BaseModel):
    outline_id: str
    scene_id:   int
    image_url:  str   # 上传后的图片 URL 或 data URL

class GenerateRequest(BaseModel):
    outline_id: str
    config:     Optional[SystemConfig] = None

class SaveConfigRequest(BaseModel):
    config: SystemConfig

class OutlineResponse(BaseModel):
    outline: ScriptOutline
    message: str

class GenerateResponse(BaseModel):
    job_id:  str
    message: str
    ws_url:  str