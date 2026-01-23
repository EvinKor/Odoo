from odoo import http
from odoo.http import request
from urllib.parse import urlparse, urlencode, urlunparse, parse_qs
import jwt
import datetime
import os
import json
import logging

_logger = logging.getLogger(__name__)

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
            _logger.exception(f"Signin failed: {e}")
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
            _logger.exception(f"Signin failed: {e}")
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

        response.set_cookie(
            key='access_token',
            value='',
            max_age=0,
            path='/',
            httponly=True
        )

        return response

    @http.route('/api/auth/redirect', type='http', auth='none', csrf=False, methods=['GET'])
    def auth_redirect(self, **kwargs):
        destination = kwargs.get("destination")

        if not destination:
            return request.make_response(
                json.dumps({"error": "Missing destination"}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # Whitelist allowed domains (add your allowed hosts here)
        allowed_hosts = ["localhost:3001", "localhost:3002", "192.168.0.149:3001", "192.168.0.149:3002", "192.168.0.149:8069"]


        try:
            parsed = urlparse(destination)
            if parsed.netloc not in allowed_hosts:
                return request.make_response(
                    json.dumps({"error": "Invalid destination"}),
                    headers=[('Content-Type', 'application/json')],
                    status=400
                )
        except Exception:
            return request.make_response(
                json.dumps({"error": "Invalid URL"}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # Read the HttpOnly cookie (server has access)
        token = request.httprequest.cookies.get("access_token")

        if not token:
            return request.make_response(
                json.dumps({"error": "Not authenticated"}),
                headers=[('Content-Type', 'application/json')],
                status=401
            )

        # Append token to destination URL
        query_params = parse_qs(parsed.query)
        query_params["token"] = [token]
        new_query = urlencode(query_params, doseq=True)
        redirect_url = urlunparse(parsed._replace(query=new_query))
        return request.redirect(redirect_url)

class AuthSignup(http.Controller):

    @http.route("/api/auth/signup", type="http", auth="none", csrf=False, methods=["POST"])
    def signup(self, **kwargs):
        try:
            # ---- Parse JSON safely (Odoo-compatible) ----
            body = json.loads(request.httprequest.data or "{}")

            login = (body.get("email") or "").strip().lower()
            full_name = (body.get("fullName") or "").strip()
            job_position = (body.get("jobPosition") or "").strip()
            phone = (body.get("phone") or "").strip()

            if not login or "@" not in login or not full_name or not phone:
                return request.make_response(
                    json.dumps({"ok": False, "error": "Missing required fields (email, fullName, phone)"}),
                    headers=[("Content-Type", "application/json")],
                    status=400,
                )

            # ---- Use SUPERUSER env correctly (NO sudo() on env, NO with_user()) ----
            # 1) Find a company as superuser
            company = request.env(user=1)["res.company"].search([], limit=1)
            if not company:
                return request.make_response(
                    json.dumps({"ok": False, "error": "No company found"}),
                    headers=[("Content-Type", "application/json")],
                    status=500,
                )

            # 2) Build ONE env and use it everywhere
            env = request.env(
                user=1,
                context=dict(
                    request.env.context,
                    allowed_company_ids=[company.id],
                    force_company=company.id,
                    company_id=company.id,  # helps in some setups
                ),
            )

            Users = env["res.users"]
            portal_group = env.ref("base.group_portal")

            # ---- Helper: base_url without sudo() ----
            base_url = env["ir.config_parameter"].get_param("web.base.url")

            # 1) If user already exists (same login)
            existing = Users.search([("login", "=", login)], limit=1)
            if existing:
                # If it's an internal user, block
                if not existing.share:
                    return request.make_response(
                        json.dumps({"ok": False, "error": "Email already used by a staff account"}),
                        headers=[("Content-Type", "application/json")],
                        status=409,
                    )

                # Ensure email is present (fixes "user has no email address")
                if not existing.email:
                    existing.write({"email": existing.login})

                # Ensure portal group + share flag + company fields are correct
                vals = {}
                if not existing.share:
                    vals["share"] = True
                if portal_group not in existing.groups_id:
                    vals["groups_id"] = [(6, 0, [portal_group.id])]
                if existing.company_id.id != company.id:
                    vals["company_id"] = company.id
                if company.id not in existing.company_ids.ids:
                    vals["company_ids"] = [(6, 0, [company.id])]

                if vals:
                    existing.write(vals)

                # Update partner data (optional)
                if existing.partner_id:
                    existing.partner_id.write({
                        "phone": phone,
                        "function": job_position or False,
                        "company_id": company.id,
                    })

                # Generate signup token + send set-password email
                partner = existing.partner_id
                # Make sure the user has an email
                if not existing.email:
                    existing.write({"email": existing.email})
                
                # This triggers Odoo's reset password email + /web/reset_password link
                existing.action_reset_password()
                # partner.signup_prepare()
                # signup_url = f"{base_url}/web/signup?token={partner.signup_token}"

                # _send_signup_email(env=env, user=existing, email_to=login, signup_url=signup_url)

                return request.make_response(
                    json.dumps({"ok": True, "message": "User already exists. Signup email sent."}),
                    headers=[("Content-Type", "application/json")],
                    status=200,
                )

            # 2) Create a portal user WITHOUT setting password (user sets via emailed link)
            new_user = Users.create({
                "name": full_name,
                "login": login,
                "email": login,
                "share": True,
                "groups_id": [(6, 0, [portal_group.id])],
                "company_id": company.id,
                "company_ids": [(6, 0, [company.id])],
                "active": True,
            })

            # Update linked contact details
            if new_user.partner_id:
                new_user.partner_id.write({
                    "phone": phone,
                    "function": job_position or False,
                    "company_id": company.id,
                })

            # Prepare signup token and send email
            partner = new_user.partner_id
            partner.signup_prepare()
            signup_url = f"{base_url}/web/signup?token={partner.signup_token}"

            _send_signup_email(env=env, user=new_user, email_to=login, signup_url=signup_url)

            return request.make_response(
                json.dumps({
                    "ok": True,
                    "message": "Portal user created. Signup email sent.",
                    # Optional debugging. Remove in production.
                    "signup_url": signup_url,
                }),
                headers=[("Content-Type", "application/json")],
                status=201,
            )

        except Exception as e:
            _logger.exception("Signup failed")
            return request.make_response(
                json.dumps({"ok": False, "error": str(e)}),
                headers=[("Content-Type", "application/json")],
                status=500,
            )


def _send_signup_email(env, user, email_to, signup_url):
    """
    Sends an email that lets the user set a password via /web/signup?token=...
    Uses standard Odoo templates if available, otherwise sends a basic fallback email.

    IMPORTANT:
    - We call template.sudo() because mail.template access is restricted for non-admins.
      (Even though we're using user=1, sudo() on recordset is safe and avoids ACL surprises.)
    """
    template = (
        env.ref("auth_signup.mail_template_user_signup_account_created", raise_if_not_found=False)
        or env.ref("auth_signup.reset_password_email", raise_if_not_found=False)
    )

    # if template:
    #     ctx = dict(env.context, signup_url=signup_url)
    #     template.sudo().with_context(ctx).send_mail(
    #         user.id,
    #         force_send=True,
    #         email_values={"email_to": email_to},
    #     )
    #     return

    # Fallback: direct email if templates are missing
    subject = "Finish setting up your account"
    body_html = f"""
        <p>Hello {user.name},</p>
        <p>Please click the link below to set your password and activate your account:</p>
        <p><a href="{signup_url}">{signup_url}</a></p>
        <p>If you did not request this, you can ignore this email.</p>
    """

    mail = env["mail.mail"].sudo().create({
        "subject": subject,
        "body_html": body_html,
        "email_to": email_to,
    })
    mail.send()

    # @http.route('/api/auth/signup', type='http', auth='none', csrf=False, methods=['POST'])
    # def signup(self, **kwargs):
    #     try:
    #         body = json.loads(request.httprequest.data or "{}")

    #         db = body.get("db")
    #         login = body.get("email")
    #         password = body.get("password")
    #         full_name = body.get("fullName")
    #         job_position = body.get("jobPosition")
    #         phone = body.get("phone")

    #         if not all([login, password, full_name, phone]):
    #             return request.make_response(
    #                 json.dumps({"error": "Missing required fields"}),
    #                 headers=[('Content-Type', 'application/json')]
    #             )

    #         User = request.env['res.users'].sudo()

    #         # if User.search([('login', '=', login)], limit=1):
    #         #     return request.make_response(
    #         #         json.dumps({"error": "User with this email already exists"}),
    #         #         headers=[('Content-Type', 'application/json')]
    #         #     )
            
    #         existing = User.search([('login', '=', login)], limit=1)
    #         if existing:
    #             if not existing.email:
    #              existing.sudo().write({"email": existing.login})
    #             existing.sudo().action_reset_password()
    #             if existing.share:
    #                 # portal user already exists → resend verification/reset
    #                 existing.partner_id.sudo().signup_prepare()
    #                 template = request.env.ref(
    #                     "auth_signup.mail_template_user_signup_account_created",
    #                     raise_if_not_found=False
    #                 ) or request.env.ref(
    #                     "auth_signup.reset_password_email",
    #                     raise_if_not_found=False
    #                 )
                
    #                 if not template:
    #                     return {"error": "No signup email template found"}

    #                 template.sudo().send_mail(
    #                     existing.id,
    #                     force_send=True,
    #                     email_values={"email_to": existing.login},
    #                 )
    #                 return request.make_response(
    #                     json.dumps({
    #                         "ok": True,
    #                         "message": "User already exists. Email sent."
    #                     }),
    #                     headers=[("Content-Type", "application/json")],
    #                     status=200,
    #                 )
    #             else:
    #                 # internal user → block
    #                 return {"error": "Email already used by staff account"}

    #         company = request.env['res.company'].sudo().search([], limit=1)
    #         if not company:
    #             return request.make_response(
    #                 json.dumps({"error": "No company found"}),
    #                 headers=[('Content-Type', 'application/json')]
    #             )

    #         # group_user = request.env['res.groups'].sudo().search(
    #         #     [('name', '=', 'Internal User')],
    #         #     limit=1
    #         # )

    #         group_portal = request.env.ref("base.group_portal")

    #         # if not group_portal:
    #         #     return request.make_response(
    #         #         json.dumps({"error": "Internal User group not found"}),
    #         #         headers=[('Content-Type', 'application/json')]
    #         #     )

    #         _logger.info("NEW USER group: %s", group_portal)

    #         new_user = User.create({
    #             'name': full_name,
    #             'login': login,
    #             'email': login,
    #             'company_id': company.id,
    #             'company_ids': [(6, 0, [company.id])],
    #             'groups_id': [(6, 0, [group_portal.id])],
    #             'active': True,
    #             'share': True,
    #         })


    #         # IMPORTANT: hash password
    #         # new_user._set_password(password)

    #         # new_user.partner_id.sudo().write({
    #         #     'company_id': company.id,
    #         #     'function': job_position,
    #         #     'phone': phone,
    #         # })

    #         payload = {
    #             "uid": new_user.id,
    #             "db": db,
    #             "iat": datetime.datetime.utcnow(),
    #             "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=TOKEN_EXP_MINUTES)
    #         }
    #         token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    #         response = request.make_response(
    #             json.dumps({
    #                 "success": True,
    #                 "uid": new_user.id,
    #                 "name": new_user.name,
    #                 "email": new_user.login
    #             }),
    #             headers=[('Content-Type', 'application/json')]
    #         )

    #         response.set_cookie(
    #             key="access_token",
    #             value=token,
    #             httponly=True,
    #             secure=False,
    #             max_age=TOKEN_EXP_MINUTES * 60,
    #             path="/"
    #         )

    #         return response

    #     except Exception as e:
    #         return request.make_response(
    #             json.dumps({"error": str(e)}),
    #             headers=[('Content-Type', 'application/json')]
    #         )

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
