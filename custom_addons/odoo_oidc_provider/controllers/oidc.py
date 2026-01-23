import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from odoo import http
from odoo.http import request

import jwt  # PyJWT
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# ---------------------------
# Helpers
# ---------------------------
def _now():
    return datetime.now(timezone.utc)

def _dt_to_odoo(dt):
    # Odoo stores naive UTC datetimes
    return dt.replace(tzinfo=None)

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

def _b64url_int(n: int) -> str:
    return _b64url(n.to_bytes((n.bit_length() + 7) // 8, "big"))

def _sha256_b64url(s: str) -> str:
    return _b64url(hashlib.sha256(s.encode("utf-8")).digest())

def _get_param(key: str, default=None):
    return request.env["ir.config_parameter"].sudo().get_param(key, default)

def _set_param(key: str, value: str):
    return request.env["ir.config_parameter"].sudo().set_param(key, value)

def _get_base_url():
    # Prefer your configured public base URL if you have reverse proxy
    return _get_param("web.base.url") or request.httprequest.host_url.rstrip("/")

def _issuer():
    # Issuer must exactly match discovery issuer
    return _get_param("oidc.issuer") or (f"{_get_base_url()}/oidc")

def _ensure_rsa_keys():
    pem = _get_param("oidc.private_key_pem")
    kid = _get_param("oidc.kid")
    if pem and kid:
        return pem, kid

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pem = pem_bytes.decode("utf-8")
    kid = secrets.token_urlsafe(16)

    _set_param("oidc.private_key_pem", pem)
    _set_param("oidc.kid", kid)
    return pem, kid

def _public_jwks():
    pem, kid = _ensure_rsa_keys()
    private_key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    pub = private_key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": _b64url_int(pub.n),
        "e": _b64url_int(pub.e),
    }
    return {"keys": [jwk]}

def _allowed_redirects():
    raw = _get_param("oidc.redirect_allowlist", "")
    # comma-separated exact matches
    return [x.strip() for x in raw.split(",") if x.strip()]

def _client_config():
    # For quick setup: single client.
    client_id = _get_param("oidc.client_id", "miniapps-client")
    client_secret = _get_param("oidc.client_secret", "")
    return client_id, client_secret

def _issue_id_token(user, client_id: str, nonce: str | None):
    pem, kid = _ensure_rsa_keys()
    now = _now()
    exp = now + timedelta(minutes=5)

    payload = {
        "iss": _issuer(),
        "sub": str(user.id),
        "aud": client_id,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "email": (user.login or "").lower(),
        "email_verified": True,
        "name": user.name or "",
    }
    if nonce:
        payload["nonce"] = nonce

    headers = {"kid": kid, "typ": "JWT", "alg": "RS256"}
    return jwt.encode(payload, pem, algorithm="RS256", headers=headers)

def _json_response(data, status=200):
    return request.make_response(
        json.dumps(data),
        headers=[("Content-Type", "application/json")],
        status=status,
    )

# ---------------------------
# OIDC Provider
# ---------------------------
class OidcProviderController(http.Controller):

    @http.route("/oidc/.well-known/openid-configuration", type="http", auth="public", csrf=False, methods=["GET"])
    def discovery(self, **kw):
        iss = _issuer()
        cfg = {
            "issuer": iss,
            "authorization_endpoint": f"{iss}/authorize",
            "token_endpoint": f"{iss}/token",
            "userinfo_endpoint": f"{iss}/userinfo",
            "jwks_uri": f"{iss}/jwks.json",
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "scopes_supported": ["openid", "email", "profile"],
            "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
            "code_challenge_methods_supported": ["S256"],
            "claims_supported": ["sub", "email", "email_verified", "name"],
        }
        return _json_response(cfg)

    @http.route("/oidc/jwks.json", type="http", auth="public", csrf=False, methods=["GET"])
    def jwks(self, **kw):
        return _json_response(_public_jwks())

    # AUTHORIZATION ENDPOINT (PKCE)
    @http.route("/oidc/authorize", type="http", auth="user", csrf=False, methods=["GET"])
    def authorize(self, **kw):
        # Required
        response_type = kw.get("response_type")
        client_id = kw.get("client_id")
        redirect_uri = kw.get("redirect_uri")
        state = kw.get("state")
        scope = kw.get("scope", "")
        code_challenge = kw.get("code_challenge")
        code_challenge_method = kw.get("code_challenge_method", "S256")
        nonce = kw.get("nonce")

        if response_type != "code":
            return request.make_response("unsupported response_type", status=400)
        if "openid" not in scope.split():
            return request.make_response("missing openid scope", status=400)
        if code_challenge_method != "S256" or not code_challenge:
            return request.make_response("PKCE required (S256)", status=400)

        expected_client_id, _ = _client_config()
        if client_id != expected_client_id:
            return request.make_response("invalid client_id", status=400)

        allowed = _allowed_redirects()
        if not redirect_uri or redirect_uri not in allowed:
            return request.make_response("redirect_uri not allowed", status=400)

        # Create one-time code
        code = secrets.token_urlsafe(32)
        expires_at = _now() + timedelta(minutes=2)

        request.env["oidc.auth.code"].sudo().create({
            "code": code,
            "user_id": request.env.user.id,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "nonce": nonce,
            "state": state,
            "expires_at": _dt_to_odoo(expires_at),
        })

        # Redirect back with code + state
        from werkzeug.urls import url_encode
        from werkzeug.utils import redirect

        params = {"code": code}
        if state:
            params["state"] = state
        sep = "&" if "?" in redirect_uri else "?"
        return redirect(redirect_uri + sep + url_encode(params))

    # TOKEN ENDPOINT
    @http.route("/oidc/token", type="http", auth="public", csrf=False, methods=["POST"])
    def token(self, **kw):
        grant_type = kw.get("grant_type")
        code = kw.get("code")
        redirect_uri = kw.get("redirect_uri")
        client_id = kw.get("client_id")
        client_secret = kw.get("client_secret")
        code_verifier = kw.get("code_verifier")

        if grant_type != "authorization_code":
            return _json_response({"error": "unsupported_grant_type"}, status=400)

        expected_client_id, expected_secret = _client_config()
        if client_id != expected_client_id:
            return _json_response({"error": "invalid_client"}, status=401)
        if expected_secret and client_secret != expected_secret:
            return _json_response({"error": "invalid_client"}, status=401)

        rec = request.env["oidc.auth.code"].sudo().search([("code", "=", code)], limit=1)
        if not rec:
            return _json_response({"error": "invalid_grant"}, status=400)
        if rec.used_at:
            return _json_response({"error": "invalid_grant", "error_description": "code already used"}, status=400)

        if redirect_uri != rec.redirect_uri:
            return _json_response({"error": "invalid_grant", "error_description": "redirect_uri mismatch"}, status=400)

        if not code_verifier:
            return _json_response({"error": "invalid_request", "error_description": "missing code_verifier"}, status=400)

        # Validate PKCE
        if _sha256_b64url(code_verifier) != rec.code_challenge:
            return _json_response({"error": "invalid_grant", "error_description": "PKCE verification failed"}, status=400)

        # Expiry
        if _now() > rec.expires_at.replace(tzinfo=timezone.utc):
            return _json_response({"error": "invalid_grant", "error_description": "code expired"}, status=400)

        user = rec.user_id
        id_token = _issue_id_token(user, rec.client_id, rec.nonce)

        # Issue access_token and store (optional but nice for /userinfo)
        access_token = secrets.token_urlsafe(32)
        access_exp = _now() + timedelta(minutes=10)
        request.env["oidc.access.token"].sudo().create({
            "token": access_token,
            "user_id": user.id,
            "client_id": rec.client_id,
            "expires_at": _dt_to_odoo(access_exp),
        })

        rec.sudo().write({"used_at": _dt_to_odoo(_now())})

        return _json_response({
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 600,
            "id_token": id_token,
            "scope": "openid email profile",
        })

    @http.route("/oidc/userinfo", type="http", auth="public", csrf=False, methods=["GET"])
    def userinfo(self, **kw):
        authz = request.httprequest.headers.get("Authorization", "")
        if not authz.startswith("Bearer "):
            return _json_response({"error": "invalid_request"}, status=401)
        token = authz.split(" ", 1)[1].strip()

        rec = request.env["oidc.access.token"].sudo().search([("token", "=", token)], limit=1)
        if not rec:
            return _json_response({"error": "invalid_token"}, status=401)
        if _now() > rec.expires_at.replace(tzinfo=timezone.utc):
            return _json_response({"error": "invalid_token", "error_description": "expired"}, status=401)

        user = rec.user_id
        return _json_response({
            "sub": str(user.id),
            "email": (user.login or "").lower(),
            "email_verified": True,
            "name": user.name or "",
        })
