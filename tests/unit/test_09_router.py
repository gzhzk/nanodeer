"""Unit tests for Router - mode detection."""
import pytest
from harness.agent.router import Router, AgentMode, detect_mode


class TestRouter:
    """Test Router mode detection."""

    @pytest.mark.parametrize("message,expected", [
        # Direct keywords - simple questions
        ("什么是 Python？", AgentMode.DIRECT),
        ("为什么天是蓝的？", AgentMode.DIRECT),
        ("如何学习编程？", AgentMode.DIRECT),
        ("介绍一下 Docker", AgentMode.DIRECT),
        ("hello", AgentMode.DIRECT),
        ("你好", AgentMode.DIRECT),
        ("hi", AgentMode.DIRECT),
        ("Hello, how are you?", AgentMode.DIRECT),
        ("这是什么？", AgentMode.DIRECT),

        # Plan keywords - multi-step tasks
        ("帮我做一个网页", AgentMode.PLAN_EXECUTE),
        ("帮我分析这个项目", AgentMode.PLAN_EXECUTE),
        ("开发一个网站", AgentMode.PLAN_EXECUTE),
        ("创建一个博客系统", AgentMode.PLAN_EXECUTE),
        ("调研一下竞品", AgentMode.PLAN_EXECUTE),
        ("比较一下这两个框架", AgentMode.PLAN_EXECUTE),
        ("帮我开发一个 APP", AgentMode.PLAN_EXECUTE),
        ("实现一个用户系统", AgentMode.PLAN_EXECUTE),
        ("设计一个数据库架构", AgentMode.PLAN_EXECUTE),

        # ReAct - needs tools but not complex planning
        ("读取 /tmp/test.txt", AgentMode.REACT),
        ("执行 ls 命令", AgentMode.REACT),
        ("帮我看看这个文件", AgentMode.PLAN_EXECUTE),  # "帮我" triggers plan
        ("搜索一下 Docker 文档", AgentMode.REACT),
        ("查看当前目录", AgentMode.REACT),
    ])
    def test_detect_mode(self, message, expected):
        """Test mode detection for various messages."""
        router = Router()
        result = router.detect(message)
        assert result == expected, f"Expected {expected} for '{message}', got {result}"


class TestDetectModeFunction:
    """Test convenience function."""

    def test_direct_simple_question(self):
        """Simple question triggers Direct mode."""
        assert detect_mode("什么是 API？") == AgentMode.DIRECT

    def test_plan_multi_step(self):
        """Multi-step task triggers PlanExecute mode."""
        assert detect_mode("帮我做一个博客") == AgentMode.PLAN_EXECUTE
        assert detect_mode("开发一个网站需要什么？") == AgentMode.PLAN_EXECUTE

    def test_react_needs_tools(self):
        """No keywords triggers ReAct mode (default)."""
        assert detect_mode("读取 /tmp/test.txt") == AgentMode.REACT
        assert detect_mode("执行命令") == AgentMode.REACT

    def test_mixed_case(self):
        """Handles mixed case input."""
        assert detect_mode("HELLO") == AgentMode.DIRECT
        assert detect_mode("帮我做一个网页") == AgentMode.PLAN_EXECUTE


class TestAgentModeEnum:
    """Test AgentMode enum values."""

    def test_mode_values(self):
        """Mode values are correct strings."""
        assert AgentMode.DIRECT.value == "direct"
        assert AgentMode.REACT.value == "react"
        assert AgentMode.PLAN_EXECUTE.value == "plan"

    def test_mode_count(self):
        """Has exactly 3 modes."""
        assert len(AgentMode) == 3


class TestRouterKeywords:
    """Test router keyword lists."""

    def test_has_direct_keywords(self):
        """Router has DIRECT keywords."""
        router = Router()
        assert len(router.DIRECT_KEYWORDS) > 0

    def test_has_plan_keywords(self):
        """Router has PLAN keywords."""
        router = Router()
        assert len(router.PLAN_KEYWORDS) > 0

    def test_keyword_matching_case_insensitive(self):
        """Keyword matching is case insensitive."""
        router = Router()
        # Chinese keywords are typically not case-sensitive
        assert router._has_keywords("你好", ["你好"])
        assert router._has_keywords("帮我", ["帮我"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
