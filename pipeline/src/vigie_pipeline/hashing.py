"""Empreintes stables utilisées pour la découverte et les manifestes."""

import hashlib


def sha256_bytes(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def sha256_text(content: str) -> str:
    return sha256_bytes(content.encode("utf-8"))
