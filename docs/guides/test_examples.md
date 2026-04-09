# 测试与示例

详细测试用例和示例列表，供开发者参考。

## 测试体系

### 单元测试 (tests/unit/)

| 测试 | 测试内容 |
|------|----------|
| test_01_agent_state | ThreadState, SandboxInfo 数据结构 |
| test_02_agent_prompt | System prompt 生成（工具/记忆/todos） |
| test_03_tools | 全部 18 个工具及其功能 |
| test_04_middleware_chain | MiddlewareChain 钩子执行顺序（正序/逆序） |
| test_05_memory_store | MemoryStore 文件存储 |
| test_06_plan | TodoItem, TodoStatus 任务追踪 |
| test_07_sandbox_path | 虚拟路径 ↔ 物理路径翻译与验证 |
| test_08_sandbox_real | 真实 Docker 沙箱（需要 Docker 环境） |
| test_09_router | Direct/ReAct/PlanExecute 模式检测 |

### 集成测试 (tests/integration/)

| 测试 | 测试内容 |
|------|----------|
| test_10_agent_builder | 使用工具构建 LangGraph agent |
| test_11_sandbox_mock | 沙箱工具包装器与 base64 编码 |
| test_12_middleware_integration | UploadsMiddleware 和 CompressionMiddleware |
| test_13_skills | SkillLoader 和 invoke_skill 工具 |

### Subagent 测试 (tests/unit/test_09_subagent.py)

| 测试 | 测试内容 |
|------|----------|
| test_subagent_id_generation | Subagent ID 生成 |
| test_subagent_run | 单个 Subagent 执行 |
| test_subagent_parallel | 多个 Subagent 并行执行 |

## 运行测试

```bash
# 单元测试（快速，无需 Docker）
pytest tests/unit/ -v

# 集成测试
pytest tests/integration/ -v

# 只需一个文件
pytest tests/unit/test_01_agent_state.py -v
```

## 示例

### 单元示例 (examples/unit/)

| 示例 | 说明 |
|------|------|
| 01_agent_state | ThreadState 和 SandboxInfo 数据结构 |
| 02_agent_prompt | System prompt 生成（工具/记忆/todos） |
| 03_tools | 全部 18 个工具及其用法 |
| 04_middleware_chain | 中间件钩子执行顺序（正序/逆序） |
| 05_memory_store | MemoryStore 文件存储 |
| 06_plan | TodoItem 和 TodoStatus 任务追踪 |
| 07_sandbox_path | 虚拟路径 ↔ 物理路径翻译与验证 |
| 08_router | Direct/ReAct/PlanExecute 模式检测 |
| 09_subagent | Subagent 并行执行系统 |

### 集成示例 (examples/integration/)

| 示例 | 说明 |
|------|------|
| 10_agent_builder | 使用工具构建 LangGraph agent |
| 11_sandbox_mock | 沙箱工具包装器和 base64 编码 |
| 12_middleware_integration | UploadsMiddleware 和 CompressionMiddleware |
| 13_skills | SkillLoader 和 invoke_skill 工具 |

## 运行示例

```bash
# 单元示例
python -m examples.unit.01_agent_state
python -m examples.unit.02_agent_prompt
python -m examples.unit.03_tools
# ...

# 集成示例
python -m examples.integration.10_agent_builder
python -m examples.integration.11_sandbox_mock
# ...
```
