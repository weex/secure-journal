from journal_app.password import assess


def test_rejects_short_common_and_repeated_passwords():
    short = assess("Ab1!")
    assert not short["accepted"]
    assert any("14" in reason for reason in short["reasons"])

    common = assess("12345678901234")
    assert not common["accepted"]
    assert any("common" in reason for reason in common["reasons"])

    repeated = assess("abcabcabcabcabc")
    assert not repeated["accepted"]


def test_accepts_a_long_mixed_password():
    result = assess("Correct-Horse-Battery")
    assert result["accepted"]
    assert result["classes"] >= 3
