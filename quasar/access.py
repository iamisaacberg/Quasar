"""Shared password gate and short-lived browser sessions for team demos."""

import base64
import hashlib
import hmac
import secrets
import time
from http.cookies import CookieError, SimpleCookie
from urllib.parse import urlsplit

SESSION_COOKIE = "quasar_team_session"
SESSION_TTL = 12 * 60 * 60


class TeamGate:
    """Keep only a credential digest; never return credentials to the browser."""

    def __init__(self, password):
        if len(password.strip()) < 12 or len(password) > 256 or any(c in password for c in "\r\n\x00"):
            raise ValueError("Use a shared password of 12-256 characters without line breaks.")
        self.digest = hashlib.sha256(("team:" + password).encode("utf-8")).digest()

    def allows_password(self, password):
        if not isinstance(password, str) or len(password) > 256:
            return False
        candidate = hashlib.sha256(("team:" + password).encode("utf-8")).digest()
        return hmac.compare_digest(candidate, self.digest)

    def issue_session(self, now=None):
        expires = int(now if now is not None else time.time()) + SESSION_TTL
        nonce = secrets.token_urlsafe(12)
        payload = f"{expires}.{nonce}"
        signature = hmac.new(self.digest, payload.encode(), hashlib.sha256).digest()
        token = base64.urlsafe_b64encode(payload.encode() + b"." + signature).decode().rstrip("=")
        return token, expires

    def allows_session(self, token, now=None):
        if not token or len(token) > 256:
            return False
        try:
            raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
            if len(raw) < 34 or raw[-33:-32] != b".":
                return False
            payload, signature = raw[:-33], raw[-32:]
            expires_text, nonce = payload.decode("ascii").split(".", 1)
            expires = int(expires_text)
            if not nonce or expires < int(now if now is not None else time.time()):
                return False
        except (ValueError, UnicodeDecodeError):
            return False
        expected = hmac.new(self.digest, payload, hashlib.sha256).digest()
        return hmac.compare_digest(signature, expected)

    def allows_cookie_header(self, header):
        try:
            cookie = SimpleCookie()
            cookie.load(header or "")
            morsel = cookie.get(SESSION_COOKIE)
            return bool(morsel and self.allows_session(morsel.value))
        except CookieError:
            return False


def safe_return_to(value):
    """Keep login redirects on this origin and strip control characters."""
    if not isinstance(value, str) or len(value) > 2048 or not value.startswith("/") or value.startswith("//"):
        return "/"
    if "\\" in value or any(ord(char) < 32 for char in value):
        return "/"
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return "/"
    return value


def access_page(*, return_to="/", error="", unavailable=False):
    """Standalone, dependency-free sign-in page shown before any app assets load."""
    import html

    destination = html.escape(safe_return_to(return_to), quote=True)
    if unavailable:
        title = "Access is temporarily unavailable"
        message = "Team access has not been configured for this preview. Ask the workspace owner to finish setup."
        button = "Access unavailable"
    else:
        title = "Welcome to the team workspace"
        message = error or "Enter your shared team passphrase to continue to the Quasar workspace."
        button = "Open the workspace"
    disabled = " disabled" if unavailable else ""
    alert_class = " access-error" if error or unavailable else ""
    alert_role = "alert" if error or unavailable else "status"
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#071d2b"><meta name="robots" content="noindex,nofollow,noarchive">
<title>Quasar | Team access</title>
<style>
:root{{color-scheme:dark;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#071d2b;color:#f5fbfa;font-synthesis:none;text-rendering:optimizeLegibility}}
*{{box-sizing:border-box}}body{{min-height:100vh;margin:0;display:grid;place-items:center;padding:36px;background:radial-gradient(ellipse at 14% 16%,#124d59 0,transparent 35%),radial-gradient(ellipse at 88% 84%,#173d57 0,transparent 32%),#071d2b}}
.page{{width:min(1040px,100%);min-height:600px;display:grid;grid-template-columns:1.04fr .96fr;overflow:hidden;border:1px solid #24414d;border-radius:28px;background:#0d2736;box-shadow:0 32px 100px #020d1590}}
.story{{position:relative;display:flex;flex-direction:column;justify-content:space-between;min-height:600px;padding:42px 48px;overflow:hidden;background:linear-gradient(145deg,#105c64 0%,#0b4857 42%,#123247 100%)}}
.story:before,.story:after{{position:absolute;content:"";border:1px solid #a4e0d733;border-radius:50%;pointer-events:none}}
.story:before{{width:520px;height:520px;right:-275px;top:110px;box-shadow:0 0 0 34px #a4e0d710,0 0 0 70px #a4e0d70a}}
.story:after{{width:310px;height:310px;right:-110px;top:215px}}
.brand,.story-copy,.story-foot{{position:relative;z-index:1}}.brand{{display:flex;align-items:center;gap:12px;font-size:14px;font-weight:750;letter-spacing:.16em;text-transform:uppercase}}
.mark{{display:grid;place-items:center;width:38px;height:38px;border:1px solid #b7f0de66;border-radius:12px;background:#a1e6d522;color:#baf3dd;font-size:19px}}
.kicker{{margin:0 0 16px;color:#a9ded1;font-size:11px;font-weight:750;letter-spacing:.2em;text-transform:uppercase}}
h1{{max-width:430px;margin:0;font-size:clamp(38px,5.4vw,59px);line-height:1.02;letter-spacing:-.055em;font-weight:620}}
.story-copy>p:not(.kicker){{max-width:390px;margin:22px 0 0;color:#d2e7e3;font-size:15px;line-height:1.75}}
.county{{display:inline-flex;align-items:center;gap:10px;margin-top:34px;padding:11px 14px;border:1px solid #c5f1e633;border-radius:99px;background:#0b34444d;color:#e5f4ef;font-size:12px;letter-spacing:.02em}}
.county i{{display:block;width:7px;height:7px;border-radius:50%;background:#9ee8c8;box-shadow:0 0 12px #9ee8c8}}
.story-foot{{color:#b9d7d2;font-size:11px;line-height:1.7}}.story-foot strong{{display:block;margin-bottom:4px;color:#e6f7f0;font-size:12px}}
.login{{display:flex;flex-direction:column;justify-content:center;padding:54px clamp(30px,6vw,64px);background:linear-gradient(165deg,#102c3b,#0b202d)}}
.login-top{{margin-bottom:46px}}.eyebrow{{margin:0 0 13px;color:#7fc8b4;font-size:11px;font-weight:760;letter-spacing:.18em;text-transform:uppercase}}
h2{{margin:0;color:#f5fbfa;font-size:31px;line-height:1.16;letter-spacing:-.04em;font-weight:640}}
.intro{{margin:14px 0 0;color:#9cb3b7;font-size:14px;line-height:1.65}}
form{{display:grid;gap:13px}}label{{color:#dbe8e7;font-size:12px;font-weight:650}}input{{width:100%;height:52px;padding:0 15px;border:1px solid #31515c;border-radius:11px;outline:none;background:#091e2a;color:#f6fffb;font:inherit;font-size:15px;transition:border-color .18s,box-shadow .18s}}
input:focus{{border-color:#6ac3a8;box-shadow:0 0 0 3px #6ac3a82a}}input::placeholder{{color:#6e858a}}
button{{height:52px;margin-top:7px;border:0;border-radius:11px;background:linear-gradient(100deg,#8fe0c2,#70c8bb);color:#092a31;font:inherit;font-size:14px;font-weight:760;box-shadow:0 10px 28px #55bda42b;transition:transform .15s,filter .15s}}
button:hover:not(:disabled){{transform:translateY(-1px);filter:brightness(1.05)}}button:disabled{{opacity:.55}}
.alert{{min-height:22px;margin:0 0 5px;color:#91b7b5;font-size:12px;line-height:1.55}}.access-error{{color:#ffb1a7}}
.privacy{{display:flex;gap:11px;margin-top:32px;padding-top:22px;border-top:1px solid #24404a;color:#819b9f;font-size:11px;line-height:1.65}}
.shield{{flex:none;color:#83cdb5;font-size:15px}}.privacy strong{{display:block;color:#bdd1cf;font-size:11px}}
@media(max-width:720px){{body{{padding:18px}}.page{{max-width:490px;grid-template-columns:1fr;border-radius:22px}}.story{{min-height:280px;padding:27px 29px}}.story-copy{{margin:45px 0 8px}}h1{{font-size:40px}}.story-copy>p:not(.kicker){{display:none}}.county{{margin-top:18px}}.story-foot{{display:none}}.login{{padding:38px 29px 32px}}.login-top{{margin-bottom:30px}}}}
@media(prefers-reduced-motion:reduce){{*,*:before,*:after{{transition:none!important}}}}
</style>
</head>
<body><main class="page">
<section class="story" aria-label="Quasar project information">
<div class="brand"><span class="mark" aria-hidden="true">↗</span> Quasar</div>
<div class="story-copy"><p class="kicker">Flood intelligence workspace</p><h1>See the changing picture.</h1><p>A shared team preview for exploring Miami-Dade exercise scenarios, rainfall context, and the factors behind each estimate.</p><span class="county"><i aria-hidden="true"></i> Miami-Dade County <span aria-hidden="true">·</span> FIPS 12086</span></div>
<div class="story-foot"><strong>Built for the IBM Z Datathon</strong>Team preview · Private workspace</div>
</section>
<section class="login" aria-labelledby="access-title">
<div class="login-top"><p class="eyebrow">Team access</p><h2 id="access-title">{html.escape(title)}</h2><p class="intro">Quasar is a team preview. Use the shared passphrase provided by your workspace owner.</p></div>
<form action="/_team/access" method="post">
<input type="hidden" name="return_to" value="{destination}">
<p class="alert{alert_class}" role="{alert_role}" aria-live="polite">{html.escape(message)}</p>
<label for="team-password">Shared passphrase</label><input id="team-password" name="password" type="password" autocomplete="current-password" minlength="12" maxlength="256" placeholder="Enter your team passphrase" required{disabled}>
<button type="submit"{disabled}>{html.escape(button)} <span aria-hidden="true">→</span></button>
</form>
<div class="privacy"><span class="shield" aria-hidden="true">◆</span><div><strong>Private team preview</strong>Access is shared with your team. Estimates are illustrative and are not official alerts or safety guidance.</div></div>
</section></main></body></html>'''
