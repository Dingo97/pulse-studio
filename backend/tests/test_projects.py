from app.projects import safe_name


def test_safe_name() -> None:
    assert safe_name("  My: Song?  ") == "My Song"
