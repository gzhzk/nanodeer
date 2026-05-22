---
name: code_project
description: Generate a complete multi-file Python project from requirements. Use when user asks to create/build a project, generate code files, or scaffold a Python application. Not for single-file scripts or inline code snippets.
disable-model-invocation: true
compatibility: WriteFile ReadFile Glob Grep Bash ExecPython
---

# Code Project Generator

生成完整、可运行的多文件 Python 项目。

## 工作流程

### 1. 分析需求
理解用户目标，确定项目类型：
- CLI 工具 / Web 服务 / 数据处理 / API 服务
- 确定核心模块和数据流

### 2. 设计结构
规划项目文件树和依赖关系：

```
项目名/
├── main.py              # 入口
├── module_a.py          # 核心模块
├── module_b.py          # 辅助模块
├── config.py            # 配置
├── requirements.txt     # 依赖
└── README.md            # 文档
```

### 3. 生成代码
按依赖顺序使用 WriteFile 创建文件。

### 4. 验证质量
- ExecPython 语法检查：`py_compile.compile(f, doraise=True)`
- Bash 运行测试：`python3 main.py`

### 5. 输出结果
提供运行指令和项目说明。

## 代码规范

- pathlib.Path 处理路径
- Type hints 标注函数签名
- Docstring 说明关键函数
- TOML/YAML 配置文件

## 项目结构模式

### CLI 工具
```
project/
├── main.py          # argparse / click 入口
├── commands.py     # 子命令
├── core.py         # 核心逻辑
├── utils.py        # 工具函数
└── requirements.txt
```

### Web 服务
```
project/
├── main.py         # FastAPI/Flask 入口
├── routes.py       # 路由定义
├── models.py       # 数据模型
├── services.py     # 业务逻辑
├── config.py       # 配置
└── requirements.txt
```

### 数据处理
```
project/
├── main.py         # 入口
├── parser.py       # 数据解析
├── processor.py    # 数据处理
├── analyzer.py     # 分析统计
├── reporter.py     # 报告生成
├── config.toml     # 配置
└── requirements.txt
```

## 代码模式

### 错误处理
```python
def safe_load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(f"Failed to load {path}: {e}")
        return None
```

### 配置加载
```python
from pathlib import Path
from tomllib import load as load_toml

def load_config(path: Path = Path("config.toml")) -> dict:
    return load_toml(path.read_bytes())
```
