# 创作工作室 · Multi-Agent System v6

> 漫剧生成 + 小说写作双引擎，统一 Agent 架构，React 前端

---

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    React + Vite 前端                      │
│   /manga  漫剧工作台   │   /novel  小说写作工作台          │
│   WebSocket 实时推送   │   SSE / WS 流式对话              │
└────────────────┬────────────────────────────────────────┘
                 │ HTTP + WebSocket
┌────────────────▼────────────────────────────────────────┐
│              FastAPI 后端 v6                              │
│  /api/manga/*   漫剧 API   │  /api/novel/*  小说 API      │
│  /ws/{job_id}  WS          │  /ws/novel/{sid} WS          │
└────────┬────────────────────────┬───────────────────────┘
         │                        │
┌────────▼──────────┐  ┌──────────▼──────────────────────┐
│  漫剧 Agent 链      │  │   小说写作 Agent 链               │
│  ┌─────────────┐  │  │  ┌──────────────────────────┐   │
│  │ outline_gen │  │  │  │ novel_session_manager     │   │
│  │ voice_actor │  │  │  │  ├─ worldview_builder     │   │
│  │ video_editor│  │  │  │  ├─ outline_planner       │   │
│  └─────────────┘  │  │  │  ├─ chapter_writer        │   │
└───────────────────┘  │  │  └──────────────────────┘   │
                        │  └──────────────────────────────┘
                        │
              ┌──────────▼──────────────┐
              │   LLM Provider Layer     │
              │  OpenAI / DeepSeek / Mock│
              └─────────────────────────┘
```

---

## 项目目录结构

```
project/
├── backend/                    # FastAPI 后端
│   ├── main.py                 # 应用入口，路由注册
│   ├── requirements.txt
│   ├── .env.example
│   ├── core/
│   │   ├── config.py           # 环境变量 (pydantic-settings)
│   │   ├── config_store.py     # 系统配置持久化
│   │   ├── models.py           # 全局数据模型 (Pydantic v2)
│   │   ├── novel_models.py     # 小说专用模型
│   │   ├── outline_store.py    # 漫剧大纲存储
│   │   ├── novel_store.py      # 小说会话存储
│   │   └── ws_manager.py       # WebSocket 管理器
│   └── agents/
│       ├── outline_gen.py      # 漫剧大纲生成
│       ├── pipeline_agents.py  # 配音 + 剪辑
│       ├── novel_agent.py      # 小说写作主 Agent（NEW）
│       ├── worldview_builder.py # 世界观构建子 Agent（NEW）
│       ├── outline_planner.py  # 情节规划子 Agent（NEW）
│       └── chapter_writer.py   # 章节创作子 Agent（NEW）
│
├── frontend/                   # React + Vite 前端
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx             # 路由 + 全局布局
│       ├── api/
│       │   ├── manga.ts        # 漫剧 API 客户端
│       │   └── novel.ts        # 小说 API 客户端
│       ├── hooks/
│       │   ├── useWebSocket.ts # WS 连接管理
│       │   └── useNovelSession.ts
│       ├── stores/
│       │   ├── mangaStore.ts   # Zustand 漫剧状态
│       │   └── novelStore.ts   # Zustand 小说状态
│       ├── components/
│       │   ├── shared/
│       │   │   ├── Layout.tsx
│       │   │   ├── Sidebar.tsx
│       │   │   └── StatusBadge.tsx
│       │   ├── manga/
│       │   │   ├── OutlineForm.tsx
│       │   │   ├── SceneGrid.tsx
│       │   │   ├── PipelinePanel.tsx
│       │   │   └── HistoryPanel.tsx
│       │   └── novel/
│       │       ├── NovelChat.tsx   # 主对话界面
│       │       ├── WorldviewPanel.tsx
│       │       ├── OutlinePanel.tsx
│       │       └── ChapterPanel.tsx
│       └── pages/
│           ├── MangaStudio.tsx
│           └── NovelStudio.tsx
│
└── README.md
```

---

## 技术方案选型

| 层级 | 技术 | 选择理由 |
|------|------|---------|
| 前端框架 | React 18 + Vite 5 | 生态成熟，HMR 极快 |
| 状态管理 | Zustand | 轻量，无 boilerplate |
| 路由 | React Router v6 | 标准方案 |
| 样式 | CSS Modules + CSS Variables | 零运行时，主题可控 |
| 动画 | CSS transitions + keyframes | 无依赖，性能优 |
| WS 客户端 | 原生 WebSocket + 自定义 hook | 无多余依赖 |
| 后端框架 | FastAPI 0.115 | 异步优先，自动文档 |
| LLM SDK | openai >= 1.45 (兼容 DeepSeek) | 统一接口 |
| 数据持久化 | JSON 文件 + 内存缓存 | 轻量，无需 DB |
| 配置管理 | pydantic-settings + .env | 类型安全 |

---

## 小说写作 Agent 架构

### 会话状态机

```
INIT → WORLDVIEW_BUILDING → WORLDVIEW_CONFIRMED
     → OUTLINE_PLANNING   → OUTLINE_CONFIRMED
     → CHAPTER_WRITING(n) → CHAPTER_DONE(n)
     → [触发规划更新 每3章]
     → COMPLETE
```

### Agent 分工

| Agent | 职责 | 触发时机 |
|-------|------|---------|
| `NovelSessionManager` | 会话路由、状态机管理 | 每次用户消息 |
| `WorldviewBuilder` | 需求澄清 + 世界观文档生成 | 阶段一 |
| `OutlinePlanner` | 初始章节规划 + 动态追加 | 阶段二 + 每3章 |
| `ChapterWriter` | 场景分解 + 逐场景创作 | 阶段三 |

### YAML 配置

所有提示词、开场消息、开场问题外化至 `agents/novel_prompts.yaml`，支持前端实时编辑。

---

## 漫剧 Agent 架构迭代

| 变更 | v5 | v6 |
|------|----|----|
| 状态模型 | 嵌套 dict | `AgentInfo` 统一枚举状态 |
| 配置注入 | `get_settings()` 全局 | 依赖注入 `cfg: SystemConfig` |
| 错误处理 | 各 agent 自行 try/catch | 统一 `AgentError` + 中间件 |
| 提示词管理 | 硬编码在 `models.py` | YAML 外化 |

---

## 任务清单

### 阶段 0 · 架构文档
- [x] README.md 架构设计文档

### 阶段 1 · 小说写作 Agent 后端
- [ ] `core/novel_models.py` — 小说专用数据模型
- [ ] `core/novel_store.py` — 会话持久化
- [ ] `agents/novel_prompts.yaml` — 提示词 + 开场配置
- [ ] `agents/novel_agent.py` — 主 Agent（状态机路由）
- [ ] `agents/worldview_builder.py` — 世界观子 Agent
- [ ] `agents/outline_planner.py` — 情节规划子 Agent
- [ ] `agents/chapter_writer.py` — 章节创作子 Agent
- [ ] `main.py` 新增 `/api/novel/*` 路由

### 阶段 2 · 漫剧 Agent 架构迭代
- [ ] `core/models.py` 统一 AgentInfo/状态枚举
- [ ] `agents/pipeline_agents.py` 依赖注入重构
- [ ] 提示词迁移至 YAML

### 阶段 3 · React 前端
- [ ] Vite 项目初始化 + 配置
- [ ] 全局 Layout + 导航
- [ ] 漫剧工作台页面
- [ ] 小说工作台页面（对话式 UI）
- [ ] Zustand store 接入
- [ ] WebSocket hook
- [ ] 配置面板

---

## 快速启动

```bash
# 后端
cd backend
pip install -r requirements.txt
cp .env.example .env  # 填入 API Key
uvicorn main:app --reload

# 前端
cd frontend
npm install
npm run dev
```

---

## 环境变量

```env
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
```
