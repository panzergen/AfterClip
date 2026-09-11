import logging

REDACTED = "[REDACTED]"


class SecretRedactionFilter(logging.Filter):
    """Scrubs registered secret values from every log record.

    Messages are rewritten after %-formatting so no key can leak through
    positional args, and exception/traceback text is redacted as well
    (covers TEST_SCENARIOS.md T22).
    """

    def __init__(self):
        super().__init__()
        self._secrets: list[str] = []

    def register(self, secret: str) -> None:
        # Short strings would redact unrelated text (a 1-char secret redacts
        # every "k"); real API keys are far longer than this floor.
        if secret and len(secret) >= 8 and secret not in self._secrets:
            self._secrets.append(secret)

    def unregister(self, secret: str) -> None:
        """Drop a rotated-out secret so it stops widening redactions."""
        if secret in self._secrets:
            self._secrets.remove(secret)

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            if secret in text:
                text = text.replace(secret, REDACTED)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self.redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        if record.exc_info:
            record.exc_text = self.redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return True


SECRET_REDACTOR = SecretRedactionFilter()
