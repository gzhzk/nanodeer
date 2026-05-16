"""
NanoDeer — minimal Gradio chat interface for ReAct agent debugging.
"""

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

_kernel = Path(__file__).resolve().parent.parent / "packages" / "nanodeer-kernel" / "src"
sys.path.insert(0, str(_kernel))

import gradio as gr
from nanodeer.config import get_config
from nanodeer.engine import NanoEngine

_MAX_RESULT_LEN = 1500
_TITLE_MAX = 36
_CONVOS_DIR = Path.home() / ".nanodeer" / "conversations"
_MAX_CONVOS = 50


def _ensure_conversations_dir():
    _CONVOS_DIR.mkdir(parents=True, exist_ok=True)


def _load_conversations() -> list[dict]:
    """Load all saved conversations from disk, newest first."""
    _ensure_conversations_dir()
    files = sorted(_CONVOS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    convos = []
    for f in files:
        if f.suffix == ".json":
            try:
                with open(f) as fp:
                    convos.append(json.load(fp))
            except (json.JSONDecodeError, OSError):
                pass
        if len(convos) >= _MAX_CONVOS:
            break
    return convos


def _save_conversation(convo: dict) -> None:
    """Save a conversation to disk and rotate old files."""
    _ensure_conversations_dir()
    # Rotate: keep only the newest _MAX_CONVOS - 1 files to make room
    files = sorted(_CONVOS_DIR.iterdir(), key=lambda p: p.stat().st_mtime)
    while len(files) >= _MAX_CONVOS:
        files[0].unlink(missing_ok=True)
        files = files[1:]
    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.json"
    with open(_CONVOS_DIR / filename, "w") as fp:
        json.dump(convo, fp, ensure_ascii=False, indent=2)


def fmt_args(args: dict) -> str:
    return json.dumps(args, indent=2, ensure_ascii=False) if args else "{}"


def tool_call_md(name: str, args: dict) -> str:
    return f"\n\n**🔧 {name}**\n```json\n{fmt_args(args)}\n```\n"


def tool_result_md(name: str, result: str, success: bool) -> str:
    icon = "✅" if success else "❌"
    return f"{icon} **{name}** — result:\n```\n{str(result)[:_MAX_RESULT_LEN]}\n```\n"


def _conversation_title(messages: list) -> str:
    """Derive a title from the first user message."""
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "user":
            text = msg.get("content", "") or ""
            return (text[:_TITLE_MAX] + "…") if len(text) > _TITLE_MAX else (text or "Chat")
    return "Chat"


async def respond(message: str, history: list, convos: list):
    history = history or []
    engine = NanoEngine(get_config())

    metrics = {"turns": 0, "tool_calls": 0, "duration_ms": 0, "status": "running"}
    raw_log = []

    history.append({"role": "user", "content": message})
    yield history, {**metrics}, "", convos

    content = ""
    in_turn = False

    async for event in engine.run_streaming(prompt=message):
        ev = event.get("event")
        if ev == "turn_start":
            metrics["turns"] += 1
            if in_turn:
                content += "\n\n---\n"
            in_turn = True
            raw_log.append(f"[turn {metrics['turns']}]")
        elif ev == "llm_token":
            t = event.get("text", "")
            if t:
                content += t
        elif ev == "assistant_response":
            pass
        elif ev == "tool_call":
            metrics["tool_calls"] += 1
            content += tool_call_md(event.get("name", "?"), event.get("args", {}))
            raw_log.append(f"[tool] {event.get('name','?')}")
        elif ev == "tool_result":
            name = event.get("name", "?")
            suc = event.get("success", True)
            content += tool_result_md(name, event.get("result", ""), suc)
            raw_log.append(f"[result] {name} {'✓' if suc else '✗'}")
        elif ev == "end":
            metrics["duration_ms"] = event.get("durationMs", 0)
            metrics["status"] = "done"
            in_turn = False
            raw_log.append(f"[end] {metrics['duration_ms']}ms")
        elif ev == "error":
            content += f"\n\n❌ **Error:** {event.get('message','?')}"
            metrics["status"] = "error"
        elif ev == "wait":
            content += f"\n\n⏸️ {event.get('question','')}"
            metrics["status"] = "waiting"

        if content:
            if history and history[-1].get("role") == "assistant":
                history[-1]["content"] = content
            else:
                history.append({"role": "assistant", "content": content})
        yield history, metrics, "\n".join(raw_log[-30:]), convos

    yield history, metrics, "\n".join(raw_log[-30:]), convos


def new_chat(chat_msg, metrics_data, log_text, convos):
    """Save current conversation to disk + state, then reset UI."""
    convos = list(convos or [])
    if chat_msg and len(chat_msg) > 0:
        convo = {
            "title": _conversation_title(chat_msg),
            "time": datetime.now().strftime("%H:%M"),
            "messages": list(chat_msg),
            "metrics": dict(metrics_data) if metrics_data else {},
            "log": log_text or "",
        }
        _save_conversation(convo)
        convos.append(convo)
    choices = [f"{c['time']}  {c['title']}" for c in convos]
    return (
        [],
        {"turns": 0, "tool_calls": 0, "duration_ms": 0, "status": "ready"},
        "",
        convos,
        gr.update(choices=choices),
    )


def load_convo(selected, convos):
    """Load a conversation from history."""
    if not selected or not convos:
        return [], {"turns": 0, "tool_calls": 0, "duration_ms": 0, "status": "ready"}, "", convos
    label = selected
    for c in convos:
        if f"{c['time']}  {c['title']}" == label:
            return c.get("messages", []), c.get("metrics", {}), c.get("log", ""), convos
    return [], {"turns": 0, "tool_calls": 0, "duration_ms": 0, "status": "ready"}, "", convos


with gr.Blocks(title="NanoDeer") as demo:
    saved = _load_conversations()
    store = gr.State(saved)  # [{title, time, messages, metrics, log}]
    model = f"{get_config().agents.defaults.provider}/{get_config().agents.defaults.model}"

    gr.Markdown(f"# 🚀 NanoDeer — A 6-Layer AI Agent Harness Built from Scratch")

    with gr.Row():
        with gr.Column(scale=1):
            new_btn = gr.Button("+ New Chat")
            gr.Markdown("**History**")
            initial_choices = [f"{c['time']}  {c['title']}" for c in saved]
            history_dd = gr.Dropdown(choices=initial_choices, label="", interactive=True)

        with gr.Column(scale=4):
            chat = gr.Chatbot(label=model)
            with gr.Accordion("Debug", open=False):
                with gr.Tabs():
                    with gr.Tab("Log"):
                        log = gr.Textbox(label="", lines=6, max_lines=12)
                    with gr.Tab("Metrics"):
                        met = gr.JSON(value={"turns": 0, "tool_calls": 0, "duration_ms": 0})
                    with gr.Tab("System"):
                        gr.Markdown(f"**Model:** {model}  \n**Python:** {sys.version.split()[0]}")
            with gr.Row():
                inp = gr.Textbox(placeholder="Message NanoDeer...", container=False, scale=4)
                send = gr.Button("Send", variant="primary")

    outs = [chat, met, log, store]
    send.click(respond, [inp, chat, store], outs)
    inp.submit(respond, [inp, chat, store], outs)
    new_btn.click(new_chat, [chat, met, log, store], [chat, met, log, store, history_dd])
    history_dd.change(load_convo, [history_dd, store], [chat, met, log, store])

demo.launch(server_name="127.0.0.1", server_port=20264, show_error=True)
