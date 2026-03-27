"""
小说写作 Agent · 数据模型
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum
import uuid, time


# ════════════════════════════════════════════════════
#  枚举 / 常量
# ════════════════════════════════════════════════════

class NovelPhase(str, Enum):
    """小说创作阶段状态机"""
    INIT                 = "init"                  # 初始开场
    COLLECTING           = "collecting"            # 收集创作意图
    WORLDVIEW_BUILDING   = "worldview_building"    # 构建世界观中
    WORLDVIEW_REVIEW     = "worldview_review"      # 展示世界观待确认
    WORLDVIEW_CONFIRMED  = "worldview_confirmed"   # 世界观已确认
    OUTLINE_PLANNING     = "outline_planning"      # 规划情节大纲
    OUTLINE_REVIEW       = "outline_review"        # 展示大纲待确认
    OUTLINE_CONFIRMED    = "outline_confirmed"     # 大纲已确认
    CHAPTER_PREPARING    = "chapter_preparing"     # 分解章节场景
    CHAPTER_WRITING      = "chapter_writing"       # 逐场景创作中
    CHAPTER_DONE         = "chapter_done"          # 章节完成
    COMPLETE             = "complete"              # 全部完成


class MessageRole(str, Enum):
    USER      = "user"
    ASSISTANT = "assistant"
    SYSTEM    = "system"


# ════════════════════════════════════════════════════
#  世界观
# ════════════════════════════════════════════════════

class WorldCharacter(BaseModel):
    name:         str = ""
    role:         str = ""  # protagonist / supporting / antagonist / mentor
    age:          str = ""  # 年龄描述，如 "28岁" 或 "青年"（兼容 LLM 返回 int）
    description:  str = ""
    background:   str = ""
    personality:  str = ""
    ability:      str = ""
    motivation:   str = ""
    flaw:         str = ""
    relationship: str = ""  # 与主角的关系（配角用）
    appearance:   str = ""  # 外貌描述

    @field_validator("age", mode="before")
    @classmethod
    def coerce_age(cls, v):
        return str(v) if v is not None else ""


class WorldSetting(BaseModel):
    era:             str = ""
    geography:       str = ""
    social_structure: str = ""
    special_rules:   str = ""
    atmosphere:      str = ""


class Worldview(BaseModel):
    title:          str = ""
    genre:          str = ""
    core_theme:     str = ""
    world_setting:  WorldSetting = Field(default_factory=WorldSetting)
    protagonist:    Optional[WorldCharacter] = None
    supporting_characters: List[WorldCharacter] = []
    core_conflict:  str = ""
    story_hook:     str = ""
    themes:         List[str] = []
    writing_style:  str = ""
    target_length:  str = ""
    production_notes: str = ""
    raw_text:       str = ""   # 用户原始输入的世界观描述（不丢弃）
    created_at:     float = Field(default_factory=time.time)
    updated_at:     float = Field(default_factory=time.time)


# ════════════════════════════════════════════════════
#  情节大纲
# ════════════════════════════════════════════════════

class ChapterOutline(BaseModel):
    chapter_num:        int   = 1
    title:              str   = ""
    summary:            str   = ""
    key_events:         List[str] = []
    emotional_arc:      str   = ""
    foreshadowing:      str   = ""
    callback:           str   = ""
    ending_hook:        str   = ""
    word_count_target:  int   = 3000
    # 实际创作后填入
    actual_word_count:  int   = 0
    status:             str   = "pending"   # pending | writing | done


class NovelOutline(BaseModel):
    hook:                  str   = ""
    overall_arc:           str   = ""
    chapters:              List[ChapterOutline] = []
    planned_total_chapters: int  = 12
    created_at:            float = Field(default_factory=time.time)
    updated_at:            float = Field(default_factory=time.time)


# ════════════════════════════════════════════════════
#  场景 / 章节
# ════════════════════════════════════════════════════

class SceneTask(BaseModel):
    scene_id:           int   = 0
    title:              str   = ""
    location:           str   = ""
    time:               str   = ""
    characters:         List[str] = []
    goal:               str   = ""
    content_hint:       str   = ""
    word_count_target:  int   = 400
    completion_criteria: str  = ""
    # 创作后填入
    content:            str   = ""
    actual_word_count:  int   = 0
    status:             str   = "pending"  # pending | writing | done | skipped
    ending_line:        str   = ""         # 场景最后一句，用于下一场景续写


class Chapter(BaseModel):
    chapter_num:  int   = 1
    title:        str   = ""
    scenes:       List[SceneTask] = []
    full_content: str   = ""   # 拼接所有场景内容
    word_count:   int   = 0
    status:       str   = "pending"  # pending | writing | done
    # 质量评审
    review_score: float = 0.0       # 综合评分
    review_data:  Dict[str, Any] = {}  # 完整评审数据
    created_at:   float = Field(default_factory=time.time)


# ════════════════════════════════════════════════════
#  对话消息
# ════════════════════════════════════════════════════

class ChatMessage(BaseModel):
    msg_id:     str   = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    role:       MessageRole
    content:    str
    phase:      str   = ""   # 消息产生时的阶段
    metadata:   Dict[str, Any] = {}
    created_at: float = Field(default_factory=time.time)


# ════════════════════════════════════════════════════
#  小说会话（顶层对象）
# ════════════════════════════════════════════════════

class CollectedInfo(BaseModel):
    """开场收集的信息"""
    genre:       str = ""
    theme:       str = ""
    protagonist: str = ""
    length:      str = ""
    extra_notes: str = ""


class NovelSession(BaseModel):
    session_id:        str   = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title:             str   = ""   # 小说标题（世界观确认后填入）
    phase:             NovelPhase = NovelPhase.INIT
    use_memory_mode:   bool  = False    # 无文档ID时降级

    # 收集的信息
    collected_info:    CollectedInfo = Field(default_factory=CollectedInfo)

    # 三阶段产物
    worldview:         Optional[Worldview]    = None
    outline:           Optional[NovelOutline] = None
    chapters:          List[Chapter]          = []

    # 当前写作位置
    current_chapter_num: int = 0
    current_scene_id:    int = 0

    # 对话历史（用于 LLM context）
    messages:          List[ChatMessage] = []

    # 生成日志
    generation_log:    List[str] = []

    created_at:        float = Field(default_factory=time.time)
    updated_at:        float = Field(default_factory=time.time)

    def add_message(self, role: MessageRole, content: str, phase: str = "", metadata: dict = {}) -> ChatMessage:
        msg = ChatMessage(role=role, content=content, phase=phase or self.phase.value, metadata=metadata)
        self.messages.append(msg)
        self.updated_at = time.time()
        return msg

    def log(self, text: str):
        entry = f"[{time.strftime('%H:%M:%S')}] {text}"
        self.generation_log.append(entry)

    @property
    def current_chapter(self) -> Optional[Chapter]:
        if not self.current_chapter_num: return None
        return next((c for c in self.chapters if c.chapter_num == self.current_chapter_num), None)

    @property
    def llm_messages(self) -> List[dict]:
        """转换为 OpenAI messages 格式，根据上下文窗口动态调整保留条数"""
        # 默认 20 条（128K 以下模型），长上下文模型可保留更多
        max_msgs = 20
        recent = self.messages[-max_msgs:]
        return [{"role": m.role.value, "content": m.content} for m in recent
                if m.role in (MessageRole.USER, MessageRole.ASSISTANT)]

    def llm_messages_for_context(self, context_window: int = 128_000) -> List[dict]:
        """根据模型上下文窗口大小返回适量的历史消息"""
        if context_window >= 1_000_000:
            max_msgs = 50   # 百万token级：保留50条
        elif context_window >= 256_000:
            max_msgs = 30   # 256K级：保留30条
        elif context_window >= 128_000:
            max_msgs = 20   # 128K级：保留20条
        else:
            max_msgs = 10   # 小模型：保留10条

        recent = self.messages[-max_msgs:]
        return [{"role": m.role.value, "content": m.content} for m in recent
                if m.role in (MessageRole.USER, MessageRole.ASSISTANT)]

    def summary(self) -> dict:
        """轻量摘要，用于列表展示"""
        return {
            "session_id":    self.session_id,
            "title":         self.title or "未命名小说",
            "phase":         self.phase.value,
            "chapters_done": sum(1 for c in self.chapters if c.status == "done"),
            "total_words":   sum(c.word_count for c in self.chapters),
            "created_at":    self.created_at,
            "updated_at":    self.updated_at,
        }


# ════════════════════════════════════════════════════
#  HTTP 请求/响应模型
# ════════════════════════════════════════════════════

class NovelChatRequest(BaseModel):
    session_id: Optional[str] = None    # None 则新建会话
    message:    str
    config:     Optional[dict] = None   # 可覆盖 LLM 配置


class NovelChatResponse(BaseModel):
    session_id: str
    reply:      str
    phase:      str
    phase_data: Optional[dict] = None   # 阶段产物（世界观/大纲/场景列表）


class NovelSessionSummary(BaseModel):
    session_id:    str
    title:         str
    phase:         str
    chapters_done: int
    total_words:   int
    created_at:    float
    updated_at:    float