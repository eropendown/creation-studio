"""
大纲生成 Agent v5
核心改进：
1. 三步分批生成（分析→章节结构→分镜），每步独立 LLM 调用
2. 分镜按每批 3-4 个生成，彻底解决 token 截断问题
3. 支持小说文本导入（自动提取情节节点）
4. 所有字段强制完整，生成后校验
"""
import asyncio, json, logging, re, time
from typing import List, Optional
from core.models import (
    OutlineRequest, NovelImportRequest,
    ScriptOutline, SceneItem, Character, PlotPoint, Act,
    SystemConfig, AgentPrompts,
)

log = logging.getLogger(__name__)

EMOTIONS = ["震惊","愤怒","柔情","紧张","释然","悲伤","喜悦","绝望","坚定","迷茫"]
CAMERAS  = ["俯拍全景","仰拍特写","近景特写","侧面中景","跟拍运镜","固定长镜","慢推镜头","急速切换"]

STYLE_EN = {
    "古风仙侠": "ancient Chinese xianxia fantasy, traditional ink painting style, flowing hanfu robes, misty mountains, celestial atmosphere",
    "赛博朋克": "cyberpunk style, neon lights, holographic displays, rain-slicked streets, high-tech low-life",
    "都市言情": "modern urban romance, soft cinematic lighting, contemporary fashion, city skyline",
    "热血漫画": "shonen manga style, dynamic action poses, speed lines, bold ink outlines, vibrant colors",
    "悬疑惊悚": "noir thriller, dramatic chiaroscuro lighting, deep shadows, suspenseful atmosphere, desaturated tones",
    "甜宠日常": "cozy romance, warm pastel colors, soft lighting, cute everyday moments",
    "复仇爽文": "power fantasy, dramatic lighting, imposing presence, cold aura, satisfying revenge moment",
    "穿越重生": "time-slip fantasy, dual era aesthetics, nostalgic warmth meets modern clarity",
    "末世废土": "post-apocalyptic wasteland, rust and decay, blood-red sky, survival tension",
}


# ══════════════════════════════════════════════════════════
#  LLM 工具函数
# ══════════════════════════════════════════════════════════

async def _llm(system: str, user: str, cfg: SystemConfig, label="") -> str:
    """单次 LLM 调用，返回原始文本"""
    from openai import AsyncOpenAI
    llm = cfg.llm
    client = AsyncOpenAI(api_key=llm.api_key, base_url=llm.base_url)
    log.info(f"LLM call [{label}] model={llm.model} max_tokens={llm.max_tokens}")
    resp = await client.chat.completions.create(
        model=llm.model,
        messages=[{"role":"system","content":system},{"role":"user","content":user}],
        temperature=llm.temperature,
        max_tokens=llm.max_tokens,
        timeout=llm.timeout,
    )
    txt = resp.choices[0].message.content.strip()
    finish = resp.choices[0].finish_reason
    if finish == "length":
        log.warning(f"[{label}] TRUNCATED by max_tokens! Consider increasing max_tokens or reducing batch size.")
    return txt


def _parse_json(raw: str, label="") -> dict | list:
    """健壮地解析 JSON，处理常见问题"""
    # 去除 markdown code block
    raw = re.sub(r"```json\s*", "", raw)
    raw = re.sub(r"```\s*", "", raw)
    raw = raw.strip()

    # 尝试直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 截断修复：找最后一个完整的 } 或 ]
    # 对于数组
    if raw.startswith("["):
        # 找最后一个完整的 }
        last_close = raw.rfind("},")
        if last_close == -1:
            last_close = raw.rfind("}")
        if last_close > 0:
            truncated = raw[:last_close+1] + "]"
            try:
                result = json.loads(truncated)
                log.warning(f"[{label}] JSON array was truncated, recovered {len(result)} items")
                return result
            except: pass

    # 对于对象
    if raw.startswith("{"):
        # 尝试逐步缩短找到有效 JSON
        for i in range(len(raw)-1, 0, -10):
            candidate = raw[:i]
            # 找最后一个完整键值对结束位置
            end = candidate.rfind(",\n")
            if end > 0:
                candidate = candidate[:end] + "\n}"
                try:
                    return json.loads(candidate)
                except: pass

    raise ValueError(f"[{label}] Cannot parse JSON: {raw[:200]}...")


# ══════════════════════════════════════════════════════════
#  步骤1：分析文本
# ══════════════════════════════════════════════════════════

async def _step1_analyze(text: str, cfg: SystemConfig, glog: list) -> dict:
    """分析小说/简介，提取基础信息"""
    sys_p  = cfg.prompts.analyze_system
    user_p = f"请分析以下文本并提取故事要素：\n\n{text[:6000]}"  # 限制输入长度

    glog.append(f"[步骤1] 分析文本（长度:{len(text)}字）")
    raw  = await _llm(sys_p, user_p, cfg, "analyze")
    data = _parse_json(raw, "analyze")
    glog.append(f"[步骤1] 完成：提取 {len(data.get('characters',[]))} 个角色，{len(data.get('plot_points',[]))} 个情节节点")
    return data


# ══════════════════════════════════════════════════════════
#  步骤2：生成章节结构
# ══════════════════════════════════════════════════════════

async def _step2_structure(analysis: dict, scene_count: int, style: str,
                            cfg: SystemConfig, glog: list) -> dict:
    """生成起承转合章节结构"""
    sys_p = cfg.prompts.structure_system
    user_p = (
        f"基于以下故事分析，生成章节结构（共需约 {scene_count} 个分镜）：\n\n"
        f"标题：{analysis.get('title','')}\n"
        f"核心冲突：{analysis.get('core_conflict','')}\n"
        f"简介：{analysis.get('synopsis','')[:500]}\n"
        f"画风风格：{style}（{STYLE_EN.get(style,'')}）\n"
        f"主要角色：{json.dumps([{'name':c['name'],'role':c['role']} for c in analysis.get('characters',[])], ensure_ascii=False)}\n"
        f"情节节点：{json.dumps(analysis.get('plot_points',[])[:8], ensure_ascii=False)}\n"
        f"主题：{analysis.get('themes','')}\n"
        f"基调：{analysis.get('tone','')}"
    )

    glog.append(f"[步骤2] 生成章节结构")
    raw  = await _llm(sys_p, user_p, cfg, "structure")
    data = _parse_json(raw, "structure")
    glog.append(f"[步骤2] 完成：{len(data.get('acts',[]))} 幕章节")
    return data


# ══════════════════════════════════════════════════════════
#  步骤3：分批生成分镜
# ══════════════════════════════════════════════════════════

BATCH_SIZE = 3  # 每批生成3个，防止截断

async def _step3_scenes_batch(
    batch_ids: list, act_info: dict, analysis: dict,
    style: str, all_previous: list,
    cfg: SystemConfig, glog: list
) -> list:
    """生成一批分镜"""
    sys_p  = cfg.prompts.scene_batch_system
    style_desc = STYLE_EN.get(style, style)
    pfx = cfg.prompts.art_style_prefix

    prev_summary = ""
    if all_previous:
        last = all_previous[-2:] if len(all_previous)>=2 else all_previous
        prev_summary = "前序分镜摘要：" + "；".join([f"第{s['scene_id']}镜：{s['narration']}" for s in last])

    chars_desc = json.dumps(
        [{"name":c["name"],"role":c["role"],"appearance":c.get("appearance","")} for c in analysis.get("characters",[])],
        ensure_ascii=False
    )

    user_p = (
        f"请为以下情节生成第 {batch_ids[0]}-{batch_ids[-1]} 号分镜，共 {len(batch_ids)} 个。\n\n"
        f"【作品信息】\n"
        f"标题：{analysis.get('title','')}\n"
        f"画风：{style}（{style_desc}）\n"
        f"{'全局风格前缀：'+pfx if pfx else ''}\n"
        f"主要角色：{chars_desc}\n\n"
        f"【当前幕次】第 {act_info.get('act',1)} 幕：{act_info.get('title','')}\n"
        f"本幕情节：{act_info.get('description','')}\n"
        f"情绪走向：{act_info.get('emotional_arc','')}\n"
        f"关键事件：{'、'.join(act_info.get('key_events',[]))}\n\n"
        f"{prev_summary}\n\n"
        f"【分镜要求】\n"
        f"- scene_id 从 {batch_ids[0]} 到 {batch_ids[-1]}\n"
        f"- act = {act_info.get('act',1)}\n"
        f"- 必须生成恰好 {len(batch_ids)} 个分镜\n"
        f"- visual_description 每条 ≥ 60 字\n"
        f"- image_prompt 为英文，≥ 60 词\n"
        f"- 情绪标签从以下选择：震惊/愤怒/柔情/紧张/释然/悲伤/喜悦/绝望/坚定/迷茫"
    )

    raw  = await _llm(sys_p, user_p, cfg, f"scenes_{batch_ids[0]}-{batch_ids[-1]}")
    data = _parse_json(raw, f"scenes_batch_{batch_ids[0]}")

    if not isinstance(data, list):
        data = data.get("scenes", data.get("scene_breakdown", [data] if isinstance(data, dict) else []))

    # 修正 scene_id
    for i, item in enumerate(data):
        expected_id = batch_ids[i] if i < len(batch_ids) else batch_ids[-1] + i
        item["scene_id"] = expected_id
        item["act"] = act_info.get("act", 1)
        # 补全必填字段
        if not item.get("image_prompt"):
            item["image_prompt"] = f"{style_desc}, scene {expected_id}, {item.get('emotion','dramatic')}, masterpiece, best quality, highly detailed, 8k"
        if not item.get("negative_prompt"):
            item["negative_prompt"] = "lowres, bad anatomy, bad hands, text, watermark, blurry, deformed, ugly"
        if pfx and item.get("image_prompt"):
            item["image_prompt"] = pfx + ", " + item["image_prompt"]

    glog.append(f"[步骤3] 批次 {batch_ids[0]}-{batch_ids[-1]} 生成 {len(data)} 个分镜")
    return data


async def _step3_all_scenes(
    analysis: dict, structure: dict,
    total_scenes: int, style: str,
    cfg: SystemConfig, glog: list
) -> list:
    """按幕次分配并批量生成所有分镜"""
    acts  = structure.get("acts", [])
    if not acts:
        acts = [{"act":1,"title":"起承转合","description":analysis.get("synopsis",""),"emotional_arc":"平静→高潮→释然","key_events":[],"character_focus":[],"scene_count_suggest":total_scenes}]

    # 按幕次分配分镜数量
    act_scene_map = []
    total_suggest = sum(a.get("scene_count_suggest",3) for a in acts) or len(acts)*3
    remaining = total_scenes
    for i, act in enumerate(acts):
        if i == len(acts)-1:
            cnt = remaining
        else:
            cnt = max(1, round(act.get("scene_count_suggest",3) / total_suggest * total_scenes))
            remaining -= cnt
        act_scene_map.append((act, cnt))

    glog.append(f"[步骤3] 分配：{[(a['title'],c) for a,c in act_scene_map]}")

    all_scenes = []
    sid = 1
    for act, cnt in act_scene_map:
        # 按 BATCH_SIZE 批次处理
        for batch_start in range(0, cnt, BATCH_SIZE):
            batch_cnt  = min(BATCH_SIZE, cnt - batch_start)
            batch_ids  = list(range(sid, sid + batch_cnt))
            batch_data = await _step3_scenes_batch(
                batch_ids, act, analysis, style,
                all_scenes[-4:], cfg, glog  # 传入最近4个场景作为上下文
            )
            all_scenes.extend(batch_data)
            sid += batch_cnt
            await asyncio.sleep(0.5)  # 避免速率限制

    return all_scenes[:total_scenes]




# ══════════════════════════════════════════════════════════
#  主生成函数
# ══════════════════════════════════════════════════════════

async def generate_outline(
    genre: str, synopsis: str, style: str,
    scene_count: int, cfg: SystemConfig,
    glog: list = None,
) -> ScriptOutline:
    """从简介生成大纲"""
    if glog is None: glog = []
    if cfg.llm.provider == "mock":
        raise ValueError(
            "LLM 提供商设置为 Mock，无法生成真实大纲。\n"
            "请前往「系统配置 → LLM 大模型」将提供商改为 openai 或 deepseek，并填写有效的 API Key。"
        )

    # 步骤1：分析
    analysis = await _step1_analyze(f"类型：{genre}\n画风：{style}\n简介：{synopsis}", cfg, glog)
    analysis.setdefault("title", f"【{genre}】{synopsis[:12]}…")
    analysis.setdefault("synopsis", synopsis)

    # 步骤2：章节结构
    structure = await _step2_structure(analysis, scene_count, style, cfg, glog)

    # 步骤3：分批分镜
    raw_scenes = await _step3_all_scenes(analysis, structure, scene_count, style, cfg, glog)

    return _assemble(analysis, structure, raw_scenes, genre, synopsis, style, scene_count, "manual", glog)


async def import_novel(req: NovelImportRequest, cfg: SystemConfig) -> ScriptOutline:
    """从小说文本导入生成大纲"""
    glog = []
    if cfg.llm.provider == "mock":
        raise ValueError(
            "LLM 提供商设置为 Mock，无法生成真实大纲。\n"
            "请前往「系统配置 → LLM 大模型」将提供商改为 openai 或 deepseek，并填写有效的 API Key。"
        )

    # 截取文本（过长则智能截取重点段落）
    text = req.novel_text
    focus = req.focus_range
    text_for_analysis = _extract_key_text(text, focus, max_chars=5000)

    glog.append(f"[小说导入] 原文长度:{len(text)}字，分析片段:{len(text_for_analysis)}字")

    analysis = await _step1_analyze(
        f"小说标题：{req.novel_title}\n重点范围：{focus}\n\n正文片段：\n{text_for_analysis}",
        cfg, glog
    )
    if req.novel_title:
        analysis["title"] = req.novel_title

    structure = await _step2_structure(analysis, req.scene_count, req.style, cfg, glog)
    raw_scenes = await _step3_all_scenes(analysis, structure, req.scene_count, req.style, cfg, glog)

    outline = _assemble(analysis, structure, raw_scenes,
                        analysis.get("genre","小说改编"), analysis.get("synopsis",""),
                        req.style, req.scene_count, "novel", glog)
    outline.source_title   = req.novel_title or analysis.get("title","")
    outline.source_excerpt = text[:300] + "…" if len(text)>300 else text
    return outline


def _extract_key_text(text: str, focus: str, max_chars: int) -> str:
    """智能截取小说关键段落"""
    if len(text) <= max_chars:
        return text

    if focus:
        # 尝试找到指定章节关键词
        keywords = re.findall(r"第[一二三四五六七八九十\d]+章|chapter\s*\d+", focus, re.IGNORECASE)
        for kw in keywords:
            idx = text.find(kw)
            if idx >= 0:
                return text[idx:idx+max_chars]

    # 默认：取开头2000字 + 中间1000字 + 结尾2000字
    head = text[:2000]
    mid_start = len(text)//2 - 500
    mid  = text[mid_start:mid_start+1000]
    tail = text[-2000:]
    combined = head + "\n\n[...中间省略...]\n\n" + mid + "\n\n[...中间省略...]\n\n" + tail
    return combined[:max_chars]


def _assemble(
    analysis: dict, structure: dict, raw_scenes: list,
    genre: str, synopsis: str, style: str,
    scene_count: int, source_type: str, glog: list
) -> ScriptOutline:
    """组装最终 ScriptOutline"""
    # Characters
    chars = []
    for c in analysis.get("characters", []):
        chars.append(Character(
            name=c.get("name",""), role=c.get("role","配角"),
            description=c.get("description",""), appearance=c.get("appearance",""),
            motivation=c.get("motivation",""),
        ))
    if not chars:
        chars = [Character(name="主角", role="主角", description="核心人物")]

    # Plot points
    plots = []
    for p in analysis.get("plot_points", []):
        plots.append(PlotPoint(
            order=p.get("order",0), title=p.get("title",""),
            content=p.get("content",""), emotion=p.get("emotion",""),
            importance=p.get("importance","medium"),
        ))

    # Acts
    acts = []
    for a in structure.get("acts", []):
        acts.append(Act(
            act=a.get("act",1), title=a.get("title",""),
            description=a.get("description",""),
            emotional_arc=a.get("emotional_arc",""),
            key_events=a.get("key_events",[]),
            character_focus=a.get("character_focus",[]),
            scene_count_suggest=a.get("scene_count_suggest",3),
        ))

    # Scenes — 补全缺失字段
    scenes = []
    style_en = STYLE_EN.get(style, style)
    for i, s in enumerate(raw_scenes[:scene_count]):
        sid = i + 1
        sc  = SceneItem(
            scene_id=sid,
            act=s.get("act",1),
            title=s.get("title",f"第{sid}镜"),
            visual_description=s.get("visual_description","") or f"画面{sid}",
            narration=s.get("narration","") or "故事继续。",
            character_name=s.get("character_name",chars[0].name if chars else "主角"),
            emotion=s.get("emotion","坚定"),
            camera_shot=s.get("camera_shot","近景特写"),
            duration_estimate=float(s.get("duration_estimate",3.5)),
            image_prompt=s.get("image_prompt","") or f"{style_en}, scene {sid}, masterpiece, best quality",
            negative_prompt=s.get("negative_prompt","lowres, bad anatomy, bad hands, text, watermark, blurry"),
            status="prompt_ready",
        )
        scenes.append(sc)

    total_dur = sum(s.duration_estimate for s in scenes)
    hook      = structure.get("hook","") or (scenes[0].narration if scenes else "")

    return ScriptOutline(
        source_type=source_type,
        title=analysis.get("title", f"【{genre}】"),
        genre=genre, style=style,
        synopsis=analysis.get("synopsis", synopsis),
        core_conflict=analysis.get("core_conflict",""),
        themes=analysis.get("themes",[]),
        tone=analysis.get("tone",""),
        production_notes=structure.get("production_notes",""),
        word_count_estimate=int(analysis.get("word_count_estimate", scene_count * 80)),
        estimated_duration=round(total_dur,1),
        characters=chars,
        plot_points=plots,
        acts=acts,
        scene_breakdown=scenes,
        total_scenes=len(scenes),
        tags=[genre, style, "漫剧", "短视频"],
        hook=hook,
        climax_scene=max(1, len(scenes)-2),
        climax_description=structure.get("climax_description",""),
        ending_type=structure.get("ending_type","开放式结局"),
        outline_status="draft",
        generation_log=glog,
    )


# ══════════════════════════════════════════════════════════
#  内存存储
# ══════════════════════════════════════════════════════════
_STORE: dict[str, ScriptOutline] = {}
def outline_save(o: ScriptOutline): _STORE[o.outline_id] = o
def outline_get(oid: str): return _STORE.get(oid)
def outline_list(): return list(_STORE.values())