import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import agent


HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8000"))

BASE_DIR = Path(__file__).resolve().parent
UI_FILE = BASE_DIR / "mobile_ui.html"


class AgentHandler(BaseHTTPRequestHandler):

    def _send_json(self, status_code: int, payload: Any) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")

        self.send_response(status_code)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )
        self.send_header(
            "Content-Length",
            str(len(body)),
        )
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self) -> None:
        if not UI_FILE.exists():
            self._send_json(
                404,
                {
                    "status": "error",
                    "error": "mobile_ui.html not found",
                },
            )
            return

        body = UI_FILE.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8",
        )
        self.send_header(
            "Content-Length",
            str(len(body)),
        )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[HTTP] {self.address_string()} - {fmt % args}")

    def do_GET(self):
        if self.path in {"/", "/index.html", "/mobile_ui.html"}:
            self._send_html()
            return
        if self.path == "/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "service": "AI Agent",
                    "port": PORT,
                },
            )
            return

        if self.path == "/project":
            project = agent.get_current_project()
            data = (
                agent.project_context(int(project["id"]))
                if isinstance(project, dict) and project.get("id") is not None
                else {}
            )
            self._send_json(
                200,
                {
                    "status": "completed",
                    "workflow": "project",
                    "response": "Current project loaded.",
                    "results": [],
                    "errors": [],
                    "data": {"current_project": data},
                },
            )
            return

        if self.path == "/tasks":
            tasks = agent.load_tasks()
            self._send_json(
                200,
                {
                    "status": "completed",
                    "workflow": "tasks",
                    "response": "Tasks loaded.",
                    "results": tasks,
                    "errors": [],
                    "data": {},
                },
            )
            return

        if self.path == "/memory":
            memory = agent.load_memory()
            self._send_json(
                200,
                {
                    "status": "completed",
                    "workflow": "memory",
                    "response": "Memory loaded.",
                    "results": [],
                    "errors": [],
                    "data": {"memory": memory},
                },
            )
            return

        self._send_json(
            404,
            {
                "status": "error",
                "error": "Not found",
            },
        )

    def do_POST(self):
        if self.path != "/command":
            self._send_json(
                404,
                {
                    "status": "error",
                    "error": "Not found",
                },
            )
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 64 * 1024:
                self._send_json(
                    400,
                    {
                        "status": "error",
                        "error": "Invalid request body",
                    },
                )
                return

            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))

            if not isinstance(data, dict):
                raise ValueError("JSON body must be an object")

            command = str(data.get("command", "")).strip()
            if not command:
                self._send_json(
                    400,
                    {
                        "status": "error",
                        "error": "command is required",
                    },
                )
                return

            print(f"[COMMAND] {command}")
            result = agent.process_command(command)

            if not isinstance(result, dict):
                raise TypeError(
                    "agent.process_command() must return a dictionary"
                )

            print(
                "[AGENT RESULT]",
                f"status={result.get('status')}",
                f"workflow={result.get('workflow')}",
            )

            # The HTTP request succeeded even when the agent reports
            # an application-level error. This keeps the UI response contract
            # consistent and lets the frontend display agent errors normally.
            self._send_json(200, result)

        except json.JSONDecodeError:
            self._send_json(
                400,
                {
                    "status": "error",
                    "error": "Invalid JSON",
                },
            )

        except Exception as exc:
            print(f"[SERVER ERROR] {type(exc).__name__}: {exc}")
            self._send_json(
                500,
                {
                    "status": "error",
                    "error": str(exc),
                },
            )


if __name__ == "__main__":
    print("AI Agent Mobile Server")
    print(f"Listening on http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")

    ThreadingHTTPServer(
        (HOST, PORT),
        AgentHandler,
    ).serve_forever()

