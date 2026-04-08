# @module: aevara.tests.unit.infra.security.test_credential_vault
# @deps: aevara.src.infra.security.credential_vault
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para CredentialVault: loading, masking, rotation, integrity, expiration.

from __future__ import annotations

import time
import pytest

from aevara.src.infra.security.credential_vault import CredentialVault, CredentialEntry


# === HAPPY PATH ===
class TestCredentialVaultHappyPath:
    def test_set_and_get(self):
        vault = CredentialVault()
        vault.set("api_key", "secret_123")
        assert vault.get("api_key") == "secret_123"

    def test_verify_integrity(self):
        vault = CredentialVault()
        vault.set("key", "value")
        assert vault.verify_integrity("key")

    def test_rotate(self):
        vault = CredentialVault()
        vault.set("key", "old_value")
        vault.rotate("key", "new_value")
        assert vault.get("key") == "new_value"
        assert vault.verify_integrity("key")

    def test_mask_for_logging(self):
        assert CredentialVault.mask_for_logging("hello_world_123") == "hell***********"
        assert CredentialVault.mask_for_logging("ab", visible_chars=4) == "**"
        assert CredentialVault.mask_for_logging("") == ""

    def test_list_keys(self):
        vault = CredentialVault()
        vault.set("a", "1")
        vault.set("b", "2")
        keys = vault.list_keys()
        assert set(keys) == {"a", "b"}

    def test_remove(self):
        vault = CredentialVault()
        vault.set("key", "value")
        assert vault.remove("key")
        assert vault.get("key") is None
        assert not vault.remove("nonexistent")


# === EXPIRATION & ROTATION ===
class TestCredentialVaultExpiration:
    def test_expires_after_interval(self):
        vault = CredentialVault(default_rotation_s=1)
        vault.set("key", "value")
        assert vault.get("key") == "value"
        # Wait for expiry
        time.sleep(1.1)
        assert vault.get("key") is None

    def test_entry_is_expired(self):
        # Create entry that's already expired
        entry = CredentialEntry(
            key_id="e1",
            value_hash="abc",
            rotation_interval_s=1,
            last_rotated_ns=time.time_ns() - 5_000_000_000,  # 5 seconds ago
        )
        assert entry.is_expired()


# === ERROR CASES ===
class TestCredentialVaultErrors:
    def test_invalid_max_entries(self):
        with pytest.raises(AssertionError):
            CredentialVault(max_entries=0)

    def test_rotate_unknown_key(self):
        vault = CredentialVault()
        with pytest.raises(KeyError):
            vault.rotate("unknown", "new_value")

    def test_get_unknown_key(self):
        vault = CredentialVault()
        assert vault.get("unknown") is None

    def test_verify_unknown_key(self):
        vault = CredentialVault()
        assert not vault.verify_integrity("unknown")

    def test_eviction_when_full(self):
        vault = CredentialVault(max_entries=2, default_rotation_s=86400)
        vault.set("k1", "v1")
        vault.set("k2", "v2")
        vault.set("k3", "v3")  # Should evict oldest
        assert vault.get("k3") == "v3"
        assert len(vault.list_keys()) == 2
