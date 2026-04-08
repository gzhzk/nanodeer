"""Example 08: Router - Mode Detection.

Demonstrates:
- Router.detect() for message mode detection
- Three agent modes: DIRECT, REACT, PLAN_EXECUTE
- Rule-based detection using keywords
"""
from harness.agent.router import Router, AgentMode


def main():
    print("=" * 60)
    print("Example 08: Router - Mode Detection")
    print("=" * 60)

    router = Router()

    print("\nAgent Modes:")
    print("-" * 40)
    print(f"  DIRECT: {AgentMode.DIRECT.value} - Simple Q&A, no tools")
    print(f"  REACT: {AgentMode.REACT.value} - Standard tool loop")
    print(f"  PLAN_EXECUTE: {AgentMode.PLAN_EXECUTE.value} - Plan first, then execute")

    print("\n" + "=" * 60)
    print("Mode Detection Examples:")
    print("=" * 60)

    test_cases = [
        # DIRECT - simple questions
        ("什么是 Python？", AgentMode.DIRECT),
        ("为什么天是蓝的？", AgentMode.DIRECT),
        ("如何学习编程？", AgentMode.DIRECT),
        ("hello", AgentMode.DIRECT),
        ("你好", AgentMode.DIRECT),

        # PLAN_EXECUTE - multi-step tasks
        ("帮我做一个网页", AgentMode.PLAN_EXECUTE),
        ("开发一个网站", AgentMode.PLAN_EXECUTE),
        ("帮我分析这个项目", AgentMode.PLAN_EXECUTE),
        ("创建一个博客系统", AgentMode.PLAN_EXECUTE),

        # REACT - needs tools but not complex planning
        ("读取 /tmp/test.txt", AgentMode.REACT),
        ("执行 ls 命令", AgentMode.REACT),
        ("搜索一下 Docker 文档", AgentMode.REACT),
    ]

    for message, expected_mode in test_cases:
        detected = router.detect(message)
        status = "✓" if detected == expected_mode else "✗"
        print(f"  {status} \"{message}\"")
        print(f"      → {detected.value}")

    print("\n" + "=" * 60)
    print("Detection Rules:")
    print("=" * 60)
    print("""
  Keywords → PLAN_EXECUTE:
    帮我, 项目, 网站, 应用, 开发, 创建, 分析, 调研...

  Keywords → DIRECT:
    是什么, 为什么, 如何, 介绍, hello, 你好...

  Default → REACT
    (No keywords matched, needs tools)
""")


if __name__ == "__main__":
    main()
