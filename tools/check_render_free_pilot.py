#!/usr/bin/env python3
"""Minimal weekly smoke check for the DELTA Render Free pilot."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def fetch_text(url: str) -> tuple[int, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "DELTA-Free-Pilot-Check/1.0",
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.status, response.read().decode(charset, errors="replace")
    except HTTPError as exc:
        charset = exc.headers.get_content_charset() if exc.headers else None
        body = exc.read().decode(charset or "utf-8", errors="replace")
        return exc.code, body
    except URLError as exc:
        raise RuntimeError(f"request failed for {url}: {exc.reason}") from exc


def check_health() -> CheckResult:
    status, body = fetch_text("https://api.deltaplant.ai/api/health")
    if status != 200:
        return CheckResult("api_health", False, f"expected HTTP 200, got {status}")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return CheckResult("api_health", False, f"invalid JSON response: {exc}")

    if payload.get("status") != "ok":
        return CheckResult("api_health", False, f"unexpected status payload: {payload}")
    if payload.get("service") != "nasa-deltaplant":
        return CheckResult("api_health", False, f"unexpected service payload: {payload}")

    return CheckResult("api_health", True, f"HTTP 200, session={payload.get('session')}")


def check_homepage() -> CheckResult:
    status, body = fetch_text("https://deltaplant.ai/")
    if status != 200:
        return CheckResult("homepage", False, f"expected HTTP 200, got {status}")

    required_markers = (
        "DELTA Plant | NASA Crop Stress and Disease Monitor",
        "https://api.deltaplant.ai",
        "deltaplant-api-base",
    )
    missing = [marker for marker in required_markers if marker not in body]
    if missing:
        return CheckResult("homepage", False, f"missing markers: {', '.join(missing)}")

    return CheckResult("homepage", True, "root page references the live API base")


def check_legal_page(path: str) -> CheckResult:
    status, body = fetch_text(f"https://deltaplant.ai/{path}")
    if status != 200:
        return CheckResult(path, False, f"expected HTTP 200, got {status}")
    if "DELTA" not in body and "Delta" not in body:
        return CheckResult(path, False, "page loaded but expected legal content markers were missing")
    return CheckResult(path, True, "HTTP 200")


def run_checks() -> list[CheckResult]:
    checks = [
        check_health(),
        check_homepage(),
        check_legal_page("privacy-policy.html"),
        check_legal_page("cookie-policy.html"),
        check_legal_page("terms-of-service.html"),
    ]
    return checks


def print_results(results: Iterable[CheckResult]) -> int:
    failures = 0
    for result in results:
        prefix = "PASS" if result.ok else "FAIL"
        print(f"[{prefix}] {result.name}: {result.detail}")
        if not result.ok:
            failures += 1

    if failures:
        print(f"DELTA Render Free pilot check failed: {failures} check(s) failed.")
        return 1

    print("DELTA Render Free pilot check passed.")
    return 0


def main() -> int:
    try:
        return print_results(run_checks())
    except Exception as exc:  # pragma: no cover - top-level operational guard
        print(f"[FAIL] pilot_check: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())