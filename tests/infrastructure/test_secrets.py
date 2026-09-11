import sys
import types

import pytest

from app.infrastructure.logging_filter import REDACTED, SECRET_REDACTOR
from app.infrastructure.secrets import KeyringSecretStore


@pytest.fixture
def fake_keyring(monkeypatch):
    store = {}
    module = types.ModuleType("keyring")
    module.set_password = lambda service, name, value: store.__setitem__((service, name), value)
    module.get_password = lambda service, name: store.get((service, name))
    module.delete_password = lambda service, name: store.pop((service, name), None)
    module.errors = types.SimpleNamespace(PasswordDeleteError=type("PasswordDeleteError", (Exception,), {}))
    monkeypatch.setitem(sys.modules, "keyring", module)
    return module, store


def test_keyring_roundtrip_registers_secret_for_redaction(fake_keyring):
    module, store = fake_keyring
    secret_store = KeyringSecretStore(service="test-svc")
    secret_store.set("gemini", "sk-roundtrip-value")
    assert store[("test-svc", "gemini")] == "sk-roundtrip-value"
    assert secret_store.get("gemini") == "sk-roundtrip-value"
    assert SECRET_REDACTOR.redact("key sk-roundtrip-value leaked") == f"key {REDACTED} leaked"


def test_keyring_delete_removes_secret(fake_keyring):
    module, store = fake_keyring
    secret_store = KeyringSecretStore(service="test-svc")
    secret_store.set("gemini", "sk-delete-value")
    secret_store.delete("gemini")
    assert ("test-svc", "gemini") not in store
    assert secret_store.get("gemini") is None


def test_keyring_delete_missing_password_is_silent(fake_keyring):
    module, _ = fake_keyring
    missing = ("test-svc", "ghost")

    def raise_delete_error(service, name):
        if (service, name) == missing:
            raise module.errors.PasswordDeleteError("not found")

    module.delete_password = raise_delete_error
    KeyringSecretStore(service="test-svc").delete("ghost")
