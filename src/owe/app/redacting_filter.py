import logging
import re


class RedactingFilter(logging.Filter):
  """A logging filter that redacts secrets from log messages."""

  _pattern: re.Pattern | None
  _secret_lengths: dict[str, int]

  def __init__(self, *secrets: str) -> None:
    """Initialize the filter with secrets."""
    super().__init__()
    secrets: list[str] = [secret for secret in secrets if secret]
    self._secret_lengths = {secret: len(secret) for secret in secrets}
    if secrets:
      self._pattern = re.compile(
        "|".join(re.escape(secret) for secret in secrets)
      )
    else:
      self._pattern = None

  def filter(self, record: logging.LogRecord) -> bool:
    """Redact secrets from the log message before it is emitted."""
    if self._pattern is None:
      return True
    original_message = record.getMessage()
    redacted_message = self._pattern.sub(
      lambda match: "*" * self._secret_lengths[match.group(0)],
      original_message,
    )
    record.msg = redacted_message
    record.args = None
    return True
