# Tamil Colloquial Teaching System - Architecture v2.0

## 🎯 核心目标
从真实Tamil语料库自动生成多难度、多语气的口语课程。

## 🔄 数据流

```
COLLECTION → CLEANING → CORPUS → LESSONS → HERMES → OUTPUT
   (采集)      (清洗)     (库)    (注册表)  (润色)   (输出)
```

### 1️⃣ 采集阶段 (Collector)
**目标**: 采集Tamil口语语料

```bash
python collector/tamil_collector.py \
  --output-dir temp \
  --reddit-max-posts 15 \
  --ddgs-queries "tamil slang" "அன்றாட தமிழ்" \
  --youtube-queries "tamil full movie" \
  --youtube-max-per-query 5
```

**采集优先级**:
1. **YouTube** (长视频transcript - 高质量对话)
2. **DDGS** (Tamil字符搜索)
3. **Reddit** (社区对话)

**去重机制**: 
- URL规范化 + SHA1 hash
- 本地缓存: `data/cache/collected_urls.json`
- 自动跳过重复

**语言过滤**:
- 仅保存 `language="ta"` 的sources

---

### 2️⃣ 清洗阶段 (Cleaner)
**目标**: 提取对话对/短语并评分

```bash
python collector/tamil_cleaner.py \
  --agent-input temp/tamil_agent_input.json \
  --keywords-file data/tamil_keywords.json \
  --output-dir temp \
  --min-colloquial-score 0.3
```

**输出**: `tamil_cleaned_dialogues.json`
- 每条: `{text, source_type, colloquial_score, language, detected_keywords, ...}`
- 按难度分级: 1a, 1b, 2a, 2b, 3a, 3b

---

### 3️⃣ 语料库管理 (Corpus Manager)
**目标**: 存储到本地语料库 + 生成Lesson

```bash
python collector/tamil_corpus_manager.py \
  --corpus-dir data/corpus \
  --add-cleaned temp/tamil_cleaned_dialogues.json \
  --generate-lessons
```

**输出**:
- `data/corpus/tamil_corpus.json` - 所有条目 (5个)
- `data/corpus/lessons_registry.json` - Lesson索引

**难度自动分级**:
```
Score ≥ 0.6 & words ≤ 8   → 1a (初级简单)
Score ≥ 0.5 & words ≤ 12  → 1b (初级中等)
Score ≥ 0.4 & words ≤ 18  → 2a (中级简单)
Score ≥ 0.3 & words ≤ 25  → 2b (中级高等)
...
```

---

### 4️⃣ Hermes查询 API
从Lesson库中抽取符合条件的课程

```bash
# 获取2b级别的句子课程
python collector/tamil_corpus_manager.py \
  --corpus-dir data/corpus \
  --get-lesson "2b_sentence"
```

**输出格式** (JSON):
```json
{
  "lesson_id": "2b_sentence_20260504_011036_0",
  "title": "Tamil Colloquial 2B Sentence Lesson",
  "difficulty_level": "2b",
  "entries": [
    {
      "text": "Tamil text here",
      "tanglish_text": "Tamil as Tanglish",
      "colloquial_score": 0.31,
      "source_type": "reddit",
      "word_count": 5
    },
    ...
  ],
  "metadata": {
    "entry_count": 5,
    "avg_score": 0.31,
    "source_types": ["reddit"]
  }
}
```

---

### 5️⃣ 完整流程 (Daily Pipeline)
```bash
cd tamil-teacher
python bin/tamil_daily_lesson.py
```

**完成的步骤**:
1. ✅ 采集 50+ sources (Reddit + DDGS)
2. ✅ 清洗 → 5个高质量Tamil短语
3. ✅ 生成 → 1个Lesson (2b_sentence)
4. ✅ 存储 → 本地语料库 (可扩展)

---

## 📊 当前数据

### Corpus 统计
- **总条目**: 5
- **难度分布**: 全部 2b (中级)
- **类型**: 100% 句子 (sentence)
- **平均评分**: 0.31
- **语言**: 100% Tamil

### 样本条目
```
1. ": நிலா அது வானத்து மேலே" (5词)
2. "But நாம சொன்னா யாரு கேக்கப்போறா" (5词)
3. "அன்பழகன், அறிவழகன்: Love the meanings, thank you" (7词)
4. "அப்புறம் உள்ளார வச்சு வேப்பிலையைக்..." (8词)
5. ": இத trailer ல போட்டுதான்..." (16词)
```

---

## 🚀 下一步

### 立即可做
1. **扩大采集**: YouTube "tamil full movie" 应该有很多长transcript
2. **多轮迭代**: 每天运行pipeline自动加入新语料
3. **Hermes集成**: 从Corpus API读取lesson并润色

### 缺失 (可选)
1. Tanglish转换 (目前是占位符,待实现proper transliteration)
2. Reddit对话对提取 (目前只有单句)
3. 语义去重 (目前只有URL去重)

---

## 🛠️ 关键文件

| 文件 | 作用 |
|------|------|
| `collector/tamil_collector.py` | 采集sources |
| `collector/url_deduplicator.py` | URL缓存+去重 |
| `collector/tamil_cleaner.py` | 清洗+评分 |
| `collector/tamil_corpus_manager.py` | **新:语料库+Lesson** |
| `data/corpus/` | 本地语料库 |
| `data/cache/collected_urls.json` | URL去重缓存 |
| `bin/tamil_daily_lesson.py` | 入口脚本 |

---

## 💡 架构优势

✅ **本地化**: 所有数据本地存储,无云依赖
✅ **可重用**: 语料库积累,质量越来越高
✅ **自动化**: 一键运行,自动分级+去重
✅ **模块化**: 采集/清洗/存储/查询分离
✅ **可扩展**: 支持任意数量sources和难度级别
✅ **Hermes友好**: 标准JSON API

---

**最后修改**: 2026-05-04
**系统版本**: v2.0 (本地语料库 + Lesson Registry)
