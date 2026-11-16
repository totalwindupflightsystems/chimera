"""Minimal OpenAI-compatible stub provider for the chimera-v2 dogfood run 30.

Serves POST /v1/chat/completions and GET /v1/models on 127.0.0.1:<PORT>.
The model id controls latency: `stub/sleep8` sleeps 8s, `stub/sleep20` sleeps 20s,
`stub/fast` answers immediately. Deliberately dumb: no auth checks beyond
accepting any Bearer token (a stub that 401s teaches nothing about timeouts).
"""

from __future__ import annotations

import json
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18777


def delay_for(model: str) -> float:
    m = re.search(r"sleep(\d+)", model)
    return float(m.group(1)) if m else 0.0


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep stdout readable
        sys.stderr.write("stub %s\n" % (fmt % args))

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/v1/models"):
            self._send(
                200,
                {
                    "object": "list",
                    "data": [
                        {"id": "stub/fast", "object": "model", "owned_by": "stub"},
                        {"id": "stub/sleep8", "object": "model", "owned_by": "stub"},
                        {"id": "stub/sleep20", "object": "model", "owned_by": "stub"},
                    ],
                },
            )
        else:
            self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            req = {}
        model = str(req.get("model", "stub/fast"))
        delay = delay_for(model)
        if delay:
            # sleep in short slices so a client disconnect does not wedge the thread
            deadline = time.monotonic() + delay
            while time.monotonic() < deadline:
                time.sleep(0.2)
        text = f"STUB[{model}] reply to prompt of {len(req.get('messages') or [])} messages"
        self._send(
            200,
            {
                "id": f"chatcmpl-stub-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
            },
        )


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    srv.daemon_threads = True
    sys.stderr.write(f"stub listening on 127.0.0.1:{PORT}\n")
    srv.serve_forever()
