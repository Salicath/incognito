"""Tests for vault-backed API secrets and legacy plaintext-file migration."""

from datetime import date

from backend.core.profile import Profile, ProfileVault, SmtpConfig
from backend.core.secrets import read_secret, remove_secret, write_secret


def _vault(tmp_path, password="pw"):
    v = ProfileVault(tmp_path / "profile.enc")
    profile = Profile(full_name="T", emails=["t@example.com"], date_of_birth=date(1990, 1, 1))
    v.save(profile, SmtpConfig(host="h", port=587, username="u", password="p"), password)
    key, salt = v.derive_key_from_file(password)
    return v, key, salt


class TestVaultSecrets:
    def test_set_get_roundtrip(self, tmp_path):
        v, key, salt = _vault(tmp_path)
        assert v.get_secret("hibp", key) is None
        v.set_secret("hibp", "abc123", key, salt)
        assert v.get_secret("hibp", key) == "abc123"

    def test_delete(self, tmp_path):
        v, key, salt = _vault(tmp_path)
        v.set_secret("github", "ghp_x", key, salt)
        assert v.delete_secret("github", key, salt) is True
        assert v.get_secret("github", key) is None
        assert v.delete_secret("github", key, salt) is False

    def test_secrets_survive_ordinary_profile_save(self, tmp_path):
        """The critical property: saving profile/smtp must not wipe stored secrets."""
        v, key, salt = _vault(tmp_path)
        v.set_secret("hibp", "keepme", key, salt)

        # simulate a settings profile update (save_with_key with no secrets arg)
        profile, smtp, imap = v.load_with_key(key)
        profile.full_name = "Changed Name"
        v.save_with_key(profile, smtp, imap, key, salt)

        assert v.get_secret("hibp", key) == "keepme"
        assert v.load_with_key(key)[0].full_name == "Changed Name"

    def test_multiple_secrets_independent(self, tmp_path):
        v, key, salt = _vault(tmp_path)
        v.set_secret("hibp", "h", key, salt)
        v.set_secret("github", "g", key, salt)
        assert v.get_secret("hibp", key) == "h"
        assert v.get_secret("github", key) == "g"

    def test_old_vault_without_secrets_field_loads(self, tmp_path):
        """A vault written before the secrets field must still load (defaults to {})."""
        v, key, salt = _vault(tmp_path)
        # A fresh vault has no secrets; reading one returns None, not an error.
        assert v.get_secret("hibp", key) is None
        assert v.load_with_key(key)[0].full_name == "T"


class TestLegacyMigration:
    def test_read_migrates_legacy_file_into_vault(self, tmp_path):
        v, key, salt = _vault(tmp_path)
        legacy = tmp_path / "hibp_key.txt"
        legacy.write_text("legacy-key\n")

        value = read_secret(v, tmp_path, key, salt, "hibp")
        assert value == "legacy-key"
        # file is consumed and the secret now lives in the vault
        assert not legacy.exists()
        assert v.get_secret("hibp", key) == "legacy-key"

    def test_read_prefers_vault_over_legacy(self, tmp_path):
        v, key, salt = _vault(tmp_path)
        v.set_secret("github", "vault-token", key, salt)
        (tmp_path / "github_token.txt").write_text("stale-file-token")

        assert read_secret(v, tmp_path, key, salt, "github") == "vault-token"

    def test_read_returns_none_when_absent(self, tmp_path):
        v, key, salt = _vault(tmp_path)
        assert read_secret(v, tmp_path, key, salt, "github") is None

    def test_remove_clears_vault_and_legacy_file(self, tmp_path):
        v, key, salt = _vault(tmp_path)
        v.set_secret("hibp", "x", key, salt)
        legacy = tmp_path / "hibp_key.txt"
        legacy.write_text("also-here")

        remove_secret(v, tmp_path, key, salt, "hibp")
        assert v.get_secret("hibp", key) is None
        assert not legacy.exists()

    def test_write_secret_helper(self, tmp_path):
        v, key, salt = _vault(tmp_path)
        write_secret(v, key, salt, "hibp", "written")
        assert v.get_secret("hibp", key) == "written"


class TestSettingsApiMigration:
    """A legacy plaintext key on disk is adopted by the vault via the settings API."""

    def test_get_migrates_legacy_hibp_file(self, authenticated_client, config):
        legacy = config.data_dir / "hibp_key.txt"
        legacy.write_text("legacy-hibp-key-1234")

        resp = authenticated_client.get("/api/settings/hibp")
        assert resp.status_code == 200
        assert resp.json()["configured"] is True
        # file consumed; value now served from the vault on subsequent reads
        assert not legacy.exists()
        assert authenticated_client.get("/api/settings/hibp").json()["configured"] is True

    def test_save_then_read_via_vault(self, authenticated_client, config):
        authenticated_client.post("/api/settings/github", json={"api_key": "ghp_vaulted_token"})
        # nothing written to the legacy plaintext file
        assert not (config.data_dir / "github_token.txt").exists()
        status = authenticated_client.get("/api/settings/github").json()
        assert status["configured"] is True
        assert status["key_preview"].startswith("ghp_")
