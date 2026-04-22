from dataclasses import dataclass
from io import BytesIO
import re


@dataclass
class ReceiptScan:
    status: str
    text: str
    notes: list[str]
    confidence: int


def scan_receipt_text(content: bytes, content_type: str, filename: str) -> ReceiptScan:
    lower_name = filename.lower()
    if content_type == "application/pdf" or lower_name.endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except Exception:
            text = ""

        if text:
            return ReceiptScan(
                status="text_extracted",
                text=text,
                notes=["PDF содержит машинно-читаемый текст. Бот смог выполнить текстовую сверку."],
                confidence=40,
            )
        return ReceiptScan(
            status="no_text",
            text="",
            notes=["PDF похож на скан/картинку без текста. Нужна ручная проверка или OCR."],
            confidence=0,
        )

    if content_type.startswith("image/"):
        return ReceiptScan(
            status="image_needs_ocr",
            text="",
            notes=["Фото или скрин чека нельзя надежно прочитать без OCR. Нужна ручная проверка."],
            confidence=0,
        )

    return ReceiptScan(
        status="unsupported",
        text="",
        notes=["Формат файла не поддерживает автоматическое чтение текста."],
        confidence=0,
    )


def text_contains_amount(text: str, amount: object) -> bool:
    if not text or amount is None:
        return False
    normalized = text.replace(",", ".").replace(" ", "")
    raw = f"{amount}"
    candidates = {raw, raw.replace(".00", ""), raw.replace(".", "")}
    return any(candidate.replace(" ", "") in normalized for candidate in candidates)


def text_contains_operation(text: str, operation_id: str | None) -> bool:
    if not text or not operation_id:
        return False
    needle = re.sub(r"\s+", "", operation_id.lower())
    haystack = re.sub(r"\s+", "", text.lower())
    return needle in haystack


def text_contains_name_part(text: str, full_name: str) -> bool:
    if not text:
        return False
    haystack = text.lower()
    parts = [part.lower() for part in full_name.split() if len(part) >= 3]
    return bool(parts and any(part in haystack for part in parts))
