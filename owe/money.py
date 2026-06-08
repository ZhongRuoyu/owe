from decimal import Decimal, InvalidOperation

CENTS_PER_UNIT = 100


def amount_to_cents(amount: str) -> int:
  """Convert a decimal amount string into integer cents."""
  try:
    decimal_amount = Decimal(amount)
  except InvalidOperation as error:
    msg = f"Invalid amount: {amount}"
    raise ValueError(msg) from error

  if not decimal_amount.is_finite():
    msg = f"Invalid amount: {amount}"
    raise ValueError(msg)

  cents = decimal_amount * CENTS_PER_UNIT
  if cents <= 0 or cents != cents.to_integral_value():
    msg = (
      f"Amount must be a positive decimal with no fractional cents: {amount}"
    )
    raise ValueError(msg)

  return int(cents)


def cents_to_amount(cents: int) -> str:
  """Convert an integer cents amount into a decimal string."""
  decimal_amount = Decimal(cents) / CENTS_PER_UNIT
  return f"{decimal_amount:.2f}"
