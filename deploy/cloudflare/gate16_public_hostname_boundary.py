#!/usr/bin/env python3
"""Read-only acceptance for the ABDA-NL public hostname boundary."""

from __future__ import annotations

from dataclasses import dataclass
import http.client
import ipaddress
import json
import shutil
import ssl
import subprocess
from urllib.parse import urlsplit


SCRIPT_REVISION = "1"
APEX_HOST = "abda-nl.org"
WWW_HOST = "www.abda-nl.org"
DEMO_HOST = "demo.abda-nl.org"
DEMO_CNAME = "abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io"
LOGIN_HOST = "login.abda-nl.org"
LOGIN_CNAME = "abda-nl-public-cd-agj741h5jp2wla4l.edge.tenants.us.auth0.com"
DEMO_ORIGIN = f"https://{DEMO_HOST}"


class AcceptanceError(RuntimeError):
    """Raised when the public hostname contract is not satisfied."""


@dataclass(frozen=True)
class HTTPResult:
    status: int
    headers: dict[str, str]
    body: bytes


def _normalized_dns_value(value: str) -> str:
    return value.strip().strip('"').rstrip(".").lower()


def query_dns(name: str, record_type: str) -> list[str]:
    if shutil.which("dig") is None:
        raise AcceptanceError("the dig command is unavailable")
    try:
        completed = subprocess.run(
            ["dig", "+time=5", "+tries=1", "+short", name, record_type],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired as exc:
        raise AcceptanceError(f"the {name} {record_type} DNS query timed out") from exc
    if completed.returncode != 0:
        raise AcceptanceError(f"the {name} {record_type} DNS query failed")
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def request(url: str, *, timeout: float = 15.0) -> HTTPResult:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise AcceptanceError("an invalid fixed acceptance URL was configured")
    if parsed.username or parsed.password or parsed.port:
        raise AcceptanceError("acceptance URLs may not contain credentials or ports")
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"
    connection_class = (
        http.client.HTTPSConnection
        if parsed.scheme == "https"
        else http.client.HTTPConnection
    )
    kwargs: dict[str, object] = {"timeout": timeout}
    if parsed.scheme == "https":
        kwargs["context"] = ssl.create_default_context()
    connection = connection_class(parsed.hostname, **kwargs)
    try:
        connection.request(
            "GET",
            path,
            headers={
                "Accept": "application/json,text/html;q=0.9,*/*;q=0.1",
                "User-Agent": "ABDA-NL-public-hostname-acceptance/1",
            },
        )
        response = connection.getresponse()
        body = response.read(1_048_577)
        if len(body) > 1_048_576:
            raise AcceptanceError("an acceptance response exceeded one MiB")
        headers = {name.lower(): value for name, value in response.getheaders()}
        return HTTPResult(status=response.status, headers=headers, body=body)
    except (OSError, TimeoutError, ssl.SSLError, http.client.HTTPException) as exc:
        raise AcceptanceError(f"the request to {parsed.hostname} failed") from exc
    finally:
        connection.close()


def validate_redirect(result: HTTPResult, expected_location: str) -> None:
    if result.status != 301:
        raise AcceptanceError("a friendly hostname did not return HTTP 301")
    if result.headers.get("location") != expected_location:
        raise AcceptanceError("a friendly hostname changed the redirect target")


def validate_http_entry(result: HTTPResult, path: str) -> None:
    expected_target = f"{DEMO_ORIGIN}{path}"
    if result.status == 301 and result.headers.get("location") == expected_target:
        return
    https_apex = f"https://{APEX_HOST}{path}"
    if result.status not in {301, 308} or result.headers.get("location") != https_apex:
        raise AcceptanceError("the plaintext apex redirect boundary changed")
    validate_redirect(request(https_apex), expected_target)


def validate_json(result: HTTPResult, expected: dict[str, object], label: str) -> None:
    if result.status != 200:
        raise AcceptanceError(f"{label} did not return HTTP 200")
    try:
        payload = json.loads(result.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"{label} returned invalid JSON") from exc
    if payload != expected:
        raise AcceptanceError(f"{label} returned an unexpected response")


def _require_ip_records(records: list[str], label: str) -> None:
    if not records:
        raise AcceptanceError(f"{label} has no public A record")
    try:
        addresses = [ipaddress.ip_address(item) for item in records]
    except ValueError as exc:
        raise AcceptanceError(f"{label} returned an invalid A record") from exc
    if any(not isinstance(address, ipaddress.IPv4Address) for address in addresses):
        raise AcceptanceError(f"{label} returned a non-IPv4 A record")


def validate_dns_snapshot(records: dict[tuple[str, str], list[str]]) -> None:
    _require_ip_records(records[(APEX_HOST, "A")], "the apex hostname")
    _require_ip_records(records[(WWW_HOST, "A")], "the www hostname")

    demo_cnames = {
        _normalized_dns_value(value) for value in records[(DEMO_HOST, "CNAME")]
    }
    if demo_cnames != {DEMO_CNAME}:
        raise AcceptanceError("the demo CNAME changed")
    login_cnames = {
        _normalized_dns_value(value) for value in records[(LOGIN_HOST, "CNAME")]
    }
    if login_cnames != {LOGIN_CNAME}:
        raise AcceptanceError("the Auth0 custom-domain CNAME changed")

    mx_records = " ".join(records[("send.auth.abda-nl.org", "MX")]).lower()
    if "feedback-smtp.us-east-1.amazonses.com" not in mx_records:
        raise AcceptanceError("the Resend return-path MX record changed")
    spf_records = " ".join(records[("send.auth.abda-nl.org", "TXT")]).lower()
    if "v=spf1" not in spf_records or "include:amazonses.com" not in spf_records:
        raise AcceptanceError("the Resend SPF record changed")
    dkim_records = "".join(
        records[("resend._domainkey.auth.abda-nl.org", "TXT")]
    ).replace('"', "")
    if not dkim_records.startswith("p=") or len(dkim_records) < 64:
        raise AcceptanceError("the Resend DKIM record is absent or invalid")
    dmarc_records = " ".join(records[("_dmarc.auth.abda-nl.org", "TXT")]).lower()
    if "v=dmarc1" not in dmarc_records or "p=none" not in dmarc_records:
        raise AcceptanceError("the authentication-domain DMARC record changed")


def collect_dns_snapshot() -> dict[tuple[str, str], list[str]]:
    queries = (
        (APEX_HOST, "A"),
        (WWW_HOST, "A"),
        (DEMO_HOST, "CNAME"),
        (LOGIN_HOST, "CNAME"),
        ("send.auth.abda-nl.org", "MX"),
        ("send.auth.abda-nl.org", "TXT"),
        ("resend._domainkey.auth.abda-nl.org", "TXT"),
        ("_dmarc.auth.abda-nl.org", "TXT"),
    )
    return {(name, kind): query_dns(name, kind) for name, kind in queries}


def run_acceptance() -> None:
    validate_dns_snapshot(collect_dns_snapshot())
    validate_redirect(request(f"https://{APEX_HOST}/"), f"{DEMO_ORIGIN}/")
    test_path = "/privacy.html?source=redirect-test"
    validate_redirect(
        request(f"https://{WWW_HOST}{test_path}"),
        f"{DEMO_ORIGIN}{test_path}",
    )
    validate_http_entry(
        request(f"http://{APEX_HOST}/health/ready"),
        "/health/ready",
    )
    validate_json(
        request(f"{DEMO_ORIGIN}/health/ready"),
        {"status": "ready"},
        "the direct demo readiness endpoint",
    )
    discovery = request(f"https://{LOGIN_HOST}/.well-known/openid-configuration")
    if discovery.status != 200:
        raise AcceptanceError("the Auth0 custom domain did not return discovery metadata")
    try:
        issuer = json.loads(discovery.body).get("issuer")
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError("the Auth0 custom domain returned invalid metadata") from exc
    if issuer != f"https://{LOGIN_HOST}/":
        raise AcceptanceError("the Auth0 custom-domain issuer changed")


def main() -> int:
    try:
        run_acceptance()
    except AcceptanceError as exc:
        print(f"STOP: {exc}")
        return 1
    print("ABDA-NL public hostname boundary status:")
    print(f"script_revision: {SCRIPT_REVISION}")
    print(f"public_origin: {DEMO_ORIGIN}")
    print("apex_https_redirect: passed")
    print("apex_http_redirect: passed")
    print("www_https_redirect: passed")
    print("path_and_query_preserved: passed")
    print("demo_origin_readiness: passed")
    print("auth0_custom_domain: passed")
    print("resend_spf_dkim_dmarc_mx: passed")
    print("credentials_used: false")
    print("external_state_changed: false")
    print("result: PUBLIC_HOSTNAME_AND_EMAIL_DNS_BOUNDARY_VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
