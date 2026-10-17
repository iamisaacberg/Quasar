"""Single Vercel entry point: no public application or static routes."""

import os

from quasar.access import TeamGate
from quasar.server import Handler


class handler(Handler):
    def end_headers(self):
        self.send_header("Vary", "Authorization")
        self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        super().end_headers()

    def _deny(self, status, message):
        body = message.encode("utf-8")
        self.send_response(status)
        if status == 401:
            self.send_header("WWW-Authenticate", 'Basic realm="Quasar team", charset="UTF-8"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.close_connection = True
        return False

    def _authorized(self):
        # Never load a local .env, accept query/cookie bypasses, or fail open.
        try:
            gate = TeamGate(os.environ.get("QUASAR_TEAM_PASSWORD", ""))
        except ValueError:
            return self._deny(503, "Team access is not configured.\n")
        credentials = self.headers.get_all("Authorization", [])
        if len(credentials) != 1 or not gate.allows(credentials[0]):
            return self._deny(401, "Team sign-in required.\n")
        return True

    def parse_request(self):
        return super().parse_request() and self._authorized()

    # Check inside methods too: hosted runtimes may dispatch methods directly.
    def do_GET(self):
        if self._authorized():
            super().do_GET()

    def do_POST(self):
        if self._authorized():
            super().do_POST()

    def do_HEAD(self):
        if self._authorized():
            super().do_GET()

    def _unsupported(self):
        if self._authorized():
            self._deny(405, "Method not allowed.\n")

    do_OPTIONS = _unsupported
    do_PUT = _unsupported
    do_PATCH = _unsupported
    do_DELETE = _unsupported
    do_TRACE = _unsupported
    do_CONNECT = _unsupported
