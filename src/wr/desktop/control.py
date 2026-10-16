from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Literal, overload
import hmac
import json
import os
import socket
import urllib.request

from wr.models.base import Record
from wr.models.desktop import ControlResponse, DataResponse, FolderResponse, StatusResponse, StopResponse


@overload
def control_request(endpoint: str, token: str, action: Literal["status"], timeout: float = 120) -> StatusResponse: ...


@overload
def control_request(endpoint: str, token: str, action: Literal["folder"], timeout: float = 120) -> FolderResponse: ...


@overload
def control_request(endpoint: str, token: str, action: Literal["data"], timeout: float = 120) -> DataResponse: ...


@overload
def control_request(endpoint: str, token: str, action: Literal["stop"], timeout: float = 120) -> StopResponse: ...


def control_request(endpoint: str, token: str, action: str, timeout: float = 120) -> ControlResponse:
    request = urllib.request.Request(
        endpoint + "/" + action, data=b"", method="POST",
        headers={"X-WR-Token": token},
    )
    # Bypass environment proxies: local financial operations never go through one.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
        model = {"status": StatusResponse, "folder": FolderResponse, "data": DataResponse, "stop": StopResponse}[action]
        return model.model_validate_json(response.read())


def desktop_request(action: str) -> ControlResponse:
    return control_request(os.environ["WR_CONTROL_URL"], os.environ["WR_CONTROL_TOKEN"], action)


def make_control_server(token: str, dispatch):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.headers.get("Origin") or not hmac.compare_digest(self.headers.get("X-WR-Token", ""), token):
                self.send_error(403)
                return
            action = self.path.removeprefix("/")
            if action not in {"status", "folder", "data", "stop"}:
                self.send_error(404)
                return
            try:
                result = dispatch(action)
                data = result.model_dump_json().encode() if isinstance(result, Record) else json.dumps(result).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self.send_error(503, "Launcher unavailable")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    return server


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
