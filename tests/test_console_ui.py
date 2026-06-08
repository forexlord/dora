from core import console_ui


def test_console_ui_emit_helpers_do_not_raise() -> None:
    console_ui.emit("hello", style="green")
    console_ui.emit_dim("dim")
    console_ui.emit_listen_prompt()
    console_ui.emit_thinking()
    console_ui.emit_reply("reply")
    console_ui.emit_result("done", style="green")
