from core.intent.arithmetic import try_spoken_arithmetic


def test_numeric_multiply() -> None:
    result = try_spoken_arithmetic("what is 10 times 5")
    assert result is not None
    assert "50" in result


def test_numeric_plus() -> None:
    result = try_spoken_arithmetic("what is 2 plus 3")
    assert result is not None
    assert "5" in result
