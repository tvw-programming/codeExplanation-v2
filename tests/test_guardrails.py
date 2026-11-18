from src.security.guardrails import redact_secrets


def test_bare_credentials_in_prose_are_redacted_not_just_assignments():
    """Doc comments are read aloud in the narration now, so a key
    mentioned in prose would be spoken as well as written. The
    assignment-shaped patterns alone never matched these."""
    # Built piece by piece rather than written out: a literal
    # credential-shaped string here, even a fake one, trips GitHub's
    # push protection and would block the repository's own pushes.
    prose_secrets = [
        f"Use AKIA{'Q' * 16} for the staging bucket.",
        f"Token {'gho_'}{'d' * 36} is the bot's.",
        f"Call it with AIza{'B' * 35} and retry.",
        f"Billing runs on {'sk_' + 'live_'}{'c' * 24} here.",
        f"Slack posts via {'xoxb-'}{'1' * 12}-{'e' * 12} now.",
    ]
    for prose in prose_secrets:
        redacted, was_redacted = redact_secrets(prose)
        assert was_redacted, f"not redacted: {prose}"

    ordinary = "This function returns the current identity token for the signed-in user."
    unchanged, was_redacted = redact_secrets(ordinary)
    assert unchanged == ordinary and not was_redacted
