# Tamil Colloquial Teacher

泰米尔语口语教学系统 — 从 YouTube 字幕采集到课程生成的端到端流水线。

## 架构

```
YouTube/网页采集 → 清洗过滤 → 课程上下文构建 → 语料库管理 + 课程生成
    (collector)       (cleaner)       (context_builder)    (corpus_manager)
```

### 目录结构

```
tamil-teacher/
├── bin/
│   ├── tamil_daily_lesson.py          # 流水线入口（Python）
│   └── tamil_daily_lesson.sh          # 流水线入口（Shell）
├── collector/
│   ├── tamil_collector.py             # 数据采集（YouTube + DDGS）
│   ├── tamil_cleaner.py               # 清洗过滤 + 口语评分
│   ├── tamil_lesson_context_builder.py # 课程上下文构建
│   ├── tamil_corpus_manager.py        # 语料库管理 + 课程生成
│   └── url_deduplicator.py            # URL 去重
├── data/
│   ├── status/                        # 运行状态
│   │   └── dialogue_used.json         # 已用对话 hash（防重复）
│   ├── resources/                     # 资源管理
│   │   ├── valid/                     # 有效资源（有 Tamil 字幕、口语）
│   │   │   └── youtube_videos.json    # 已验证的 YouTube 视频
│   │   └── invalid/                   # 无效资源（标记后不再访问）
│   │       ├── no_tamil_subs.json     # 无 Tamil 字幕
│   │       ├── not_colloquial.json    # 非口语（新闻、演讲等）
│   │       ├── poor_quality.json      # 字幕质量差/断断续续
│   │       └── tanglish_unmatchable.json # 无法对应 Tanglish
│   ├── lessons/                       # 生成的课程（分级、分语境）
│   │   ├── L1_*.json
│   │   ├── L2_*.json
│   │   └── ...
│   ├── lessons_registry/              # 课程注册表
│   │   └── registry.json
│   ├── corpus/                        # 语料库
│   │   └── tamil_corpus.json          # 原始语料
│   └── definitions/                   # 程序配置定义
│       ├── difficulty_definitions.json
│       ├── scenario_definitions.json
│       └── tamil_keywords_definitions.json
├── .gitignore
├── requirements.txt
└── ARCHITECTURE.md
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 运行完整流水线
python bin/tamil_daily_lesson.py

# 或分步运行
python collector/tamil_collector.py --output-dir ./temp
python collector/tamil_cleaner.py --agent-input ./temp/tamil_agent_input.json --keywords-file ./data/definitions/tamil_keywords_definitions.json --output-dir ./temp
python collector/tamil_lesson_context_builder.py --cleaned-dialogues ./temp/tamil_cleaned_dialogues.json --scenarios-file ./data/definitions/scenario_definitions.json --difficulty-file ./data/definitions/difficulty_definitions.json --cache-file ./data/status/dialogue_used.json --output-dir ./temp
python collector/tamil_corpus_manager.py --corpus-dir ./data/corpus --add-cleaned ./temp/tamil_cleaned_dialogues.json --generate-lessons
```

## 文件职责

### 流水线核心

| 文件 | 职责 |
|------|------|
| `bin/tamil_daily_lesson.py` | **流水线入口** — 依次运行 collector → cleaner → context_builder → corpus_manager |
| `collector/tamil_collector.py` | **数据采集** — 通过 YouTube API + DDGS 搜索采集 Tamil 对话语料 |
| `collector/tamil_cleaner.py` | **清洗过滤** — 过滤低质量内容，提取句子，计算口语评分 |
| `collector/tamil_lesson_context_builder.py` | **课程上下文** — 从清洗后的对话中选取对话，构建课程上下文 JSON |
| `collector/tamil_corpus_manager.py` | **语料库管理** — 管理语料库，生成分级课程（Level 1-6） |
| `collector/url_deduplicator.py` | **URL 去重** — 维护已采集 URL 缓存，防止重复抓取 |

### 数据目录

| 目录/文件 | 职责 |
|-----------|------|
| `data/status/dialogue_used.json` | 已用对话 hash，防止课程重复使用相同对话 |
| `data/resources/valid/` | 有效资源（有 Tamil 字幕、符合口语要求） |
| `data/resources/invalid/` | 无效资源（标记后不再访问） |
| `data/lessons/` | 生成的课程（按难度分级：L1-L6） |
| `data/lessons_registry/registry.json` | 课程注册表（索引/元数据） |
| `data/corpus/tamil_corpus.json` | 原始语料库 |
| `data/definitions/difficulty_definitions.json` | 难度等级定义（L1-L6） |
| `data/definitions/scenario_definitions.json` | 场景定义（社交、家庭、购物等） |
| `data/definitions/tamil_keywords_definitions.json` | Tamil 口语关键词库 |

### 配置文件

| 文件 | 职责 |
|------|------|
| `requirements.txt` | Python 依赖列表 |
| `ARCHITECTURE.md` | 架构文档 |
| `.gitignore` | Git 忽略规则 |

### 临时文件（不提交到 git）

| 目录/文件 | 内容 |
|-----------|------|
| `temp/` | 流水线中间输出（原始语料、清洗结果、课程上下文） |
| `collector/__pycache__/` | Python 字节码缓存 |

## 输出文件

运行 `python bin/tamil_daily_lesson.py` 后生成：

- `temp/tamil_agent_input.json` — 采集的原始语料
- `temp/tamil_cleaned_dialogues.json` — 清洗后的对话（含口语评分）
- `temp/tamil_lesson_context.json` — 课程上下文（含选中的对话）
- `data/lessons/` — 生成的课程（按难度分级）
- `data/lessons_registry/registry.json` — 课程注册表
- `data/status/dialogue_used.json` — 更新已用对话 hash
