"""Public Vercel app; source credentials and bridge authentication stay server-side."""
from quasar.server import Handler


class handler(Handler):
    def end_headers(self):
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        super().end_headers()

    def do_HEAD(self):
        super().do_GET()
