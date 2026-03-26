# Creation Studio · Multi-Agent 创作工作室

> 漫剧生成 + 小说写作双引擎，Multi-Agent 架构，React 前端

## 功能

- **小说写作工作台** — 对话式 AI 协作写作，支持世界观构建、大纲规划、章节创作多 Agent 流转
- **漫剧生成工作台** — 从大纲到配音到视频，Agent 自动化流水线
- **AI 视频生成** — 火山引擎 Seedance 模型，从剧本描述直接生成视频片段
- **质量评审** — 章节完成后自动多维度评分 + 修改建议
- **灵感面板** — 基于创意自动推荐相关作品与写作技巧
- **系统配置** — LLM/TTS/视频提供 商切换、提示词管理

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + Vite 5 + TypeScript |
| 状态管理 | Zustand |
| 路由 | React Router v6 |
| 样式 | CSS Modules + CSS Variables |
| 后端 | FastAPI + Python 3.10+ |
| LLM | OpenAI / DeepSeek（兼容 openai SDK）|
| TTS | **edge-tts**（默认免费）/ 火山引擎 / OpenAI / ElevenLabs |
| 视频生成 | **火山引擎 Seedance 2.0** + 直接上传 |
| 实时通信 | WebSocket + SSE |
| 数据持久化 | JSON 文件 |

## 项目结构

```
├── backend/
│   ├── main.py                     # FastAPI 入口
│   ├── requirements.txt
│   ├── .env.example
│   ├── core/
│   │   ├── config.py               # 环境变量
│   │   ├── config_store.py         # 系统配置持久化
│   │   ├── models.py               # 漫剧数据模型
│   │   ├── novel_models.py         # 小说数据模型
│   │   ├── outline_store.py        # 大纲存储
│   │   ├── novel_store.py          # 小说会话存储
│   │   └── ws_manager.py           # WebSocket 管理
│   └── agents/
│       ├── novel_agent.py          # 小说主 Agent（流式支持）
│       ├── worldview_builder.py    # 世界观构建
│       ├── outline_planner.py      # 情节规划 + 动态追加
│       ├── chapter_writer.py       # 场景分解 + 逐场景创作
│       ├── quality_reviewer.py     # 质量评审 + 角色追踪
│       ├── inspiration_engine.py   # 灵感推荐
│       ├── agent_tools.py          # 工具调用（搜索/代码/核查）
│       ├── outline_gen.py          # 漫剧大纲生成
│       └── pipeline_agents.py      # 配音 + 视频生成 + 剪辑
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx                 # 路由
│       ├── api/                    # API 客户端
│       ├── stores/                 # Zustand 状态
│       ├── components/
│       │   ├── shared/             # Layout、导航
│       │   ├── novel/              # 小说写作组件
│       │   └── manga/              # 漫剧组件
│       └── pages/
│           ├── NovelStudio.tsx     # 小说工作台
│           ├── MangaStudio.tsx     # 漫剧工作台
│           └── ConfigPanel.tsx     # 配置面板
│
└── README.md
```

## 快速启动

### 后端

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # 填入 API Key（或使用 mock 免费调试）
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173`，默认跳转至小说写作工作台。

## 环境变量

```env
# LLM（二选一，或使用 mock 免费调试）
OPENAI_API_KEY=sk-xxx
DEEPSEEK_API_KEY=sk-xxx

# TTS 配音 — edge_tts 免费默认，无需配置
# 可选：火山引擎 TTS
VOLCENGINE_TTS_APP_ID=
VOLCENGINE_TTS_ACCESS_KEY=
VOLCENGINE_TTS_SECRET_KEY=

# 视频生成 — 火山引擎 Seedance
VOLCENGINE_VIDEO_API_KEY=
VOLCENGINE_VIDEO_MODEL=seedance-2.0
```

## Agent 架构

### 小说写作 Agent

```
INIT → COLLECTING → WORLDVIEW_BUILDING → WORLDVIEW_REVIEW
     → OUTLINE_PLANNING → OUTLINE_REVIEW
     → CHAPTER_WRITING(n) → [自动质量评审] → CHAPTER_DONE(n)
     → COMPLETE
```

| Agent | 职责 |
|-------|------|
| `NovelAgent` | 会话路由、状态机管理、流式输出 |
| `WorldviewBuilder` | 需求澄清 + 世界观生成 |
| `OutlinePlanner` | 章节规划 + 每3章动态追加 |
| `ChapterWriter` | 场景分解 + 逐场景创作 + 工具调用 |
| `QualityReviewer` | 多维度评分 + 角色一致性检查 |
| `InspirationEngine` | 灵感推荐（带缓存）|
| `AgentToolkit` | 网络搜索 / Python执行 / 学术核查 |

### 漫剧流水线

```
voice_actor (edge-tts) → video_gen (Seedance) → video_editor (剪映/MoviePy)
```

## TTS 选型说明

| 提供商 | 费用 | 中文质量 | 需要 Key |
|--------|------|---------|---------|
| **edge-tts** | 免费 | 优秀 | 否 |
| 火山引擎 TTS | ~¥0.02/千次 | 优秀 | 是 |
| OpenAI TTS | ~$15/1M字符 | 良好 | 是 |
| ElevenLabs | $5/月起 | 良好 | 是 |
