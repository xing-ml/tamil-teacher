# Tamil Colloquial Teacher

泰米尔语口语教学系统 — 从 YouTube 字幕采集到课程生成的端到端流水线。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 运行完整流水线
python bin/tamil_daily_lesson.py

# 或分步运行
python collector/tamil_colloquial_collector.py --output-dir ./temp
python collector/tamil_cleaner.py --agent-input ./temp/tamil_agent_input.json --keywords-file ./data/tamil_keywords.json --output-dir ./temp
python collector/tamil_lesson_context_builder.py --cleaned-dialogues ./temp/tamil_cleaned_dialogues.json --scenarios-file ./data/scenario_definitions.json --difficulty-file ./data/difficulty_levels.json --cache-file ./data/cache/dialogue_cache.json --output-dir ./temp
python collector/tamil_corpus_manager.py --corpus-dir ./data/corpus --add-cleaned ./temp/tamil_cleaned_dialogues.json --generate-lessons
```

## 流水线架构

```
YouTube/网页采集 → 清洗过滤 → 课程上下文构建 → 语料库管理 + 课程生成
    (collector)       (cleaner)       (context_builder)    (corpus_manager)
```

## 文件职责总览

### 🔧 流水线核心（活跃）

| 文件 | 职责 |
|------|------|
| `bin/tamil_daily_lesson.py` | **流水线入口** — 依次运行 collector → cleaner → context_builder → corpus_manager |
| `collector/tamil_colloquial_collector.py` | **数据采集** — 通过 YouTube API + DDGS 搜索采集 Tamil 对话语料 |
| `collector/tamil_cleaner.py` | **清洗过滤** — 过滤低质量内容，提取句子，计算口语评分 |
| `collector/tamil_lesson_context_builder.py` | **课程上下文** — 从清洗后的对话中选取对话，构建课程上下文 JSON |
| `collector/tamil_corpus_manager.py` | **语料库管理** — 管理语料库，生成分级课程（Level 1-6） |
| `collector/url_deduplicator.py` | **URL 去重** — 维护已采集 URL 缓存，防止重复抓取（被 collector 使用） |

### 📊 数据文件

| 文件 | 职责 |
|------|------|
| `data/difficulty_levels.json` | 难度等级定义（L1-L6），被 context_builder 和 corpus_manager 使用 |
| `data/scenario_definitions.json` | 场景定义（社交、家庭、购物等），被 context_builder 使用 |
| `data/tamil_keywords.json` | Tamil 口语关键词库（核心词、俚语、语气词等），被 cleaner 使用 |
| `data/corpus/lessons_registry.json` | **输出** — 生成的课程注册表 |
| `data/corpus/tamil_corpus.json` | **输出** — 对话语料库 |
| `data/cache/dialogue_cache.json` | 对话缓存（去重用），被 context_builder 使用 |
| `data/intermediate/L*/utterances.json` | **输出** — 中间层语料（按难度分级） |

### 🧪 测试文件

| 文件 | 职责 | 流水线 |
|------|------|--------|
| `test_api_structure.py` | 测试 YouTube API 返回结构 | ❌ 无用 |
| `test_classification_pipeline.py` | 集成测试：classifier → context → LLM evaluator | ❌ 无用 |
| `test_search_queries.py` | 测试不同 YouTube 搜索策略 | ❌ 无用 |
| `test_tamil_movies.py` | 测试 Tamil 电影字幕抓取 | ❌ 无用 |
| `test_youtube_direct.py` | 直接测试 YouTube 字幕抓取 | ❌ 无用 |

### 🔬 未接入流水线的模块

| 文件 | 职责 | 状态 |
|------|------|------|
| `collector/tamil_linguistic_classifier.py` | 按难度等级对 Tamil 话语分类（功能已被 `tamil_corpus_manager._determine_difficulty()` 替代） | ❌ 无用 |
| `collector/tamil_context_extractor.py` | 提取分类话语的上下文窗口 | ❌ 无用（被 test_classification_pipeline.py 使用） |
| `collector/llm_evaluator.py` | 基于 LLM 的课程质量评估 | ❌ 无用（被 test_classification_pipeline.py 使用） |
| `bin/tamil_lesson_analyzer.py` | 完整分析流水线（classifier → context → LLM eval） | ❌ 无用 |

### 🎬 演示/工具

| 文件 | 职责 |
|------|------|
| `demo_v2.2.py` | 演示脚本 — 展示语料库及音译转换 |
| `check_system.py` | 系统完整性检查 — 验证所有组件就位 |

### 📁 配置文件

| 文件 | 职责 |
|------|------|
| `requirements.txt` | Python 依赖列表 |
| `ARCHITECTURE.md` | 架构文档 |
| `.gitignore` | Git 忽略规则 |

### 📁 临时文件（不提交到 git）

| 目录/文件 | 内容 |
|-----------|------|
| `temp/` | 流水线中间输出（原始语料、清洗结果、课程上下文） |
| `collector/__pycache__/` | Python 字节码缓存 |

## 输出文件

运行 `python bin/tamil_daily_lesson.py` 后生成：

- `temp/tamil_agent_input.json` — 采集的原始语料
- `temp/tamil_cleaned_dialogues.json` — 清洗后的对话（含口语评分）
- `temp/tamil_lesson_context.json` — 课程上下文（含选中的对话）
- `data/corpus/lessons_registry.json` — 生成的课程注册表
- `data/corpus/tamil_corpus.json` — 更新后的语料库
