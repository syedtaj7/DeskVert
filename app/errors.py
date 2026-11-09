"""Error types and plain-language messages shown to the user."""

from __future__ import annotations


class ConversionError(Exception):
    """A failure whose message is already written for the user."""


class VerificationError(ConversionError):
    """The output was produced but did not match the source. It is discarded."""

    def __init__(self, detail: str):
        super().__init__(f"Safety check failed, so the file was not saved ({detail}).")


class Cancelled(ConversionError):
    def __init__(self):
        super().__init__("Cancelled.")


def friendly(exc: BaseException) -> str:
    if isinstance(exc, ConversionError):
        return str(exc)
    name = type(exc).__name__
    msg = str(exc)
    low = msg.lower()
    if name == "UnidentifiedImageError":
        return "This file isn't a readable image, or it is damaged."
    if name == "DecompressionBombError":
        return "This image is too large to convert safely."
    if isinstance(exc, MemoryError):
        return "Not enough free memory to convert this file."
    if isinstance(exc, FileNotFoundError):
        return "The file was moved or deleted before it could be converted."
    if isinstance(exc, PermissionError):
        return "Windows blocked access to the file. It may be open in another app."
    if isinstance(exc, OSError):
        win = getattr(exc, "winerror", None)
        if win == 32:
            return "The file is being used by another app."
        if win == 112 or "no space" in low:
            return "The disk is full."
        if "truncated" in low:
            return "The file is incomplete or damaged (truncated)."
        if "cannot write mode" in low or "cannot write" in low:
            return f"This image type can't be saved in that format ({msg})."
    return f"Unexpected error: {name}: {msg}"
