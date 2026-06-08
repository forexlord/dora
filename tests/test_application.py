from core.application import DoraAssistant, run_assistant


def test_application_reexports() -> None:
    assert DoraAssistant is not None
    assert callable(run_assistant)
