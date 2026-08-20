"""Portable ABDA-NL development and demo server entrypoint."""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _load_environment(root: Path = REPO_ROOT) -> None:
    """Load local configuration without ever echoing its contents."""
    load_dotenv(root / ".env", override=False)
    load_dotenv(root / ".env.local", override=True)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _llm_is_configured() -> bool:
    backend = (os.getenv("ABDA_LLM_BACKEND") or "claude").strip().lower()
    if backend == "ollama":
        return True
    return backend == "claude" and bool(
        (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    )


def _configure_llm(mode: str) -> bool:
    if mode == "on":
        os.environ["ABDA_ENABLE_LLM"] = "1"
        return True
    if mode == "off":
        os.environ["ABDA_ENABLE_LLM"] = "0"
        return False

    explicit = os.getenv("ABDA_ENABLE_LLM")
    enabled = _truthy(explicit) if explicit is not None else _llm_is_configured()
    os.environ["ABDA_ENABLE_LLM"] = "1" if enabled else "0"
    return enabled


def _port_is_available(host: str, port: int) -> bool:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    bind_host = host
    if host == "localhost":
        family = socket.AF_INET
        bind_host = "127.0.0.1"
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((bind_host, port))
        except OSError:
            return False
    return True


def _choose_port(host: str, requested: int | None) -> int:
    if requested is not None:
        if not 1 <= requested <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if not _port_is_available(host, requested):
            raise RuntimeError(f"port {requested} is already in use on {host}")
        return requested

    for port in range(8000, 8101):
        if _port_is_available(host, port):
            return port
    raise RuntimeError("no available local port found from 8000 through 8100")


def _browser_host(host: str) -> str:
    return "127.0.0.1" if host in {"0.0.0.0", "::"} else host


def _open_browser_when_ready(base_url: str, timeout_seconds: float = 30.0) -> None:
    ready_url = f"{base_url.rstrip('/')}/health/ready"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(ready_url, timeout=0.75) as response:
                if response.status == 200:
                    webbrowser.open(base_url)
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.15)
    print(f"ABDA-NL started, but readiness was not confirmed at {ready_url}", file=sys.stderr)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ABDA-NL browser demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--reload", action="store_true", help="reload after source changes")
    parser.add_argument(
        "--allow-non-loopback",
        action="store_true",
        help="permit an explicit non-loopback bind for a managed deployment",
    )
    llm = parser.add_mutually_exclusive_group()
    llm.add_argument("--llm", dest="llm_mode", action="store_const", const="on")
    llm.add_argument("--basic", dest="llm_mode", action="store_const", const="off")
    parser.set_defaults(llm_mode="auto")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _load_environment()

    if args.host not in LOOPBACK_HOSTS and not args.allow_non_loopback:
        print("Refusing a non-loopback bind without --allow-non-loopback", file=sys.stderr)
        return 2

    try:
        port = _choose_port(args.host, args.port)
    except (RuntimeError, ValueError) as exc:
        print(f"Cannot start ABDA-NL: {exc}", file=sys.stderr)
        return 2

    llm_enabled = _configure_llm(args.llm_mode)
    base_url = f"http://{_browser_host(args.host)}:{port}"
    mode = "LLM enabled" if llm_enabled else "deterministic mode"
    print(f"Starting ABDA-NL at {base_url} ({mode})")

    if not args.no_browser:
        threading.Thread(
            target=_open_browser_when_ready,
            args=(base_url,),
            daemon=True,
            name="abda-browser-opener",
        ).start()

    import uvicorn

    uvicorn.run(
        "app.api.main:app",
        host=args.host,
        port=port,
        reload=args.reload,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
