# 教程 6：Skills 系统

## 1. 生活中的类比

**没有 Skill**：像请了一个**通用厨师**
- 厨师会做很多菜，但不确定什么时候用什么火候
- 每道菜都要你详细指挥

**有 Skill**：像请了一个**川菜师傅**
- 他知道川菜的标准流程（爆炒、回锅、麻辣）
- 你说"做道川菜"，他自动按套路来

**NanoDeer 的 Skill**：把常用工作流固化下来，Agent 收到特定请求时自动套用。

---

## 2. 什么是 Skill？

当用户说"帮我分析这个 Excel"，Agent 需要知道：
1. 用什么工具（ReadFile, ExecPython, WriteFile）
2. 分析步骤是什么（读取 → 处理 → 生成图表 → 保存）
3. 有没有现成的模式可以参考

**Skill 就是把这种"套路"固化下来。**

---

## 3. Skill 格式

```markdown
---
name: skill_name
description: 何时使用这个 Skill
compatibility: WriteFile ReadFile ExecPython
---

# Skill 标题

## 工作流程

### 1. 步骤名称
具体做什么。

### 2. 步骤名称
做什么。
```

---

## 4. 内置 Skills

| Skill | 用途 | 所需工具 |
|-------|------|----------|
| code_project | 生成多文件 Python 项目 | WriteFile, ReadFile, Glob, Grep, Bash, ExecPython |
| excel_analysis | 分析 Excel 生成图表 | ReadFile, ExecPython, WriteFile, Ls |
| web_scraper | 抓取网页生成报告 | FetchUrl, WebSearch, ExecPython, WriteFile |

---

## 5. 代码演示

### 5.1 调用 Skill

Agent 通过 `invoke_skill` 工具调用：

```python
# 工具定义
from harness.tools import invoke_skill

# Agent 收到请求："帮我创建一个 Web 项目"
# Agent 调用 invoke_skill("code_project")
# → 返回完整的 Skill workflow
# → 按步骤执行任务
```

### 5.2 加载 Skill

```python
from harness.skills.loader import SkillLoader

loader = SkillLoader("src/harness/skills")
skill = loader.get("code_project")
print(skill.name)        # "code_project"
print(skill.description) # "生成完整的多文件 Python 项目"
print(skill.tools)       # ["WriteFile", "ReadFile", "Glob", "Grep", "Bash", "ExecPython"]
```

### 5.3 Skill 返回的内容

```python
skill = loader.get("excel_analysis")
print(skill.content)
# 输出：
# # Excel Analysis Skill
#
# ## 工作流程
#
# ### 1. 读取文件
# 使用 ReadFile 读取 Excel 文件...
```

---

## 6. 创建新 Skill

### 6.1 创建文件

在 `src/harness/skills/impl/` 创建 `my-project.md`：

```markdown
---
name: my-project
description: 当用户想要...时使用
compatibility: WriteFile ReadFile Bash
---

# My Project Skill

## 工作流程

### 1. 分析需求
理解用户目标，确定项目类型。

### 2. 创建结构
使用 WriteFile 创建必要的文件。

### 3. 实现功能
按依赖顺序实现各个模块。

### 4. 测试验证
使用 Bash 运行测试，确保代码正确。
```

### 6.2 自动加载

Skill 会被 `SkillLoader` 自动发现，无需额外注册。

---

## 7. Skill 与 Tool 的区别

| | Tool | Skill |
|---|---|---|
| **粒度** | 单个操作 | 完整工作流 |
| **调用方式** | Agent 主动调用 | Agent 收到特定请求时触发 |
| **内容** | 做什么 | 怎么做 |
| **例子** | ReadFile 读取文件 | excel_analysis 分析数据的工作流 |

---

## 8. 常见问题

**Q: Skill 和 Tool 什么时候用？**
A: Tool 做单点操作，Skill 处理复杂套路。当用户说"做某件事的流程"时用 Skill。

**Q: Skill 内容很长会塞满 Context 吗？**
A: 不会。Skill 是按需调用的，不是全部注入。只有 Agent 明确调用时才加载对应 Skill。

**Q: 可以让 Skill 调用另一个 Skill 吗？**
A: 可以，但建议保持简单，Skill 之间解耦更易维护。

**Q: Skill 保存在哪？**
A: `src/harness/skills/impl/*.md`，每个 Skill 一个文件。
