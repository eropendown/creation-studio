"""
灵感引擎 v1
- 根据用户的 idea，异步搜索相关小说/影视作品
- 分析其优点、设定手法、结构亮点
- 以「参考卡片」形式返回，不注入对话历史
- 前端在侧边栏展示，完全独立于写作流程
"""
from __future__ import annotations
import asyncio, json, logging, re, time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════
#  数据结构
# ════════════════════════════════════════════════════

@dataclass
class InspirationCard:
    """单个参考作品卡片"""
    title:       str          # 作品名
    type:        str          # novel | film | series
    genre:       str          # 类型
    why_relevant: str         # 为何与用户 idea 相关（1 句）
    highlights:  list[str]    # 值得借鉴的亮点（3-5 条）
    techniques:  list[str]    # 具体手法（结构/叙事/人物）
    caution:     str = ""     # 可选：避免踩的坑

    def to_dict(self) -> dict:
        return {
            "title":        self.title,
            "type":         self.type,
            "genre":        self.genre,
            "why_relevant": self.why_relevant,
            "highlights":   self.highlights,
            "techniques":   self.techniques,
            "caution":      self.caution,
        }


@dataclass
class InspirationResult:
    query:      str
    cards:      list[InspirationCard] = field(default_factory=list)
    writing_tips: list[str]           = field(default_factory=list)  # 通用写作建议
    generated_at: float               = field(default_factory=time.time)
    source:     str = "llm"           # llm | cache

    def to_dict(self) -> dict:
        return {
            "query":        self.query,
            "cards":        [c.to_dict() for c in self.cards],
            "writing_tips": self.writing_tips,
            "generated_at": self.generated_at,
            "source":       self.source,
        }


# ════════════════════════════════════════════════════
#  简易内存缓存（同一 idea 30 分钟内不重复调用 LLM）
# ════════════════════════════════════════════════════

_cache: dict[str, tuple[float, InspirationResult]] = {}
_CACHE_TTL = 1800  # 30 min


def _cache_key(idea: str) -> str:
    # 取前 80 字作为缓存 key，忽略标点空格
    clean = re.sub(r"[^\u4e00-\u9fff\w]", "", idea)[:80]
    return clean.lower()


# ════════════════════════════════════════════════════
#  LLM 提示词
# ════════════════════════════════════════════════════

_SYSTEM = """你是一位资深文学编辑和影视研究者，专门帮助创作者寻找参考作品和提炼创作技巧。

任务：根据用户的小说创意，推荐3-4部最相关的参考作品（国内外小说、电影、剧集均可），
并提炼每部作品中最值得借鉴的具体手法和设定。

重要原则：
- 推荐真实存在的作品，不要编造
- 亮点必须具体，不能泛泛而谈（"人物塑造好"不算，"用碎片化闪回揭示主角童年创伤"才算）
- 手法必须可操作，创作者读完知道怎么用
- 每部作品标注类型：novel（小说）/ film（电影）/ series（剧集/网剧）

输出格式（纯JSON，不含其他文字）：
{
  "cards": [
    {
      "title": "作品名",
      "type": "novel|film|series",
      "genre": "类型",
      "why_relevant": "一句话说明为何与用户 idea 相关",
      "highlights": [
        "具体亮点1（可直接借鉴的）",
        "具体亮点2",
        "具体亮点3"
      ],
      "techniques": [
        "具体叙事/结构手法1",
        "具体手法2"
      ],
      "caution": "可选：这部作品的常见误读或创作陷阱"
    }
  ],
  "writing_tips": [
    "基于以上参考，给用户这个具体创意的3条写作建议",
    "建议2",
    "建议3"
  ]
}"""


# ════════════════════════════════════════════════════
#  主引擎
# ════════════════════════════════════════════════════

class InspirationEngine:
    def __init__(self, llm_cfg: dict):
        from core.llm import LLMClient
        self.llm = LLMClient(llm_cfg)

    async def get_inspiration(self, idea: str) -> InspirationResult:
        """
        根据创意 idea 返回灵感卡片列表。
        带缓存，同一 idea 30 分钟内直接返回缓存结果。
        """
        key = _cache_key(idea)

        # 检查缓存
        if key in _cache:
            ts, cached = _cache[key]
            if time.time() - ts < _CACHE_TTL:
                log.debug(f"Inspiration cache hit: {key[:30]}")
                cached.source = "cache"
                return cached

        # 调用 LLM
        result = await self._generate(idea)

        # 写入缓存
        _cache[key] = (time.time(), result)
        return result

    async def _generate(self, idea: str) -> InspirationResult:
        try:
            raw = await self.llm.chat(
                _SYSTEM,
                f"用户的创意：\n\n{idea[:1500]}",
                temperature=0.7,
                max_tokens=2000,
            )
            return self._parse(idea, raw)

        except Exception as e:
            log.error(f"InspirationEngine LLM error: {e}")
            # 降级返回空结果，不抛错
            return InspirationResult(
                query=idea,
                cards=[],
                writing_tips=[f"灵感推荐暂时不可用（{e}）"],
                source="error",
            )

    def _parse(self, idea: str, raw: str) -> InspirationResult:
        try:
            clean = re.sub(r"```json\s*|\s*```", "", raw).strip()
            data  = json.loads(clean)
            cards = [
                InspirationCard(
                    title=c.get("title", ""),
                    type=c.get("type", "novel"),
                    genre=c.get("genre", ""),
                    why_relevant=c.get("why_relevant", ""),
                    highlights=c.get("highlights") or [],
                    techniques=c.get("techniques") or [],
                    caution=c.get("caution", ""),
                )
                for c in (data.get("cards") or [])
            ]
            return InspirationResult(
                query=idea,
                cards=cards,
                writing_tips=data.get("writing_tips") or [],
                source="llm",
            )
        except Exception as e:
            log.error(f"InspirationEngine parse error: {e}\nRaw: {raw[:300]}")
            return InspirationResult(
                query=idea, cards=[], writing_tips=[], source="parse_error"
            )
