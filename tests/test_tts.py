from unittest.mock import MagicMock, patch

from core.tts import TextToSpeech


@patch("core.win_com.SapiSpeechSynthesizer")
def test_tts_speak_when_enabled(mock_sapi_cls: MagicMock) -> None:
    synth = MagicMock()
    mock_sapi_cls.return_value = synth
    tts = TextToSpeech(enabled=True, rate=1, volume=80, preferred_voice="zira")
    tts.speak("hello")
    synth.speak.assert_called_once_with("hello")


@patch("core.win_com.SapiSpeechSynthesizer")
def test_tts_skips_when_disabled(mock_sapi_cls: MagicMock) -> None:
    tts = TextToSpeech(enabled=False)
    tts.speak("hello")
    mock_sapi_cls.assert_not_called()


@patch("core.win_com.SapiSpeechSynthesizer")
def test_tts_stop(mock_sapi_cls: MagicMock) -> None:
    synth = MagicMock()
    mock_sapi_cls.return_value = synth
    tts = TextToSpeech(enabled=True)
    tts.speak("hi")
    tts.stop()
    synth.stop.assert_called_once()


@patch("core.tts.sys.platform", "linux")
def test_tts_non_windows_skips() -> None:
    tts = TextToSpeech(enabled=True)
    tts.speak("hello")


@patch("core.win_com.SapiSpeechSynthesizer")
def test_tts_speak_async_starts_thread(mock_sapi_cls: MagicMock) -> None:
    synth = MagicMock()
    mock_sapi_cls.return_value = synth
    tts = TextToSpeech(enabled=True)
    thread = tts.speak_async("async hello")
    thread.join(timeout=2.0)
    synth.speak.assert_called_once_with("async hello")
