import re
from pathlib import Path

from django.core.exceptions import ValidationError


def validate_cnpj(value: str | None):
    if not value:
        return
    digits = re.sub(r"\D", "", value)
    if len(digits) != 14 or digits == digits[0] * 14:
        raise ValidationError("Informe um CNPJ válido com 14 dígitos.")

    def digit(base: str, weights: list[int]) -> str:
        total = sum(int(n) * w for n, w in zip(base, weights))
        remainder = total % 11
        return "0" if remainder < 2 else str(11 - remainder)

    d1 = digit(digits[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = digit(digits[:12] + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    if digits[-2:] != d1 + d2:
        raise ValidationError("O CNPJ informado não é válido.")


def validate_file_size(file):
    max_size = 10 * 1024 * 1024
    if file.size > max_size:
        raise ValidationError("O arquivo excede o limite de 10 MB.")


def validate_document_extension(file):
    allowed = {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".png",
        ".jpg",
        ".jpeg",
        ".txt",
        ".csv",
        ".odt",
    }
    extension = Path(file.name).suffix.lower()
    if extension not in allowed:
        raise ValidationError(f"Extensão não permitida: {extension}.")
