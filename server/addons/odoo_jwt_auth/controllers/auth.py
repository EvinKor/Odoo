from odoo import http
from odoo.http import request
from odoo.exceptions import UserError
import jwt
import datetime
import os
import json

# Load secret from environment or fallback
SECRET_KEY = os.environ.get("ODOO_JWT_SECRET")
ALGORITHM = "HS256"
TOKEN_EXP_MINUTES = 60

class AuthJWT(http.Controller):

    @http.route('/api/auth/login', type='http', auth='none', csrf=False, methods=['POST'])
    def login(self, **kwargs):
        try:
            # Parse incoming JSON
            body = json.loads(request.httprequest.data or "{}")
            db = body.get("db")
            login = body.get("login")
            password = body.get("password")

            if not db or not login or not password:
                return request.make_response(
                    json.dumps({"error": "Missing credentials or database name"}),
                    headers=[('Content-Type', 'application/json')]
                )

            # Authenticate user
            uid = request.session.authenticate(db, login, password)
            if not uid:
                return request.make_response(
                    json.dumps({"error": "Authentication failed"}),
                    headers=[('Content-Type', 'application/json')]
                )

            # Create JWT payload
            payload = {
                "uid": uid,
                "db": db,
                "iat": datetime.datetime.utcnow(),
                "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=TOKEN_EXP_MINUTES)
            }

            # Encode JWT
            token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

            # Set JWT in HttpOnly cookie
            response = request.make_response(json.dumps({
                "message": "Logged in successfully",
                "expires_in": TOKEN_EXP_MINUTES * 60
            }), headers=[('Content-Type', 'application/json')])

            response.set_cookie(
                key="access_token",
                value=token,
                httponly=True,
                secure=False,  # True in production with HTTPS
                max_age=TOKEN_EXP_MINUTES * 60,
                path="/"
            )
            return response

        except Exception as e:
            # Catch all errors to avoid 500
            return request.make_response(
                json.dumps({"error": str(e)}),
                headers=[('Content-Type', 'application/json')]
            )

    @http.route('/api/auth/logout', type='http', auth='none', csrf=False, methods=['POST'])
    def logout(self, **kwargs):
        response = request.make_response(
            json.dumps({'success': True}),
            headers=[('Content-Type', 'application/json')]
        )

        # Clear session cookie
        response.set_cookie(
            key='access_token',
            value='',
            max_age=0,
            path='/',
            httponly=True
        )

        return response

class AuthSignup(http.Controller):

    @http.route("/api/auth/signup", type="http", auth="public", csrf=False, methods=["POST"])
    def post_signup(self, **kwargs):
        # Always detach from session
        try:
            request.session.logout()
        except Exception:
            pass

        payload = request.get_json_data(silent=True) or {}
        email = (payload.get("email") or "").strip().lower()
        name = (payload.get("name") or payload.get("fullName") or "").strip() or email.split("@")[0]

        if not email or "@" not in email:
            return request.make_response('{"ok":false,"error":"Invalid email"}', [("Content-Type","application/json")], 400)

        company = request.env["res.company"].sudo().search([], limit=1)

        # ✅ Use SUPERUSER with forced company for the ENTIRE logic
        env = request.env(user=1).sudo().with_context(
            allowed_company_ids=[company.id],
            force_company=company.id,
        ).with_company(company)

        Users = env["res.users"]

        if Users.search([("login", "=", email)], limit=1):
            return request.make_response('{"ok":false,"error":"Email already registered"}', [("Content-Type","application/json")], 409)

        portal_group = env.ref("base.group_portal")

        # Create user with the properly configured env
        user = Users.create({
            "name": name,
            "login": email,
            "email": email,
            "groups_id": [(4, portal_group.id)],
            "company_id": company.id,
            "company_ids": [(6, 0, [company.id])],
            "active": True,
        })

        partner = env["res.partner"].browse(user.partner_id.id)
        partner.signup_prepare()

        base_url = env["ir.config_parameter"].sudo().get_param("web.base.url")
        verify_url = f"{base_url}/web/signup?token={partner.signup_token}"

        # ✅ Get template from the same env
        template = env.ref("auth_signup.mail_template_user_signup_account_created", raise_if_not_found=False) \
               or env.ref("auth_signup.reset_password_email", raise_if_not_found=False)
        
        # ✅ Send mail using the same env context (no need to re-add context)
        if template:
         template.send_mail(
             user.id,
             force_send=True,
             email_values={"email_to": email},
         )

        # Return OK (don’t touch request.env anymore)
        resp = request.make_response(json.dumps({"ok": True}), headers=[("Content-Type","application/json")], status=200)
        resp.headers["X-SNABBB-SIGNUP"] = "v2"
        return resp
    
def verify_jwt(token):
    """Verify JWT token and return payload or error."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return {"error": "Token expired"}
    except jwt.InvalidTokenError:
        return {"error": "Invalid token"}

class ProtectedAPI(http.Controller):

    @http.route('/api/protected', type='http', auth='none', csrf=False, methods=['GET'])
    def protected(self, **kwargs):
        token = None

        # 1. Try Authorization header (curl, Postman, mobile)
        auth_header = request.httprequest.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")

        # 2. Fallback to HttpOnly cookie (browser)
        if not token:
            token = request.httprequest.cookies.get("access_token")

        if not token:
            return request.make_response(
                json.dumps({"error": "Authentication required"}),
                headers=[('Content-Type', 'application/json')]
            )

        payload = verify_jwt(token)
        if "error" in payload:
            return request.make_response(
                json.dumps({"error": payload["error"]}),
                headers=[('Content-Type', 'application/json')]
            )

        uid = payload["uid"]
        user = request.env['res.users'].sudo().browse(uid)

        return request.make_response(
            json.dumps({
                "loggedIn": True,
                "uid": uid,
                "name": user.name,
                "email": user.login,
            }),
            headers=[('Content-Type', 'application/json')]
        )
