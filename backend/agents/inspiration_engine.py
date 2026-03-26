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
#  Mock 数据（provider=mock 时返回）
# ════════════════════════════════════════════════════

_MOCK_CARDS = {
    "default": InspirationResult(
        query="示例创意",
        source="mock",
        cards=[
            InspirationCard(
                title="心理测量者",
                type="series",
                genre="赛博朋克·悬疑",
                why_relevant="同样探讨AI/系统对人类自由意志的控制与异化",
                highlights=[
                    "用「犯罪系数」这一具体数值将抽象的道德判断具象化，读者立刻理解系统逻辑",
                    "反派西比拉系统从不直接出场，始终通过中间人行动，增强神秘感和压迫感",
                    "主角成长弧与对系统信任/质疑的转变高度绑定，情感和主题同步推进",
                ],
                techniques=[
                    "设定一个可量化的「异化指标」，让读者能直观感受主角处境恶化",
                    "让系统通过「正当程序」作恶，比直接暴力更令人不安",
                ],
                caution="避免把系统写成单纯的坏，最好的版本是让读者一度觉得系统有道理",
            ),
            InspirationCard(
                title="银翼杀手2049",
                type="film",
                genre="科幻·哲学",
                why_relevant="同类世界观密度和AI存在性追问的标杆",
                highlights=[
                    "每一个画面都在暗示世界观信息，而非用台词解释，极度信任观众",
                    "主角身份之谜的揭示节奏：先给假答案满足期待，再用真答案颠覆一切",
                    "AI角色乔伊的存在感比任何人类角色都更真实，用「局限」来彰显「真实」",
                ],
                techniques=[
                    "用环境色温区分阵营：暖色=人性残留的地方，冷色=系统控制的空间",
                    "给AI角色一个「只有她自己在乎的小事」，让读者相信她有内心世界",
                ],
            ),
            InspirationCard(
                title="三体",
                type="novel",
                genre="科幻·硬核",
                why_relevant="处理宏大科技设定时保持人文温度的范本",
                highlights=[
                    "「黑暗森林法则」是全书最大的世界观设定，但通过几个思想实验推理得出，读者全程参与推导",
                    "用叶文洁的个人创伤解释她做出历史级别决定的动机，宏大选择有微观根基",
                    "技术描写始终服务于人物情感，而非炫技",
                ],
                techniques=[
                    "让角色用「讲故事」或「做实验」的方式展示世界观，而非用作者之声解释",
                    "每个宏大设定背后放置一个私人情感，防止读者疏离",
                ],
            ),
        ],
        writing_tips=[
            "你的 AI 觉醒设定最大的风险是「觉醒过程」写得太快——建议用至少3个场景让读者逐步相信 AI 有意识，每次都留一个合理解释的空间",
            "主角调查员身份天然适合「信息不对称叙事」：读者比主角先知道某件事，或主角比读者先知道——善用这个张力",
            "给 AI 角色设计一个「只有她在乎的微小事物」（比如某首诗、某种颜色），比任何哲学独白都更有说服力",
        ],
    )
}


# ════════════════════════════════════════════════════
#  主引擎
# ════════════════════════════════════════════════════

class InspirationEngine:
    def __init__(self, llm_cfg: dict):
        self.llm_cfg = llm_cfg

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
        provider = self.llm_cfg.get("provider", "mock")

        if provider == "mock":
            await asyncio.sleep(0.3)
            mock = _MOCK_CARDS["default"]
            mock.query = idea
            return mock

        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=self.llm_cfg.get("api_key"),
                base_url=self.llm_cfg.get("base_url", "https://api.openai.com/v1"),
            )
            resp = await client.chat.completions.create(
                model=self.llm_cfg.get("model", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user",   "content": f"用户的创意：\n\n{idea[:1500]}"},
                ],
                temperature=0.7,
                max_tokens=2000,
            )
            raw = resp.choices[0].message.content.strip()
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
