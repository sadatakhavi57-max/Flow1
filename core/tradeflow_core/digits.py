"""Digit normalization - contract section 2 'Digits'."""
_MAP = {ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_MAP.update({ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")})


def normalize_digits(s: str) -> str:
    """Persian (U+06F0..6F9) and Arabic-Indic (U+0660..0669) digits -> ASCII. Nothing else is touched."""
    return s.translate(_MAP)


def normalize_decimal_separator(s: str) -> str:
    """Arabic decimal separator U+066B -> '.'; used only where the contract allows it (DECIMAL specs)."""
    return s.replace("٫", ".")
