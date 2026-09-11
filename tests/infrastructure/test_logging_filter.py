import logging

from app.infrastructure.logging_filter import REDACTED, SECRET_REDACTOR, SecretRedactionFilter


def test_redacts_registered_secret_from_message(caplog):
    redactor = SecretRedactionFilter()
    logger = logging.getLogger("test.redaction.message")
    logger.addFilter(redactor)
    redactor.register("sk-super-secret-key")
    with caplog.at_level(logging.WARNING, logger="test.redaction.message"):
        logger.warning("Authentication failed for key sk-super-secret-key while calling provider")
    assert "sk-super-secret-key" not in caplog.text
    assert REDACTED in caplog.text


def test_redacts_secret_inside_exception_traceback(caplog):
    redactor = SecretRedactionFilter()
    logger = logging.getLogger("test.redaction.traceback")
    logger.addFilter(redactor)
    redactor.register("sk-super-secret-key")
    with caplog.at_level(logging.ERROR, logger="test.redaction.traceback"):
        try:
            raise RuntimeError("provider call failed with key sk-super-secret-key")
        except RuntimeError:
            logger.exception("Provider crashed")
    assert "sk-super-secret-key" not in caplog.text
    assert REDACTED in caplog.text


def test_unregistered_secrets_pass_through_and_filter_accepts_records():
    redactor = SecretRedactionFilter()
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    assert redactor.filter(record) is True
    assert record.getMessage() == "hello world"


def test_register_ignores_short_strings():
    redactor = SecretRedactionFilter()
    redactor.register("k")
    redactor.register("ok-key")
    assert redactor.redact("key ok-key value") == "key ok-key value"
    redactor.register("long-enough-secret")
    assert redactor.redact("x long-enough-secret y") == f"x {REDACTED} y"


def test_unregister_drops_rotated_keys():
    redactor = SecretRedactionFilter()
    redactor.register("old-key-value-123")
    redactor.register("new-key-value-456")
    redactor.unregister("old-key-value-123")
    assert redactor.redact("old-key-value-123 and new-key-value-456") == (
        f"old-key-value-123 and {REDACTED}"
    )


def test_unregister_missing_secret_is_silent():
    redactor = SecretRedactionFilter()
    redactor.unregister("never-registered-key")  # must not raise
