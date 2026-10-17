"""Single Vercel entry point: no public application or static routes."""

import os
from urllib.parse import parse_qs, urlsplit

from quasar.access import SESSION_COOKIE, SESSION_TTL, TeamGate, access_page, safe_return_to
from quasar.server import Handler


class handler(Handler):
    def end_headers(self):
        self.send_header("Vary", "Cookie")
        self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        super().end_headers()

    def _respond(self, status, body, content_type="text/html; charset=utf-8", headers=()):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.close_connection = True
        return True

    def _authorized(self):
        # Cache the check because the hosted adapter can call both parse_request and do_*.
        if getattr(self, "_gate_checked", False):
            return getattr(self, "_gate_allowed", False)
        self._gate_checked = True
        # Never load a local .env or fail open. Cookies are accepted only when signed below.
        try:
            gate = TeamGate(os.environ.get("QUASAR_TEAM_PASSWORD", ""))
        except ValueError:
            self._gate_allowed = False
            self._respond(503, access_page(unavailable=True).encode("utf-8"))
            return False
        if self.command == "POST" and urlsplit(self.path).path == "/_team/access":
            self._gate_allowed = True
            return True
        self._gate_allowed = gate.allows_cookie_header(self.headers.get("Cookie", ""))
        if not self._gate_allowed:
            if self.command in ("GET", "HEAD"):
                body = access_page(return_to=self.path).encode("utf-8")
                self._respond(200, body)
            else:
                self._respond(401, b"Team sign-in required.\n", "text/plain; charset=utf-8")
        return self._gate_allowed

    def parse_request(self):
        return super().parse_request() and self._authorized()

    # Check inside methods too: hosted runtimes may dispatch methods directly.
    def do_GET(self):
        if self._authorized():
            super().do_GET()

    def do_POST(self):
        if self._authorized():
            if urlsplit(self.path).path == "/_team/access":
                self._team_login()
            else:
                super().do_POST()

    def do_HEAD(self):
        if self._authorized():
            super().do_GET()

    def _team_login(self):
        try:
            gate = TeamGate(os.environ.get("QUASAR_TEAM_PASSWORD", ""))
        except ValueError:
            self._respond(503, access_page(unavailable=True).encode("utf-8"))
            return
        if self.headers.get_content_type() != "application/x-www-form-urlencoded":
            self._respond(415, access_page(error="Use the sign-in form to continue.").encode("utf-8"))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= 4096:
            self._respond(400, access_page(error="Please enter your passphrase and try again.").encode("utf-8"))
            return
        fields = parse_qs(self.rfile.read(length).decode("utf-8", "replace"), keep_blank_values=True)
        password = fields.get("password", [""])[0]
        target = safe_return_to(fields.get("return_to", ["/"])[0])
        if not gate.allows_password(password):
            self._respond(401, access_page(return_to=target, error="That passphrase did not match. Try again.").encode("utf-8"))
            return
        token, _ = gate.issue_session()
        self._respond(303, b"", "text/plain; charset=utf-8", (
            ("Location", target),
            ("Set-Cookie", f"{SESSION_COOKIE}={token}; Path=/; Max-Age={SESSION_TTL}; HttpOnly; Secure; SameSite=Strict"),
        ))

    def _unsupported(self):
        if self._authorized():
            self._respond(405, b"Method not allowed.\n", "text/plain; charset=utf-8")

    do_OPTIONS = _unsupported
    do_PUT = _unsupported
    do_PATCH = _unsupported
    do_DELETE = _unsupported
    do_TRACE = _unsupported
    do_CONNECT = _unsupported
