"""Tiny adapter exposing the API expected by tifffile's fallback loader."""

from __future__ import annotations

from importlib import import_module


def _zstandard():
    return import_module("zstandard")


def compress(data: bytes, level: int | None = None) -> bytes:
    compressor = _zstandard().ZstdCompressor(level=level or 3)
    return compressor.compress(data)


def decompress(data: bytes) -> bytes:
    decompressor = _zstandard().ZstdDecompressor()
    return decompressor.decompress(data)