---
name: web_scraper
description: Scrape articles from multiple websites and generate structured reports. Use when user asks to fetch web content, scrape news, gather articles, or create reports from URLs.
disable-model-invocation: true
compatibility: FetchUrl WebSearch ExecPython WriteFile
---

# Web Scraper & Report Generator

从多个网站抓取内容、去重、分类，生成结构化 Markdown 报告。

## 工作流程

### 1. 搜索目标源
使用 WebSearch 查找相关 URL。

### 2. 抓取内容
对每个 URL 使用 FetchUrl 获取正文。

### 3. 提取信息
使用 ExecPython 解析 HTML，提取标题、日期、摘要。

### 4. 去重分类
按标题相似度去重，按类别分组。

### 5. 生成报告
使用 WriteFile 输出 Markdown 报告。

## HTML 解析模式

### 提取标题
```python
title = soup.find("h1") or soup.find("meta", property="og:title")
title = title.get_text(strip=True) if title else soup.title.string
```

### 提取日期
```python
date = (
    soup.find("meta", attrs={"name": "date"}) or
    soup.find("time", datetime=True) or
    soup.find("span", class_="date")
)
date = date.get("content") or date.get("datetime") or date.get_text(strip=True)
```

### 提取正文
```python
article = soup.find("article") or soup.find("div", class_=re.compile("content|article|post"))
if article:
    text = article.get_text(separator="\n", strip=True)
    lines = [l for l in text.split("\n") if l.strip()]
    summary = "\n".join(lines[:50])  # 前 50 行
```

## 去重模式
```python
def deduplicate(items: list[dict], key: str = "title", threshold: int = 30) -> list[dict]:
    seen = set()
    result = []
    for item in items:
        k = item[key][:threshold].lower()
        if k not in seen:
            seen.add(k)
            result.append(item)
    return result
```

## 分类模式
```python
categories = {"技术": [], "产品": [], "行业": []}
for item in articles:
    t = item["title"].lower()
    if any(k in t for k in ["ai", "llm", "gpt", "model"]):
        categories["技术"].append(item)
    elif any(k in t for k in ["release", "launch", "update"]):
        categories["产品"].append(item)
    else:
        categories["行业"].append(item)
```

## 报告示例
```markdown
# AI 科技周报 - 2026 Week 14

## 技术进展
1. Claude 4.6 发布
   - 日期：2026-04-01
   - 摘要：Anthropic 发布新一代 Claude...

## 产品更新
1. GitHub Copilot X 正式版发布
   - 日期：2026-04-03
   - 摘要：集成 GPT-5 的代码补全...

## 行业动态
1. OpenAI 开放多模态 API
   - 日期：2026-04-05
```
