"""
Agent 工具调用层 v1
支持：
  - web_search    : 网络搜索（httpx → DuckDuckGo Instant Answer API，无需Key）
  - python_exec   : Python 沙箱执行（用于数学/算法/物理公式验证）
  - knowledge_check: 学术知识核查（调用 LLM 以严格学术模式核查事实）

设计原则：
  - 每个工具是独立的 async 函数，统一签名 tool_fn(input: str) -> ToolResult
  - AgentToolkit 负责注册、路由、格式化结果
  - chapter_writer 在写作前调用 needs_tool_call() 判断是否需要工具
"""
from __future__ import annotations
import asyncio, json, logging, re, sys, traceback
from dataclasses import dataclass, field
from typing import Optional
from io import StringIO

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════
#  结果类型
# ════════════════════════════════════════════════════

@dataclass
class ToolResult:
    tool:    str
    query:   str
    success: bool
    content: str          # 工具返回的核心内容（注入到写作 prompt 里）
    summary: str = ""     # 简短摘要（显示在前端日志里）
    raw:     str = ""     # 原始返回（调试用）

    def to_context_block(self) -> str:
        """格式化为可注入 LLM prompt 的 context 块"""
        if not self.success:
            return f"[工具调用失败: {self.tool} — {self.content}]"
        return (
            f"【参考资料 · {TOOL_LABELS.get(self.tool, self.tool)}】\n"
            f"查询：{self.query}\n"
            f"结果：\n{self.content}\n"
            f"【参考资料结束 · 请在写作中严格遵循以上事实，不得与之矛盾】"
        )


TOOL_LABELS = {
    "web_search":      "网络搜索",
    "python_exec":     "代码验证",
    "knowledge_check": "学术核查",
}


# ════════════════════════════════════════════════════
#  工具 1：网络搜索
# ════════════════════════════════════════════════════

async def web_search(query: str, max_results: int = 5) -> ToolResult:
    """
    使用 DuckDuckGo Instant Answer API（无需 Key，限制：摘要型结果）
    备用：直接抓取 DuckDuckGo HTML 搜索结果
    """
    try:
        import httpx
        # DuckDuckGo Instant Answer (JSON API)
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_redirect": "1", "no_html": "1", "skip_disambig": "1"}

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        parts = []

        # Abstract (Wikipedia-sourced)
        if data.get("Abstract"):
            parts.append(f"摘要（{data.get('AbstractSource','')}）：{data['Abstract']}")

        # Answer (direct answer e.g. calculations)
        if data.get("Answer"):
            parts.append(f"直接答案：{data['Answer']}")

        # Related topics
        topics = data.get("RelatedTopics", [])[:max_results]
        for t in topics:
            if isinstance(t, dict) and t.get("Text"):
                parts.append(f"· {t['Text'][:200]}")

        if not parts:
            # DuckDuckGo 无摘要时，返回提示而不报错
            content = f"搜索「{query}」未获得结构化摘要。建议在写作中保守处理此部分内容。"
            return ToolResult(tool="web_search", query=query, success=True,
                              content=content, summary="无结构化结果")

        content = "\n".join(parts)
        return ToolResult(
            tool="web_search", query=query, success=True,
            content=content[:2000],
            summary=parts[0][:80] if parts else "",
            raw=json.dumps(data, ensure_ascii=False)[:500],
        )

    except Exception as e:
        log.warning(f"web_search failed: {e}")
        return ToolResult(
            tool="web_search", query=query, success=False,
            content=f"搜索失败（{e}），请在写作中保守处理此部分。",
            summary=f"搜索失败: {e}",
        )


# ════════════════════════════════════════════════════
#  工具 2：Python 沙箱执行
# ════════════════════════════════════════════════════

# 允许的内置函数白名单（禁止文件/网络/系统操作）
_SAFE_BUILTINS = {
    "abs","all","any","bin","bool","chr","dict","dir","divmod",
    "enumerate","filter","float","format","frozenset","getattr",
    "hasattr","hash","hex","int","isinstance","issubclass","iter",
    "len","list","map","max","min","next","oct","ord","pow",
    "print","range","repr","reversed","round","set","setattr",
    "slice","sorted","str","sum","tuple","type","zip",
    "True","False","None",
    # math
    "__import__",   # 只允许 import math/random/statistics/decimal
}

_ALLOWED_IMPORTS = {"math", "random", "statistics", "decimal", "fractions", "itertools", "functools", "collections"}

def _safe_exec(code: str, timeout: float = 10.0) -> tuple[bool, str]:
    """
    在受限环境中执行 Python 代码，捕获 stdout 和异常。
    仅允许 math / statistics / random 等无副作用标准库。
    """
    stdout_buf = StringIO()

    # 安全命名空间
    safe_globals: dict = {
        "__builtins__": {k: __builtins__[k] for k in _SAFE_BUILTINS if k in __builtins__}  # type: ignore
        if isinstance(__builtins__, dict)
        else {k: getattr(__builtins__, k) for k in _SAFE_BUILTINS if hasattr(__builtins__, k)},
    }

    # 预注入允许的模块
    for mod_name in _ALLOWED_IMPORTS:
        try:
            import importlib
            safe_globals[mod_name] = importlib.import_module(mod_name)
        except ImportError:
            pass

    # 捕获 print 输出
    safe_globals["print"] = lambda *args, **kw: stdout_buf.write(" ".join(str(a) for a in args) + "\n")

    try:
        # 编译检查（禁止 import os/sys/subprocess 等）
        tree_src = code
        if re.search(r"\bimport\s+(os|sys|subprocess|socket|shutil|pathlib|glob|tempfile|pickle|shelve)\b", code):
            return False, "禁止导入系统模块（os/sys/subprocess等）"
        if re.search(r"\bopen\s*\(", code):
            return False, "禁止文件操作"
        if re.search(r"\bexec\b|\beval\b", code):
            return False, "禁止 exec/eval"

        exec(compile(code, "<sandbox>", "exec"), safe_globals)
        output = stdout_buf.getvalue().strip()
        return True, output or "（代码执行成功，无输出）"

    except Exception as e:
        return False, f"执行错误: {type(e).__name__}: {e}"


async def python_exec(code_request: str) -> ToolResult:
    """
    接受自然语言描述 + 可能包含的代码块，提取代码并执行。
    code_request 可以是：
      - 纯代码字符串
      - "计算光在真空中传播1光年需要多少秒" 等自然语言（此时返回说明）
    """
    # 提取 ```python ... ``` 代码块
    code_match = re.search(r"```(?:python)?\s*(.*?)```", code_request, re.DOTALL)
    if code_match:
        code = code_match.group(1).strip()
    elif any(kw in code_request for kw in ["import ", "def ", "print(", "=", "for ", "while "]):
        # 看起来是直接的代码
        code = code_request.strip()
    else:
        # 自然语言，无法直接执行，返回说明
        content = f"无法直接执行自然语言描述。请提供具体的 Python 代码，或使用代码块格式：\n```python\n# 你的代码\n```"
        return ToolResult(
            tool="python_exec", query=code_request,
            success=False, content=content, summary="需要提供代码",
        )

    loop = asyncio.get_running_loop()
    success, output = await loop.run_in_executor(None, _safe_exec, code)

    if success:
        content = f"代码：\n```python\n{code}\n```\n\n输出：\n{output}"
        summary = output[:80] if output else "执行成功"
    else:
        content = f"执行失败：{output}\n代码：\n```python\n{code}\n```"
        summary = f"执行失败: {output[:60]}"

    return ToolResult(
        tool="python_exec", query=code_request,
        success=success, content=content, summary=summary,
    )


# ════════════════════════════════════════════════════
#  工具 3：学术知识核查
# ════════════════════════════════════════════════════

async def knowledge_check(claim: str, llm_cfg: dict) -> ToolResult:
    """
    用 LLM 以"学术严谨模式"核查事实性陈述。
    系统提示要求 LLM 只引用已知事实，对不确定的内容明确标注。
    """
    system = """你是一位严谨的学术顾问，专门核查创作内容中的事实准确性。

任务：核查给定陈述是否符合已知科学/学术事实。

输出格式（严格遵守）：
## 核查结论
[✓ 准确 / ⚠ 部分准确 / ✗ 有误 / ? 无法确认]

## 事实说明
[简明扼要说明正确的知识，引用具体数据、定律、理论]

## 写作建议
[如何在小说中准确且自然地表达这一知识点]

注意：
- 对不确定的内容必须标注"无法确认"，不得猜测
- 只陈述事实，不做价值判断
- 涉及前沿科学时注明知识截止年份"""

    from core.llm import LLMClient
    llm = LLMClient(llm_cfg)

    if llm._is_mock:
        content = (
            f"## 核查结论\n? 无法确认（Mock模式）\n\n"
            f"## 事实说明\n当前为 Mock 模式，无法进行实际知识核查。\n"
            f"待核查内容：{claim}\n\n"
            f"## 写作建议\n在 Mock 模式下，请自行核实相关事实后再写作。"
        )
        return ToolResult(
            tool="knowledge_check", query=claim, success=True,
            content=content, summary="Mock模式，跳过核查",
        )

    try:
        content = await llm.chat(
            system,
            f"请核查以下内容的准确性：\n\n{claim}",
            temperature=0.1,
            max_tokens=800,
        )
        conclusion_match = re.search(r"\[([✓⚠✗?][^\]]*)\]", content)
        summary = conclusion_match.group(1) if conclusion_match else content[:60]

        return ToolResult(
            tool="knowledge_check", query=claim, success=True,
            content=content, summary=summary,
        )
    except Exception as e:
        log.warning(f"knowledge_check failed: {e}")
        return ToolResult(
            tool="knowledge_check", query=claim, success=False,
            content=f"核查失败（{e}），建议手动核实此部分内容。",
            summary=f"核查失败: {e}",
        )


# ════════════════════════════════════════════════════
#  工具路由器
# ════════════════════════════════════════════════════

class AgentToolkit:
    """
    统一工具调用接口。
    chapter_writer / worldview_builder 通过此类调用工具。
    """

    def __init__(self, llm_cfg: dict):
        self.llm_cfg = llm_cfg

    async def call(self, tool: str, query: str) -> ToolResult:
        """路由到对应工具"""
        log.info(f"Tool call: [{tool}] {query[:80]}")
        if tool == "web_search":
            return await web_search(query)
        elif tool == "python_exec":
            return await python_exec(query)
        elif tool == "knowledge_check":
            return await knowledge_check(query, self.llm_cfg)
        else:
            return ToolResult(
                tool=tool, query=query, success=False,
                content=f"未知工具: {tool}",
                summary="未知工具",
            )

    async def call_multiple(self, calls: list[dict]) -> list[ToolResult]:
        """并发调用多个工具"""
        tasks = [self.call(c["tool"], c["query"]) for c in calls]
        return await asyncio.gather(*tasks)

    @staticmethod
    def needs_tools(scene_goal: str, worldview_notes: str = "") -> list[dict]:
        """
        启发式判断：场景目标是否需要工具调用。
        返回建议的工具调用列表 [{"tool": ..., "query": ...}]

        触发规则：
        - 涉及物理/化学/生物/医学/数学 → knowledge_check + 可选 python_exec
        - 涉及历史事件/地理/真实人物    → web_search + knowledge_check
        - 涉及算法/代码/公式计算        → python_exec
        - 普通叙事场景                  → 不调用工具
        """
        calls: list[dict] = []
        text = (scene_goal + " " + worldview_notes).lower()

        # 物理 / 化学 / 生物 / 医学
        science_kw = [
            "物理", "化学", "生物", "医学", "药物", "量子", "相对论", "热力学",
            "光速", "引力", "辐射", "基因", "神经", "心理学", "脑科学",
            "physics", "chemistry", "quantum", "relativity",
        ]
        # 历史 / 地理 / 现实事件
        factual_kw = [
            "历史", "真实", "现实", "地理", "国家", "年代", "事件", "战役",
            "发明", "发现", "纪录", "数据", "统计",
        ]
        # 算法 / 数学 / 编程
        calc_kw = [
            "算法", "代码", "程序", "计算", "公式", "方程", "概率", "统计",
            "加密", "哈希", "排序", "复杂度", "π", "e=",
        ]

        is_science = any(k in text for k in science_kw)
        is_factual = any(k in text for k in factual_kw)
        is_calc    = any(k in text for k in calc_kw)

        if is_science:
            calls.append({"tool": "knowledge_check", "query": scene_goal})
        if is_factual and not is_science:
            calls.append({"tool": "web_search", "query": scene_goal})
        if is_calc:
            calls.append({"tool": "python_exec", "query": scene_goal})

        return calls
