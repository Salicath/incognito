from backend.core.profile import ImapConfig, Profile, ProfileVault, SmtpConfig


def test_imap_config_defaults():
    cfg = ImapConfig(host="imap.example.com", username="user@example.com", password="secret")
    assert cfg.port == 993
    assert cfg.folder == "INBOX"
    assert cfg.poll_interval_minutes == 5
    assert cfg.starttls is False


def test_imap_config_proton_bridge():
    cfg = ImapConfig(
        host="127.0.0.1",
        port=1143,
        username="user@proton.me",
        password="bridge-password",
        folder="INBOX",
        poll_interval_minutes=10,
        starttls=True,
    )
    assert cfg.port == 1143
    assert cfg.starttls is True


def test_vault_roundtrip_with_imap(tmp_path):
    vault = ProfileVault(tmp_path / "profile.enc")
    profile = Profile(full_name="Test", emails=["t@example.com"])
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="u", password="p")
    imap = ImapConfig(host="imap.test.com", username="u", password="p")

    vault.save(profile, smtp=smtp, imap=imap, password="pw")
    loaded_profile, loaded_smtp, loaded_imap = vault.load("pw")

    assert loaded_profile.full_name == "Test"
    assert loaded_smtp is not None
    assert loaded_smtp.host == "smtp.test.com"
    assert loaded_imap is not None
    assert loaded_imap.host == "imap.test.com"
    assert loaded_imap.port == 993


def test_vault_roundtrip_without_imap(tmp_path):
    vault = ProfileVault(tmp_path / "profile.enc")
    profile = Profile(full_name="Test", emails=["t@example.com"])
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="u", password="p")

    vault.save(profile, smtp=smtp, password="pw")
    loaded_profile, loaded_smtp, loaded_imap = vault.load("pw")

    assert loaded_profile.full_name == "Test"
    assert loaded_smtp is not None
    assert loaded_imap is None
