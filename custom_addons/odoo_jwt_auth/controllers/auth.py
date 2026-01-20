from odoo import http
from odoo.http import request
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

    @http.route('/api/auth/signup', type='http', auth='none', csrf=False, methods=['POST'])
    def signup(self, **kwargs):
        try:
            body = json.loads(request.httprequest.data or "{}")

            db = body.get("db")
            login = body.get("email")
            password = body.get("password")
            full_name = body.get("fullName")
            job_position = body.get("jobPosition")
            phone = body.get("phone")

            if not all([db, login, password, full_name]):
                return request.make_response(
                    json.dumps({"error": "Missing required fields"}),
                    headers=[('Content-Type', 'application/json')]
                )

            User = request.env['res.users'].sudo()

            if User.search([('login', '=', login)], limit=1):
                return request.make_response(
                    json.dumps({"error": "User with this email already exists"}),
                    headers=[('Content-Type', 'application/json')]
                )

            company = request.env['res.company'].sudo().search([], limit=1)
            if not company:
                return request.make_response(
                    json.dumps({"error": "No company found"}),
                    headers=[('Content-Type', 'application/json')]
                )

            group_user = request.env['res.groups'].sudo().search(
                [('name', '=', 'Internal User')],
                limit=1
            )

            if not group_user:
                return request.make_response(
                    json.dumps({"error": "Internal User group not found"}),
                    headers=[('Content-Type', 'application/json')]
                )

            new_user = User.create({
                'name': full_name,
                'login': login,
                'company_id': company.id,
                'groups_id': [(6, 0, [group_user.id])],
                'active': True,
                'share': False,
            })

            # IMPORTANT: hash password
            new_user._set_password(password)

            new_user.partner_id.sudo().write({
                'company_id': company.id,
                'function': job_position,
                'phone': phone,
            })

            payload = {
                "uid": new_user.id,
                "db": db,
                "iat": datetime.datetime.utcnow(),
                "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=TOKEN_EXP_MINUTES)
            }
            token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

            response = request.make_response(
                json.dumps({
                    "success": True,
                    "uid": new_user.id,
                    "name": new_user.name,
                    "email": new_user.login
                }),
                headers=[('Content-Type', 'application/json')]
            )

            response.set_cookie(
                key="access_token",
                value=token,
                httponly=True,
                secure=False,
                max_age=TOKEN_EXP_MINUTES * 60,
                path="/"
            )

            return response

        except Exception as e:
            return request.make_response(
                json.dumps({"error": str(e)}),
                headers=[('Content-Type', 'application/json')]
            )

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
