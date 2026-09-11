from app.infrastructure.logging_filter import SECRET_REDACTOR


class KeyringSecretStore:
    """Credential Manager-backed store on Windows; import is deferred for testability."""

    def __init__(self, service: str = "afterclip"):
        self.service = service

    def get(self, name: str) -> str | None:
        import keyring

        secret = keyring.get_password(self.service, name)
        if secret:
            SECRET_REDACTOR.register(secret)
        return secret

    def set(self, name: str, value: str) -> None:
        previous = self.get(name)
        if previous and previous != value:
            # A rotated-out key must stop redacting log lines (CI #5).
            SECRET_REDACTOR.unregister(previous)
        SECRET_REDACTOR.register(value)
        import keyring

        keyring.set_password(self.service, name, value)

    def delete(self, name: str) -> None:
        import keyring

        try:
            keyring.delete_password(self.service, name)
        except keyring.errors.PasswordDeleteError:
            return
