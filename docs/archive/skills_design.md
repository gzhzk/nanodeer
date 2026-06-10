# Skills 设计

Skills 系统为 Agent 提供渐进式能力披露，通过 Markdown 文件定义复杂工作流，使 Agent 在需要时能加载特定技能指南。

---

## 目录

- [架构](#架构)
- [Skill 数据结构](#skill-数据结构)
- [Frontmatter Schema](#frontmatter-schema)
- [SkillLoader](#skillloader)
- [invoke_skill 工具](#invoke_skill-工具)
- [内置 Skills](#内置-skills)
- [使用场景](#使用场景)

---

## 架构

```
packages/harness/nanodeer/skills/
├── __init__.py       # 导出：SkillLoader, load_all_skills
├── loader.py         # SkillLoader 类 + parse_frontmatter
└── impl/             # Skill 定义文件
    ├── excel_analysis.md
    ├── web_scraper.md
    └── code_project.md

packages/harness/nanodeer/tools/
└── invoke_skill.py    # invoke_skill tool（按工具组织放在此处）
```

---

## Skill 数据结构

```python
@dataclass
class Skill:
    name: str                    # 唯一标识（如 "excel_analysis"）
    description: str             # 人类可读描述
    tools: list[str]             # 所需工具列表
    prompt: str                  # 系统提示内容（Markdown body）
    file_path: str               # 来源文件路径
```

---

## Frontmatter Schema

Skill 文件使用 Markdown frontmatter：

```markdown
---
name: excel_analysis
description: Analyze Excel files with pandas, generate charts and statistics.
disable-model-invocation: true
compatibility: ReadFile ExecPython WriteFile Ls
---

# Skill Title

System prompt content...
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | **必需**。Skill 唯一标识。 |
| `description` | string | **必需**。何时使用此技能的描述。 |
| `compatibility` | list | 可选。所需工具列表（空格分隔）。 |
| `allowed-tools` | list | 可选。`compatibility` 的别名。 |
| `disable-model-invocation` | bool | 可选。是否禁用模型直接调用。 |

**兼容性格式**（两种等效）：
```yaml
compatibility: ReadFile ExecPython WriteFile Ls
# 或
compatibility: [ReadFile, ExecPython, WriteFile, Ls]
```

---

## SkillLoader

```python
class SkillLoader:
    def __init__(self, skills_dir: str | Path):
        # 默认使用 impl/ 子目录
        self.skills_dir = Path(skills_dir) / "impl"

    def load(self, skill_path: Path) -> Skill | None:
        """加载单个 skill 文件。"""

    def load_all(self) -> list[Skill]:
        """加载所有 skill。"""

    def get(self, name: str) -> Skill | None:
        """按名称加载 skill（无需 .md 后缀）。"""
```

### 解析 Frontmatter

```python
def parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 frontmatter 和 body。"""
    # 输入:
    #   "---\nname: x\n---\nBody"
    # 输出:
    #   ({"name": "x"}, "Body")
```

---

## invoke_skill 工具

```python
@tool
def invoke_skill(skill_name: str) -> str:
    """Invoke a named skill and get its full instructions."""
```

**可用技能**：

| 技能名 | 描述 | 所需工具 |
|--------|------|---------|
| `excel_analysis` | Excel 数据分析，生成图表 | ReadFile, ExecPython, WriteFile, Ls |
| `web_scraper` | 网页抓取，生成结构化报告 | 待定义 |
| `code_project` | 多文件 Python 项目生成 | 待定义 |

**返回格式**：

```
# Skill: excel_analysis
## Description: Analyze Excel files with pandas, generate charts and statistics.
## Required Tools: ReadFile, ExecPython, WriteFile, Ls

# Excel Data Analysis

用 pandas 读取 Excel、用 matplotlib 生成图表，输出分析报告。

...
```

**未找到时**：

```
Skill 'xxx' not found. Available skills: excel_analysis, web_scraper, code_project
```

---

## 内置 Skills

### excel_analysis

用于数据分析场景：
- 读取 Excel 文件（`pd.read_excel`）
- 基本统计（`df.describe()`）
- 分组聚合（`df.groupby()`）
- 生成图表（matplotlib：柱状图、饼图、折线图）
- 输出到 `/mnt/user-data/outputs/`

---

## 使用场景

### Agent 调用

```
Agent: "分析一下这份销售数据"
    ↓
invoke_skill("excel_analysis")
    ↓
返回完整技能指南
    ↓
Agent 按照指南调用 ReadFile → ExecPython → WriteFile
```

### 动态加载

Skills 不在启动时全部加载到 system prompt，而是在 Agent 需要时通过 `invoke_skill` 工具按需加载。

```
启动时 prompt：
  - Agent 基本能力
  - 通用工具定义
  - invoke_skill 工具描述

需要时加载：
  invoke_skill("excel_analysis") → 技能指南注入到对话
```

---

## 与其他模块的关系

```
skills ──→ SkillLoader → Skill
    │
    └──→ invoke_skill tool ──→ Agent conversation

skills 模块独立，不依赖 agent/plan/memory
（仅依赖 pathlib）
```
