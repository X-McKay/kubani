#!/usr/bin/env python3
"""Credential-minimal external heartbeat for the Starbase synthetic preview."""

from __future__ import annotations

import argparse
import http.client
import json
import socket
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import parse_qs, urlsplit


TARGET_HOST = "starbase.almckay.io"
TARGET_ADDRESSES = (
    "100.92.107.71",
    "100.77.107.81",
    "100.71.65.62",
    "100.76.45.84",
)
AUTHORIZATION_HOST = "auth.almckay.io"
AUTHORIZATION_PATH = "/application/o/authorize/"
CALLBACK_URL = f"https://{TARGET_HOST}/api/v1/auth/callback"
MAX_BODY_BYTES = 64 * 1024
EXPECTED_CHECKS = 7
MAX_SUCCESS_GAP_SECONDS = 405.0


class ProbeError(RuntimeError):
    """A sanitized, operator-actionable probe failure."""


class _ResolvedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to one address while retaining the reviewed TLS SNI hostname."""

    def __init__(self, host: str, address: str, *, timeout: float) -> None:
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        super().__init__(host, port=443, timeout=timeout, context=context)
        self._address = address

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._address, self.port),
            self.timeout,
            self.source_address,
        )
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except BaseException:
            raw_socket.close()
            raise


def validate_hostname(actual: str, expected: str) -> None:
    # This first-label comparison is an operator anti-footgun, not an
    # authentication boundary. Osprey's separately managed Tailscale device
    # identity and the supervised evidence review supply that boundary.
    actual_label = actual.rstrip(".").split(".", 1)[0].casefold()
    if actual_label != expected.rstrip(".").casefold():
        raise ProbeError("observer hostname does not match the reviewed host")


def validate_dns_addresses(
    observed: list[str], reviewed: tuple[str, ...]
) -> tuple[str, ...]:
    unique = tuple(dict.fromkeys(observed))
    if not unique or not set(unique).issubset(reviewed):
        raise ProbeError("Starbase DNS returned an unreviewed ingress address")
    return unique


def validate_login_redirect(location: str) -> None:
    try:
        parsed = urlsplit(location)
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise ProbeError("login returned a malformed OIDC redirect") from exc

    if (
        parsed.scheme,
        parsed.hostname,
        parsed.port,
        parsed.path,
        parsed.fragment,
        parsed.username,
        parsed.password,
    ) != (
        "https",
        AUTHORIZATION_HOST,
        None,
        AUTHORIZATION_PATH,
        "",
        None,
        None,
    ):
        raise ProbeError("login returned an unexpected OIDC destination")

    expected: Mapping[str, list[str]] = {
        "client_id": ["starbase-kubani"],
        "redirect_uri": [CALLBACK_URL],
        "response_type": ["code"],
        "code_challenge_method": ["S256"],
        "prompt": ["login"],
        "max_age": ["0"],
    }
    dynamic = {"scope", "state", "nonce", "code_challenge"}
    if set(query) != set(expected) | dynamic:
        raise ProbeError("login returned unexpected OIDC parameters")
    if any(query.get(key) != value for key, value in expected.items()):
        raise ProbeError("login changed a bound OIDC parameter")

    scopes = query.get("scope", [])
    if len(scopes) != 1 or set(scopes[0].split()) != {"groups", "openid"}:
        raise ProbeError("login changed the reviewed OIDC scopes")
    for name in ("state", "nonce", "code_challenge"):
        values = query.get(name, [])
        if len(values) != 1 or not values[0].strip():
            raise ProbeError("login omitted a required OIDC one-time value")


def _request(
    path: str,
    *,
    address: str,
    timeout: float,
) -> tuple[int, Mapping[str, str], bytes]:
    connection = _ResolvedHTTPSConnection(TARGET_HOST, address, timeout=timeout)
    try:
        connection.request(
            "GET",
            path,
            headers={"Accept": "application/json", "User-Agent": "kubani-osprey/1"},
        )
        response = connection.getresponse()
        body = response.read(MAX_BODY_BYTES + 1)
        if len(body) > MAX_BODY_BYTES:
            raise ProbeError("Starbase response exceeded the observer limit")
        return response.status, dict(response.getheaders()), body
    except ProbeError:
        raise
    except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
        raise ProbeError(f"Starbase request failed for {path}") from exc
    finally:
        connection.close()


def _json_object(body: bytes, label: str) -> Mapping[str, object]:
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProbeError(f"{label} returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise ProbeError(f"{label} returned an unexpected JSON shape")
    return value


def probe_starbase(*, timeout: float) -> int:
    checks = 0
    for address in TARGET_ADDRESSES:
        status, _, body = _request("/health/ready", address=address, timeout=timeout)
        if status != 200 or _json_object(body, "readiness").get("status") != "ready":
            raise ProbeError("a reviewed ingress path is not ready")
        checks += 1

    try:
        resolved = socket.getaddrinfo(TARGET_HOST, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ProbeError("Starbase DNS resolution failed") from exc
    dns_addresses = validate_dns_addresses(
        [result[4][0] for result in resolved], TARGET_ADDRESSES
    )
    dns_address = dns_addresses[0]
    status, _, body = _request("/health/ready", address=dns_address, timeout=timeout)
    if status != 200 or _json_object(body, "readiness").get("status") != "ready":
        raise ProbeError("the DNS-selected ingress path is not ready")
    checks += 1

    status, _, body = _request(
        "/api/v1/auth/session", address=dns_address, timeout=timeout
    )
    session = _json_object(body, "anonymous session")
    if (
        status != 200
        or session.get("mode") != "oidc"
        or session.get("authenticated") is not False
    ):
        raise ProbeError("anonymous session crossed the reviewed authentication boundary")
    checks += 1

    status, headers, _ = _request(
        "/api/v1/auth/login", address=dns_address, timeout=timeout
    )
    location = next(
        (value for name, value in headers.items() if name.casefold() == "location"), ""
    )
    if status != 303 or not location:
        raise ProbeError("login did not return the reviewed OIDC redirect")
    validate_login_redirect(location)
    return checks + 1


def parse_utc_timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProbeError(f"{label} is not a valid ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProbeError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def verify_journal(
    lines: Iterable[str],
    *,
    window_start: datetime,
    checkpoint: datetime,
) -> Mapping[str, object]:
    if window_start.tzinfo is None or window_start.utcoffset() is None:
        raise ProbeError("window start must include a timezone")
    if checkpoint.tzinfo is None or checkpoint.utcoffset() is None:
        raise ProbeError("checkpoint must include a timezone")
    window_start = window_start.astimezone(timezone.utc)
    checkpoint = checkpoint.astimezone(timezone.utc)
    if checkpoint <= window_start:
        raise ProbeError("checkpoint must be after the window start")

    successes: list[datetime] = []
    for line in lines:
        json_start = line.find("{")
        if json_start < 0:
            continue
        try:
            timestamp_text = line.split(maxsplit=1)[0]
            timestamp = datetime.strptime(
                timestamp_text, "%Y-%m-%dT%H:%M:%S.%f%z"
            ).astimezone(timezone.utc)
            event = json.loads(line[json_start:])
        except (IndexError, ValueError, json.JSONDecodeError) as exc:
            raise ProbeError("journal contains malformed observer evidence") from exc
        if event != {
            "status": "ok",
            "checks": EXPECTED_CHECKS,
            "observer": "osprey",
        }:
            raise ProbeError("journal contains ambiguous observer evidence")
        if timestamp < window_start or timestamp > checkpoint:
            raise ProbeError("journal success falls outside the declared window")
        if successes and timestamp <= successes[-1]:
            raise ProbeError("journal successes are not strictly ordered")
        successes.append(timestamp)

    if not successes:
        raise ProbeError("journal contains no successful observer runs")

    boundaries = [window_start, *successes, checkpoint]
    gaps = [
        (current - previous).total_seconds()
        for previous, current in zip(boundaries, boundaries[1:])
    ]
    max_gap = max(gaps)
    if max_gap > MAX_SUCCESS_GAP_SECONDS:
        raise ProbeError("observer success cadence exceeded the reviewed limit")
    return {
        "status": "ok",
        "runs": len(successes),
        "max_gap_seconds": max_gap,
        "window_seconds": (checkpoint - window_start).total_seconds(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-hostname", default="osprey")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--verify-journal", type=Path)
    parser.add_argument("--window-start")
    parser.add_argument("--checkpoint")
    args = parser.parse_args()
    if args.timeout <= 0 or args.timeout > 30:
        parser.error("--timeout must be greater than 0 and no more than 30 seconds")
    if args.verify_journal is not None:
        if args.window_start is None or args.checkpoint is None:
            parser.error(
                "--verify-journal requires --window-start and --checkpoint"
            )
    elif args.window_start is not None or args.checkpoint is not None:
        parser.error("journal timestamps require --verify-journal")
    return args


def main() -> int:
    args = parse_args()
    try:
        if args.verify_journal is not None:
            try:
                with args.verify_journal.open(encoding="utf-8") as journal:
                    result = verify_journal(
                        journal,
                        window_start=parse_utc_timestamp(
                            args.window_start, "window start"
                        ),
                        checkpoint=parse_utc_timestamp(args.checkpoint, "checkpoint"),
                    )
            except OSError as exc:
                raise ProbeError("observer journal is unavailable") from exc
            print(json.dumps(result, sort_keys=True))
            return 0
        validate_hostname(socket.gethostname(), args.require_hostname)
        checks = probe_starbase(timeout=args.timeout)
        print(
            json.dumps(
                {"status": "ok", "checks": checks, "observer": args.require_hostname}
            )
        )
        return 0
    except ProbeError as exc:
        print(f"starbase preview heartbeat failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
