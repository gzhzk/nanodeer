"""Router - mode selection for agent execution.

Modes:
- Direct: Simple questions answered without tools
- ReAct: Standard tool loop (Reasoning + Action)
- PlanExecute: Plan first, then execute
"""
from enum import Enum


class AgentMode(Enum):
    """Agent execution modes."""
    DIRECT = "direct"        # No tools, direct answer
    REACT = "react"          # Standard ReAct loop
    PLAN_EXECUTE = "plan"    # Plan first, then execute


class Router:
    """Simple rule-based router for mode selection."""

    # Keywords indicating multi-step/complex tasks → PlanExecute
    PLAN_KEYWORDS = [
        "帮我", "帮我做", "帮我完成", "做一个", "做一下",
        "项目", "网站", "应用", "系统", "app",
        "实现", "开发", "构建", "创建",
        "分析", "调研", "研究", "调查",
        "比较", "对比", "评估",
        "设计", "规划", "安排",
    ]

    # Keywords indicating simple direct answer → Direct
    DIRECT_KEYWORDS = [
        "是什么", "什么是", "为什么", "怎么", "如何",
        "介绍一下", "解释一下", "说明一下",
        "hello", "hi", "你好", "您好",
        "讲讲", "说说", "聊聊",
    ]

    def detect(self, message: str) -> AgentMode:
        """Detect mode from user message using simple rules.

        Args:
            message: The user's message content.

        Returns:
            Detected AgentMode.
        """
        content = message.lower().strip()

        # Check for plan keywords
        if self._has_keywords(content, self.PLAN_KEYWORDS):
            return AgentMode.PLAN_EXECUTE

        # Check for direct answer keywords
        if self._has_keywords(content, self.DIRECT_KEYWORDS):
            return AgentMode.DIRECT

        # Default to ReAct
        return AgentMode.REACT

    def _has_keywords(self, content: str, keywords: list[str]) -> bool:
        """Check if content contains any of the keywords."""
        return any(kw in content for kw in keywords)


# Singleton instance
router = Router()


def detect_mode(message: str) -> AgentMode:
    """Convenience function for mode detection."""
    return router.detect(message)
