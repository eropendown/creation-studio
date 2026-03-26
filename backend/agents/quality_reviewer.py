"""
质量评审 Agent — 章节完成后的质量审查
功能：
  1. 多维度评分（情节、人物、文笔、节奏、悬念）
  2. 角色一致性检查
  3. 具体修改建议
  4. 评分趋势追踪

参考：社区 Multi-Agent 最佳实践中的「Critic Pattern」
      Agent 输出由另一个 Agent 审查打分，形成质量闭环
"""
from __future__ import annotations
import json, logging, re, time
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class QualityScore:
    """单维度评分"""
    dimension: str   # 情节 | 人物 | 文笔 | 节奏 | 悬念
    score:     float # 1-10
    comment:   str   # 简评

    def to_dict(self) -> dict:
        return {"dimension": self.dimension, "score": self.score, "comment": self.comment}


@dataclass
class ChapterReview:
    """单章评审结果"""
    chapter_num:   int
    overall_score: float               # 综合评分 1-10
    scores:        list[QualityScore]   # 各维度评分
    strengths:     list[str]            # 优点
    issues:        list[str]            # 问题
    suggestions:   list[str]            # 修改建议
    character_consistency: dict = field(default_factory=dict)  # 角色一致性检查
    reviewed_at:   float  = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "chapter_num": self.chapter_num,
            "overall_score": self.overall_score,
            "scores": [s.to_dict() for s in self.scores],
            "strengths": self.strengths,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "character_consistency": self.character_consistency,
            "reviewed_at": self.reviewed_at,
        }

    @property
    def grade(self) -> str:
        if self.overall_score >= 8.5: return "A"
        if self.overall_score >= 7.0: return "B"
        if self.overall_score >= 5.5: return "C"
        return "D"


_SYSTEM = """你是一位资深文学编辑和小说评论家，专门负责评审小说章节的质量。

评审维度（每项 1-10 分）：
1. **情节**：情节是否有吸引力、逻辑是否通顺、转折是否自然
2. **人物**：角色行为是否符合设定、对话是否有个性、是否有成长弧
3. **文笔**：文字是否流畅、描写是否有画面感、是否有废话
4. **节奏**：场景切换是否合理、张弛是否有度、是否拖沓
5. **悬念**：是否留下继续阅读的欲望、结尾钩子是否有力

评审原则：
- 严格但公正，不敷衍
- 每个问题必须附具体修改建议
- 关注角色一致性（行为、语言风格是否偏离设定）
- 评分 7 分以上为合格，8 分以上为优秀

输出格式（纯 JSON，不含其他文字）：
{
  "scores": [
    {"dimension": "情节", "score": 7.5, "comment": "简评"},
    {"dimension": "人物", "score": 8.0, "comment": "简评"},
    {"dimension": "文笔", "score": 7.0, "comment": "简评"},
    {"dimension": "节奏", "score": 6.5, "comment": "简评"},
    {"dimension": "悬念", "score": 7.0, "comment": "简评"}
  ],
  "strengths": ["优点1", "优点2"],
  "issues": ["问题1", "问题2"],
  "suggestions": ["修改建议1（具体到哪一段如何改）", "建议2"],
  "character_consistency": {
    "角色名": {"consistent": true, "note": "行为符合设定"},
    "角色名2": {"consistent": false, "note": "此处突然改变了性格，建议..."}
  }
}"""


class QualityReviewer:
    """质量评审 Agent"""

    def __init__(self, llm_cfg: dict):
        self.llm_cfg = llm_cfg

    async def review_chapter(
        self,
        chapter_content: str,
        chapter_num: int,
        chapter_title: str,
        worldview_text: str = "",
        prev_chapter_ending: str = "",
    ) -> ChapterReview:
        """评审单个章节"""
        provider = self.llm_cfg.get("provider", "mock")

        if provider == "mock":
            return self._mock_review(chapter_num)

        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=self.llm_cfg.get("api_key"),
                base_url=self.llm_cfg.get("base_url", "https://api.openai.com/v1"),
            )

            user_msg = f"## 第{chapter_num}章《{chapter_title}》\n\n"
            if worldview_text:
                user_msg += f"### 世界观设定\n{worldview_text[:500]}\n\n"
            if prev_chapter_ending:
                user_msg += f"### 上一章结尾\n{prev_chapter_ending[-300:]}\n\n"
            user_msg += f"### 本章正文\n{chapter_content[:4000]}"

            resp = await client.chat.completions.create(
                model=self.llm_cfg.get("model", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.3,
                max_tokens=1500,
            )
            raw = resp.choices[0].message.content.strip()
            return self._parse(chapter_num, raw)

        except Exception as e:
            log.error(f"Quality review failed: {e}")
            return ChapterReview(
                chapter_num=chapter_num,
                overall_score=0,
                scores=[],
                strengths=[],
                issues=[f"评审失败: {e}"],
                suggestions=["请稍后重试"],
            )

    def _parse(self, chapter_num: int, raw: str) -> ChapterReview:
        try:
            clean = re.sub(r"```json\s*|\s*```", "", raw).strip()
            data = json.loads(clean)

            scores = [
                QualityScore(
                    dimension=s.get("dimension", ""),
                    score=float(s.get("score", 0)),
                    comment=s.get("comment", ""),
                )
                for s in (data.get("scores") or [])
            ]
            overall = sum(s.score for s in scores) / len(scores) if scores else 0

            return ChapterReview(
                chapter_num=chapter_num,
                overall_score=round(overall, 1),
                scores=scores,
                strengths=data.get("strengths") or [],
                issues=data.get("issues") or [],
                suggestions=data.get("suggestions") or [],
                character_consistency=data.get("character_consistency") or {},
            )
        except Exception as e:
            log.error(f"Review parse error: {e}")
            return ChapterReview(
                chapter_num=chapter_num, overall_score=0, scores=[],
                strengths=[], issues=["解析失败"], suggestions=[],
            )

    def _mock_review(self, chapter_num: int) -> ChapterReview:
        return ChapterReview(
            chapter_num=chapter_num,
            overall_score=7.5,
            scores=[
                QualityScore("情节", 7.5, "情节推进合理，有起伏"),
                QualityScore("人物", 8.0, "角色行为符合设定"),
                QualityScore("文笔", 7.0, "语言流畅，部分描写可加强"),
                QualityScore("节奏", 7.5, "节奏把控较好"),
                QualityScore("悬念", 7.0, "结尾留有期待"),
            ],
            strengths=["情节推进自然", "角色对话有个性"],
            issues=["部分描写略显冗长"],
            suggestions=["第三段环境描写可精简，聚焦核心冲突"],
            character_consistency={},
        )


# ══════════════════════════════════════════════════
#  角色发展追踪器
# ══════════════════════════════════════════════════

@dataclass
class CharacterArc:
    """角色发展弧线"""
    name: str
    appearances: list[str] = field(default_factory=list)     # 各章节出场记录
    personality_traits: list[str] = field(default_factory=list)  # 性格特征
    development: list[str] = field(default_factory=list)     # 成长轨迹
    relationships: dict[str, str] = field(default_factory=dict)  # 关系变化

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "appearances": self.appearances,
            "personality_traits": self.personality_traits,
            "development": self.development,
            "relationships": self.relationships,
        }


class CharacterTracker:
    """角色发展追踪器 — 跟踪角色在各章节中的一致性和发展"""

    def __init__(self):
        self.characters: dict[str, CharacterArc] = {}

    def register_character(self, name: str, traits: Optional[list[str]] = None, role: str = ""):
        """注册角色"""
        if name not in self.characters:
            self.characters[name] = CharacterArc(
                name=name,
                personality_traits=traits or [],
            )

    def record_appearance(self, name: str, chapter_num: int, summary: str):
        """记录角色出场"""
        if name not in self.characters:
            self.characters[name] = CharacterArc(name=name)
        self.characters[name].appearances.append(f"第{chapter_num}章: {summary}")

    def record_development(self, name: str, chapter_num: int, change: str):
        """记录角色成长/变化"""
        if name in self.characters:
            self.characters[name].development.append(f"第{chapter_num}章: {change}")

    def get_character_summary(self, name: str) -> dict:
        """获取角色概况"""
        if name not in self.characters:
            return {"error": f"角色 {name} 未注册"}
        return self.characters[name].to_dict()

    def get_all_characters(self) -> list[dict]:
        """获取所有角色概况"""
        return [arc.to_dict() for arc in self.characters.values()]

    def get_consistency_report(self) -> dict:
        """生成一致性报告"""
        report = {}
        for name, arc in self.characters.items():
            report[name] = {
                "total_appearances": len(arc.appearances),
                "development_steps": len(arc.development),
                "traits_defined": len(arc.personality_traits),
            }
        return report

    @classmethod
    def from_worldview(cls, worldview) -> "CharacterTracker":
        """从世界观初始化角色追踪器"""
        tracker = cls()
        if not worldview:
            return tracker

        if worldview.protagonist:
            p = worldview.protagonist
            tracker.register_character(
                p.name,
                traits=[p.personality, p.flaw] if p.personality else [],
                role="protagonist",
            )

        for sc in (worldview.supporting_characters or []):
            tracker.register_character(
                sc.name,
                traits=[sc.personality] if sc.personality else [],
                role=sc.role,
            )

        return tracker
