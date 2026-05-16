#!/usr/bin/env python3
"""Minimal weekly smoke check for the DELTA Render Free pilot."""

from __future__ import annotations

import http.cookiejar
import json
import sys
from dataclasses import dataclass
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


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


def opener_request(
    opener,
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    accept: str = "application/json, text/html;q=0.9, */*;q=0.8",
    content_type: str | None = None,
    timeout: int = 45,
) -> tuple[int, bytes, dict[str, str]]:
    headers = {
        "User-Agent": "DELTA-Free-Pilot-Check/1.0",
        "Accept": accept,
    }
    if content_type:
        headers["Content-Type"] = content_type
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read(), dict(response.headers.items())
    except HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers.items()) if exc.headers else {}
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


def check_live_area_analysis() -> CheckResult:
    cookie_jar = http.cookiejar.CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))

    health_status, health_body, _ = opener_request(opener, "https://api.deltaplant.ai/api/health", timeout=20)
    if health_status != 200:
        return CheckResult("area_analysis", False, f"health bootstrap failed with HTTP {health_status}")

    analysis_payload = {
        "geo_data": {
            "type": "circle",
            "center": {"lat": 45.46, "lng": 9.19},
            "radius": 250.0,
        },
        "date_range": {
            "start": "2026-04-01",
            "end": "2026-04-30",
        },
        "user_token": "dp_user_token_1234567890",
        "crop_answers": ["herbaceous"],
    }
    analysis_status, analysis_body, _ = opener_request(
        opener,
        "https://api.deltaplant.ai/api/nisar/area-analysis",
        method="POST",
        body=json.dumps(analysis_payload).encode("utf-8"),
        content_type="application/json",
        timeout=45,
    )
    if analysis_status != 200:
        detail = analysis_body.decode("utf-8", errors="replace")[:200].strip()
        return CheckResult("area_analysis", False, f"expected HTTP 200, got {analysis_status}: {detail or 'empty body'}")

    try:
        analysis_response = json.loads(analysis_body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        return CheckResult("area_analysis", False, f"invalid JSON response: {exc}")

    diagnosis = analysis_response.get("diagnosis") or {}
    pdf_tokens = analysis_response.get("pdf_tokens") or {}
    probable_crop = diagnosis.get("probable_crop")
    farmer_token = pdf_tokens.get("farmer")
    if not probable_crop or not farmer_token:
        return CheckResult("area_analysis", False, "missing probable_crop or farmer PDF token")

    pdf_status, pdf_body, pdf_headers = opener_request(
        opener,
        f"https://api.deltaplant.ai/api/nisar/pdf/{farmer_token}",
        accept="application/pdf, */*;q=0.8",
        timeout=20,
    )
    content_type = pdf_headers.get("Content-Type", "")
    if pdf_status != 200 or "application/pdf" not in content_type.lower() or not pdf_body.startswith(b"%PDF"):
        return CheckResult(
            "area_analysis",
            False,
            f"pdf download check failed: HTTP {pdf_status}, content-type={content_type or 'missing'}",
        )

    return CheckResult(
        "area_analysis",
        True,
        f"probable_crop={probable_crop}, mode={analysis_response.get('processing_mode', 'unknown')}",
    )


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
        check_live_area_analysis(),
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