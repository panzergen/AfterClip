import logging

from app.infrastructure.logging_filter import SECRET_REDACTOR

LOGGER = logging.getLogger(__name__)


class SecretStoreUnavailableError(RuntimeError):
    """Raised when the OS credential backend cannot store or read secrets."""


class KeyringSecretStore:
    """Cross-platform OS credential store backed by ``keyring``.

    Backends per platform: Windows Credential Manager, macOS Keychain and
    Linux Secret Service/KWallet. The import is deferred so tests can
    substitute a fake ``keyring`` module, and backend failures degrade to
    ``None`` on read while writes raise a clear ``SecretStoreUnavailableError``.
    """

    def __init__(self, service: str = "afterclip"):
        self.service = service

    def _keyring(self):
        import keyring

        return keyring

    def available(self) -> bool:
        """True when a real OS credential backend is present and usable."""
        try:
            keyring = self._keyring()
            get_keyring = getattr(keyring, "get_keyring", None)
            if get_keyring is None:
                # Minimal/embedded keyring shims cannot be introspected.
                return True
            backend = get_keyring()
        except Exception as error:  # backend discovery varies per platform
            LOGGER.debug("Could not inspect the credential backend: %s", error)
            return False
        # keyring installs this backend when no real one is available.
        return type(backend).__module__ != "keyring.backends.fail"

    def get(self, name: str) -> str | None:
        try:
            secret = self._keyring().get_password(self.service, name)
        except Exception as error:  # platform backends raise varied exception types
            LOGGER.warning("Credential backend could not read %s: %s", name, error)
            return None
        if secret:
            SECRET_REDACTOR.register(secret)
        return secret

    def set(self, name: str, value: str) -> None:
        keyring = self._keyring()
        previous = self.get(name)
        if previous and previous != value:
            # A rotated-out key must stop redacting log lines (CI #5).
            SECRET_REDACTOR.unregister(previous)
        try:
            keyring.set_password(self.service, name, value)
        except Exception as error:  # platform backends raise varied exception types
            raise SecretStoreUnavailableError(
                f"Could not store the credential in the OS credential manager: {error}"
            ) from error
        SECRET_REDACTOR.register(value)

    def delete(self, name: str) -> None:
        try:
            keyring = self._keyring()
        except Exception as error:  # keyring import failed entirely
            raise SecretStoreUnavailableError(
                f"The OS credential manager is unavailable: {error}"
            ) from error
        try:
            keyring.delete_password(self.service, name)
        except keyring.errors.PasswordDeleteError:
            return
        except Exception as error:  # platform backends raise varied exception types
            raise SecretStoreUnavailableError(
                f"Could not delete the credential from the OS credential manager: {error}"
            ) from error
