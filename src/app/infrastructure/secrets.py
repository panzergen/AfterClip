class KeyringSecretStore:
    """Credential Manager-backed store on Windows; import is deferred for testability."""

    def __init__(self, service: str = "afterclip"):
        self.service = service

    def get(self, name: str) -> str | None:
        import keyring

        return keyring.get_password(self.service, name)

    def set(self, name: str, value: str) -> None:
        import keyring

        keyring.set_password(self.service, name, value)

    def delete(self, name: str) -> None:
        import keyring

        try:
            keyring.delete_password(self.service, name)
        except keyring.errors.PasswordDeleteError:
            return
