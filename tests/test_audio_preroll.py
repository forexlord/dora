from core.listener.audio import AudioPreroll


def test_preroll_keeps_tail_only() -> None:
    preroll = AudioPreroll(16000, seconds=0.1)
    chunk = b"\x01\x00" * 800
    for _ in range(20):
        preroll.push(chunk)
    snap = preroll.snapshot()
    assert len(snap) <= int(16000 * 2 * 0.1) + 4
    assert len(snap) > 0
