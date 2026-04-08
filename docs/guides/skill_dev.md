# Skill 开发指南

Skill = 预定义的工作流，帮助 Agent 处理特定类型任务。

## Skill 格式

每个 Skill 是一个 `.md` 文件，位于 `skills/impl/` 目录。

```markdown
---
name: skill_name
description: 何时使用这个 Skill
compatibility: WriteFile ReadFile ...
---

# Skill 标题

## 工作流程

### 1. 步骤名称
具体做什么。

### 2. 步骤名称
做什么。
```

## 创建步骤

### 1. 创建文件

在 `skills/impl/` 创建 `my_skill.md`：

```markdown
---
name: my_skill
description: 当用户想要...时使用这个 Skill
compatibility: WriteFile ReadFile Bash
---

# My Skill

## 工作流程

### 1. 分析需求
理解用户想要什么。

### 2. 执行
使用工具完成任务。

### 3. 返回结果
告诉用户完成情况。
```

### 2. 配置兼容性

`compatibility` 字段声明这个 Skill 需要哪些工具：

| 工具名 | 作用 |
|--------|------|
| WriteFile | 写文件 |
| ReadFile | 读文件 |
| Bash | 执行命令 |
| ExecPython | 执行 Python |
| FetchUrl | 抓取网页 |
| WebSearch | 搜索 |
| Ls | 列表目录 |
| Glob | 模式搜索 |
| Grep | 内容搜索 |
| ReadImage | 读图 |

### 3. 调用 Skill

Agent 通过 `invoke_skill` 工具调用：

```
用户: "帮我创建一个 Web 项目"
Agent: 调用 invoke_skill("my_skill")
     → 返回完整的 Skill workflow
     → 按步骤执行任务
```

## 最佳实践

### 1. description 要具体

**好**：
```
description: 当用户想要创建一个完整的多文件 Python 项目时使用
```

**不好**：
```
description: 用于编程任务
```

### 2. workflow 要清晰

每个步骤说明：
- 要做什么
- 用什么工具
- 预期产出

### 3. 工具名称用 PascalCase

```yaml
compatibility: WriteFile ReadFile Bash  # ✅
compatibility: write_file read_file bash  # ❌
```

## 示例

参考现有 Skills：
- `skills/impl/code_project.md` - 代码生成
- `skills/impl/excel_analysis.md` - 数据分析
- `skills/impl/web_scraper.md` - 网页抓取
