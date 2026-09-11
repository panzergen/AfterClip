import sys
import types

import pytest

from app.infrastructure.logging_filter import REDACTED, SECRET_REDACTOR
from app.infrastructure.secrets import KeyringSecretStore, SecretStoreUnavailableError


class _FakeBackend:
    """Stand-in for a real keyring backend class."""


@pytest.fixture
def fake_keyring(monkeypatch):
    store = {}
    module = types.ModuleType("keyring")
    module.set_password = lambda service, name, value: store.__setitem__((service, name), value)
    module.get_password = lambda service, name: store.get((service, name))
    module.delete_password = lambda service, name: store.pop((service, name), None)
    module.get_keyring = lambda: _FakeBackend()
    module.errors = types.SimpleNamespace(
        PasswordDeleteError=type("PasswordDeleteError", (Exception,), {})
    )
    monkeypatch.setitem(sys.modules, "keyring", module)
    return module, store


def test_keyring_roundtrip_registers_secret_for_redaction(fake_keyring):
    _module, store = fake_keyring
    secret_store = KeyringSecretStore(service="test-svc")
    secret_store.set("gemini", "sk-roundtrip-value")
    assert store[("test-svc", "gemini")] == "sk-roundtrip-value"
    assert secret_store.get("gemini") == "sk-roundtrip-value"
    assert SECRET_REDACTOR.redact("key sk-roundtrip-value leaked") == f"key {REDACTED} leaked"


def test_keyring_delete_removes_secret(fake_keyring):
    _module, store = fake_keyring
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


def test_available_true_with_real_backend(fake_keyring):
    assert KeyringSecretStore(service="test-svc").available() is True


def test_available_false_for_fail_backend(monkeypatch):
    module = types.ModuleType("keyring")

    class FailKeyring:
        pass

    FailKeyring.__module__ = "keyring.backends.fail"
    module.get_keyring = lambda: FailKeyring()
    monkeypatch.setitem(sys.modules, "keyring", module)
    assert KeyringSecretStore(service="test-svc").available() is False


def test_get_returns_none_when_backend_errors(fake_keyring):
    module, _ = fake_keyring

    def boom(service, name):
        raise RuntimeError("no backend")

    module.get_password = boom
    assert KeyringSecretStore(service="test-svc").get("gemini") is None


def test_set_raises_clear_error_when_backend_fails(fake_keyring):
    module, _ = fake_keyring

    def boom(service, name, value):
        raise RuntimeError("no backend")

    module.set_password = boom
    with pytest.raises(SecretStoreUnavailableError):
        KeyringSecretStore(service="test-svc").set("gemini", "sk-unavailable-value")


def test_rotating_key_unregisters_previous_from_redaction(fake_keyring):
    secret_store = KeyringSecretStore(service="test-svc")
    secret_store.set("gemini", "sk-old-rotation-value")
    assert SECRET_REDACTOR.redact("sk-old-rotation-value") == REDACTED

    secret_store.set("gemini", "sk-new-rotation-value")
    # The rotated-out value stops being redacted; the new one is redacted.
    assert SECRET_REDACTOR.redact("sk-old-rotation-value") == "sk-old-rotation-value"
    assert SECRET_REDACTOR.redact("sk-new-rotation-value") == REDACTED
