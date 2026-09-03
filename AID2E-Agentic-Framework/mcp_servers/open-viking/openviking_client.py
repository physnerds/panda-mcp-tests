#!/usr/bin/env python3
"""Client utility for the OpenViking service on aipanda106.cern.ch.

Run ``source set_ssl.sh`` before using this client so the CERN CA path is
available through ``SSL_CERT_FILE`` or ``SSL_CERT_DIR``. The OpenViking API key
is read from ``.api_key`` in this directory by default.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Optional

import openviking as ov

DEFAULT_OPENVIKING_URL = "https://aipanda106.cern.ch:443"
DEFAULT_API_KEY_FILE = Path(__file__).resolve().parent / ".api_key"


def require_ssl_environment() -> None:
    """Fail early when set_ssl.sh has not configured certificate variables."""
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
        return
    raise RuntimeError(
        "SSL certificate environment is not configured. Run `source set_ssl.sh` "
        "from the open-viking directory before using this client."
    )


def load_api_key(api_key_file: Optional[str] = None) -> str:
    """Load the OpenViking API key from .api_key or an explicit key file."""
    token_path = Path(api_key_file).expanduser() if api_key_file else DEFAULT_API_KEY_FILE
    token_text = token_path.read_text(encoding="utf-8").strip()
    if not token_text:
        raise ValueError(f"OpenViking API key file is empty: {token_path}")
    return token_text


class OpenVikingAipandaClient:
    """Connection manager for the remote OpenViking service on aipanda106."""

    def __init__(
        self,
        url: str = DEFAULT_OPENVIKING_URL,
        api_key_file: Optional[str] = None,
        require_ssl: bool = True,
    ) -> None:
        if require_ssl:
            require_ssl_environment()
        self.url = url
        self.api_key_file = Path(api_key_file).expanduser() if api_key_file else DEFAULT_API_KEY_FILE
        self.api_key = load_api_key(str(self.api_key_file))
        self.client = ov.SyncHTTPClient(url=self.url, api_key=self.api_key)
        self.initialized = False

    def initialize(self) -> None:
        if not self.initialized:
            self.client.initialize()
            self.initialized = True

    def close(self) -> None:
        self.client.close()
        self.initialized = False

    def __enter__(self) -> "OpenVikingAipandaClient":
        self.initialize()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def find(
        self,
        query: str,
        target_uri: str = "",
        limit: int = 10,
    ) -> dict[str, Any]:
        self.initialize()
        return self.client.find(query=query, target_uri=target_uri, limit=limit)

    def ls(
        self,
        uri: str = "viking://resources/",
        simple: bool = False,
        recursive: bool = False,
    ) -> list[Any]:
        self.initialize()
        return self.client.ls(uri=uri, simple=simple, recursive=recursive)

    def read(self, uri: str, offset: int = 0, limit: int = -1) -> str:
        self.initialize()
        return self.client.read(uri=uri, offset=offset, limit=limit)

    def abstract(self, uri: str) -> str:
        self.initialize()
        return self.client.abstract(uri=uri)

    def overview(self, uri: str) -> str:
        self.initialize()
        return self.client.overview(uri=uri)

    def add_resource(
        self,
        path: str,
        to: Optional[str] = None,
        parent: Optional[str] = None,
        wait: bool = False,
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        self.initialize()
        return self.client.add_resource(
            path=path,
            to=to,
            parent=parent,
            wait=wait,
            timeout=timeout,
        )


def _json_default(value: Any) -> str:
    return str(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Connect to the OpenViking server on aipanda106.cern.ch."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("OPENVIKING_URL", DEFAULT_OPENVIKING_URL),
        help="OpenViking server URL.",
    )
    parser.add_argument(
        "--api-key-file",
        default=str(DEFAULT_API_KEY_FILE),
        help="File containing the OpenViking API key. Defaults to open-viking/.api_key.",
    )
    parser.add_argument(
        "--no-require-ssl-env",
        action="store_true",
        help="Do not require SSL_CERT_FILE or SSL_CERT_DIR to be set before connecting.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    find_parser = subparsers.add_parser("find", help="Semantic search over OpenViking resources.")
    find_parser.add_argument("query")
    find_parser.add_argument("--target-uri", default="")
    find_parser.add_argument("--limit", type=int, default=10)

    ls_parser = subparsers.add_parser("ls", help="List a viking:// resource directory.")
    ls_parser.add_argument("uri", nargs="?", default="viking://resources/")
    ls_parser.add_argument("--simple", action="store_true")
    ls_parser.add_argument("--recursive", action="store_true")

    read_parser = subparsers.add_parser("read", help="Read an exact viking:// resource URI.")
    read_parser.add_argument("uri")
    read_parser.add_argument("--offset", type=int, default=0)
    read_parser.add_argument("--limit", type=int, default=-1)

    abstract_parser = subparsers.add_parser("abstract", help="Get an L0 abstract for a resource URI.")
    abstract_parser.add_argument("uri")

    overview_parser = subparsers.add_parser("overview", help="Get an L1 overview for a resource URI.")
    overview_parser.add_argument("uri")

    add_parser = subparsers.add_parser("add-resource", help="Add a filesystem resource to OpenViking.")
    add_parser.add_argument("path")
    add_parser.add_argument("--to", default=None)
    add_parser.add_argument("--parent", default=None)
    add_parser.add_argument("--wait", action="store_true")
    add_parser.add_argument("--timeout", type=float, default=None)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    with OpenVikingAipandaClient(
        url=args.url,
        api_key_file=args.api_key_file,
        require_ssl=not args.no_require_ssl_env,
    ) as client:
        if args.command == "find":
            result = client.find(args.query, target_uri=args.target_uri, limit=args.limit)
        elif args.command == "ls":
            result = client.ls(args.uri, simple=args.simple, recursive=args.recursive)
        elif args.command == "read":
            result = client.read(args.uri, offset=args.offset, limit=args.limit)
        elif args.command == "abstract":
            result = client.abstract(args.uri)
        elif args.command == "overview":
            result = client.overview(args.uri)
        elif args.command == "add-resource":
            result = client.add_resource(
                args.path,
                to=args.to,
                parent=args.parent,
                wait=args.wait,
                timeout=args.timeout,
            )
        else:
            raise ValueError(f"Unknown command: {args.command}")

    print(json.dumps(result, indent=2, sort_keys=True, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
