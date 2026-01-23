# from odoo import models, fields, api
# from odoo import http
# from odoo.http import request
# from supabase import create_client, Client
# import os
# import requests
# import json
# import jwt
# import logging

# _logger = logging.getLogger(__name__)

# # -----------------------------
# # Config
# # -----------------------------
# SUPABASE_URL = os.environ.get("SUPABASE_URL")
# SUPABASE_ANON_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
# ODOO_JWT_SECRET = os.environ.get("ODOO_JWT_SECRET")
# ALGORITHM = "HS256"
# supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
# # -----------------------------
# # Supabase Helper
# # -----------------------------

# class ResUsers(models.Model):
#     _inherit = 'res.users'

#     supabase_uid = fields.Char(index=True)


# def get_supabase_admin() -> Client:
#     if not SUPABASE_URL or not SUPABASE_ANON_KEY:
#         raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
#     return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


# def get_or_create_supabase_auth_user(email: str, odoo_user_id: int, name: str = None, phone: str = None):
#     """
#     Returns a Supabase Auth user (admin) object.
#     Uses Admin API, so no password is required.
#     """
#     sb = get_supabase_admin()

#     # 1) Try get user by email
#     try:
#         res = sb.auth.admin.list_users(page=1, per_page=200)  # may need pagination in big systems
#         # list_users returns users list; we find matching email
#         found = None
#         for u in (res.users or []):
#             if (u.email or "").lower() == email.lower():
#                 found = u
#                 break
#         if found:
#             return found
#     except Exception:
#         _logger.exception("Supabase admin list_users failed (continuing to create_user)")

#     # 2) Create user (no password)
#     payload = {
#         "email": email,
#         "email_confirm": True,  # skip email confirm for SSO-provisioned users
#         "user_metadata": {
#             "odoo_user_id": odoo_user_id,
#             "name": name,
#             "created_via": "odoo_sso",
#         },
#     }
#     if phone:
#         payload["phone"] = phone

#     created = sb.auth.admin.create_user(payload)
#     return created.user


# def upsert_profile(user_id_uuid: str, email: str, name: str = None, phone: str = None, odoo_user_id: int = None):
#     """
#     Upsert into public.profiles where profiles.user_id is UUID (FK -> auth.users.id)
#     """
#     sb = get_supabase_admin()

#     data = {
#         "user_id": user_id_uuid,  # UUID string
#         "email": email,
#         "name": name,
#         "phone": phone,
#         "status": "active",
#     }
#     # optional: keep odoo_user_id too (even in option B, it's useful for debugging/joins)
#     if odoo_user_id is not None:
#         data["odoo_user_id"] = odoo_user_id

#     # on_conflict should target a UNIQUE constraint.
#     # Most setups have profiles.user_id as PRIMARY KEY/UNIQUE already.
#     resp = sb.table("profiles").upsert(data, on_conflict="user_id").execute()
#     return resp.data[0] if resp.data else None


# def ensure_supabase_identity_and_profile(odoo_user):
#     """
#     Main function you call from your controller after Odoo auth succeeds.
#     - ensures Supabase auth user exists
#     - ensures profiles row exists
#     Returns profile dict.
#     """
#     email = odoo_user.login  # ensure this is an email
#     name = odoo_user.name
#     phone = getattr(odoo_user, "phone", None)

#     auth_user = get_or_create_supabase_auth_user(
#         email=email,
#         odoo_user_id=odoo_user.id,
#         name=name,
#         phone=phone
#     )

#     # auth_user.id is UUID
#     profile = upsert_profile(
#         user_id_uuid=str(auth_user.id),
#         email=email,
#         name=name,
#         phone=phone,
#         odoo_user_id=odoo_user.id,
#     )
#     return {
#         "auth_user_id": str(auth_user.id),
#         "profile": profile,
#     }

# def supabase_get_user_by_email(email: str):
#     if not supabase:
#         return None # safety check
#     res = supabase.auth.admin.list_users(per_page=1000)
#     for u in res:
#         if u.email and u.email.lower() == email.lower():
#             odoo = {
# 		"id": u.id,
# 		"email": u.email,
# 		"role": getattr(u, "role", None),
# 		"confirmed_at": getattr(u, "confirmed_at", None).isoformat() if getattr(u, "confirmed_at", None) else None
#     	    }

# 	    # profiles
#             response = supabase.table("profiles").select("*").eq("email", u.email).execute()
#             meta = supabase.table("inventory_meta").select("*").eq("user_id", u.id).execute()
#             profiles_data = response.data
#             meta_data = meta.data

#             # inventory rooms
#             response = supabase.table("inventory_rooms").select("id, name, pos_x, pos_y").eq("user_id", u.id).execute()
#             rooms_data = response.data
#             rooms_error = getattr(response, "error", None) 
#             room_ids = [room["id"] for room in rooms_data]

#             # invemtory items
#             response = supabase.table("inventory_items").select("*, item_batches:inventory_item_batches(*)").in_("room_id", room_ids).execute()
#             itemsData = response.data

#             # inventory purchase history
#             response = supabase.table("inventory_purchase_history").select("*").eq("user_id", u.id).order("occurred_at", desc=True).execute()
#             history_data = response.data

#             # inventory_activity_logs
#             response = supabase.table("inventory_activity_logs").select("*").eq("user_id", u.id).order("created_at", desc=True).execute()
#             logData = response.data

#             return {"profiles": profiles_data, "meta": meta_data, "rooms": rooms_data, "rooms_error":rooms_error, "items_data":itemsData, "history_data":history_data, "log_data":logData}

#     return None

# def GetClinics():
#     # appointment
#     #get clinics
#     response = supabase.table("clinics").select("*").order("created_at").execute()
#     clinicsData=response.data


# # -----------------------------
# # JWT Helper
# # -----------------------------
# def verify_jwt(token):
#     try:
#         payload = jwt.decode(token, ODOO_JWT_SECRET, algorithms=[ALGORITHM])
#         return payload
#     except jwt.ExpiredSignatureError:
#         return {"error": "Token expired"}
#     except jwt.InvalidTokenError:
#         return {"error": "Invalid token"}

# # -----------------------------
# # Odoo Controller
# # -----------------------------
# class SupabaseUserController(http.Controller):
#     @http.route('/api/supabase/clinic', type='http', auth='none', csrf=False, methods=['GET'])
#     def get_supabase_clinic(self, **kwargs):
#         token = None
#         auth_header = request.httprequest.headers.get("Authorization")
#         if auth_header and auth_header.startswith("Bearer "):
#             token = auth_header.replace("Bearer ", "")  
#         else:
#             token = request.httprequest.cookies.get("access_token")
                
#         if not token:
#             return request.make_response(
#                 json.dumps({"error": "Authentication required"}),
#                 headers=[('Content-Type', 'application/json')]
#             )
            
#         # 2️⃣ Verify JWT
#         payload = verify_jwt(token)
#         if "error" in payload:
#             return request.make_response(
#                 json.dumps({"error": payload["error"]}),
#                 headers=[('Content-Type', 'application/json')]
#             )

#         #get clinics
#         response = supabase.table("clinics").select("*").order("created_at").execute()
#         clinicsData=response.data 
       
#         # 5️⃣ Return combined data
#         return request.make_response(
#             json.dumps({
#                     "clinics":clinicsData
#             }),
#             headers=[('Content-Type', 'application/json')]
#         )

#     @http.route('/api/supabase/user', type='http', auth='none', csrf=False, methods=['GET'])
#     def get_user(self, **kwargs):
#         # 1️⃣ Get token from Authorization header or cookie
#         token = None
#         auth_header = request.httprequest.headers.get("Authorization")
#         if auth_header and auth_header.startswith("Bearer "):
#             token = auth_header.replace("Bearer ", "")
#         else:
#             token = request.httprequest.cookies.get("access_token")

#         if not token:
#             return request.make_response(
#                 json.dumps({"error": "Authentication required"}),
#                 headers=[('Content-Type', 'application/json')]
#             )

#         # 2️⃣ Verify JWT
#         payload = verify_jwt(token)
#         if "error" in payload:
#             return request.make_response(
#                 json.dumps({"error": payload["error"]}),
#                 headers=[('Content-Type', 'application/json')]
#             )

#         # 3️⃣ Get Odoo user info
#         uid = payload["uid"]
#         user = request.env['res.users'].sudo().browse(uid)
#         if not user.exists():
#             return request.make_response(
#                 json.dumps({"error": "User not found"}),
#                 headers=[('Content-Type', 'application/json')]
#             )

#         # 4️⃣ Get Supabase profile
#         profile = supabase_get_user_by_email(user.login)
#         if not profile:
#             profile = supabase.table("profiles").insert({
#                 "user_id": uid,
#                 "email": user.login,
#                 "name": user.name,
#                 "phone": user.phone,
#             }).execute()
#         # if not profile:
#         #     return request.make_response(
#         #         json.dumps({"error": "Supabase profile not found created new user"}),
#         #         headers=[('Content-Type', 'application/json')]
#         #     )
        
#         profile = supabase.table("profiles").select("*").eq("email", user.login).maybe_single().execute()

#         # 5️⃣ Return combined data
#         return request.make_response(
#             json.dumps({
#                 "odoo_user": {
#                     "uid": uid,
#                     "name": user.name,
#                     "email": user.login,
#                 },
#                 "supabase_profile": profile
#             }),
#             headers=[('Content-Type', 'application/json')]
#         )

# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo import http
from odoo.http import request

from supabase import create_client, Client
import os
import json
import jwt
import logging

_logger = logging.getLogger(__name__)

# -----------------------------
# Config
# -----------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")  # service_role key
ODOO_JWT_SECRET = os.environ.get("ODOO_JWT_SECRET")

ALGORITHM = "HS256"

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    _logger.warning("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY env vars")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# -----------------------------
# Model extension
# -----------------------------
class ResUsers(models.Model):
    _inherit = "res.users"
    supabase_uid = fields.Char(index=True)


# -----------------------------
# Supabase Admin Helpers (Option B)
# -----------------------------
def get_supabase_admin() -> Client:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def get_or_create_supabase_auth_user(email: str, odoo_user_id: int, name: str = None, phone: str = None):
    """
    Create/find Supabase Auth user using Admin API (no password required).
    Returns the auth user object with .id (UUID).
    """
    sb = get_supabase_admin()

    # Try to find by email (simple approach for dev/small userbase)
    try:
        res = sb.auth.admin.list_users(page=1, per_page=200)
        found = None
        for u in (res.users or []):
            if (u.email or "").lower() == (email or "").lower():
                found = u
                break
        if found:
            return found
    except Exception:
        _logger.exception("Supabase admin list_users failed (continuing to create_user)")

    payload = {
        "email": email,
        "email_confirm": True,
        "user_metadata": {
            "odoo_user_id": odoo_user_id,
            "name": name,
            "created_via": "odoo_sso",
        },
    }
    if phone:
        payload["phone"] = phone

    created = sb.auth.admin.create_user(payload)
    return created.user


def upsert_profile(user_id_uuid: str, email: str, name: str = None, phone: str = None, odoo_user_id: int = None):
    """
    Upsert into public.profiles where profiles.user_id is UUID (FK -> auth.users.id).
    NOTE: profiles.user_id must be UNIQUE/PK for on_conflict="user_id" to work.
    """
    sb = get_supabase_admin()

    data = {
        "user_id": user_id_uuid,  # UUID string
        "email": email,
        "name": name,
        "phone": phone,
        "status": "active",
    }
    # Optional but useful even in Option B
    if odoo_user_id is not None:
        data["odoo_user_id"] = odoo_user_id

    resp = sb.table("profiles").upsert(data, on_conflict="user_id").execute()
    return resp.data[0] if resp.data else None


def ensure_supabase_identity_and_profile(odoo_user):
    """
    After Odoo auth succeeds, call this:
    - ensures Supabase auth user exists
    - ensures profiles row exists
    Returns dict with auth_user_id + profile row.
    """
    email = odoo_user.login
    name = odoo_user.name
    phone = getattr(odoo_user, "phone", None)

    auth_user = get_or_create_supabase_auth_user(
        email=email,
        odoo_user_id=odoo_user.id,
        name=name,
        phone=phone,
    )

    profile = upsert_profile(
        user_id_uuid=str(auth_user.id),
        email=email,
        name=name,
        phone=phone,
        odoo_user_id=odoo_user.id,
    )

    return {"auth_user_id": str(auth_user.id), "profile": profile}


def supabase_get_profile_by_email(email: str):
    """
    Reads ONLY the profile row. (No auth listing needed.)
    """
    if not supabase:
        return None
    resp = supabase.table("profiles").select("*").eq("email", email).maybe_single().execute()
    # profiles
    response = supabase.table("profiles").select("*").eq("email", email).maybe_single().execute()
    data = response.data
    _logger.info("Profile found email=%s user_id=%s", data.get("email"), data.get("user_id"))
    meta = supabase.table("inventory_meta").select("*").eq("user_id", data.get("user_id")).execute()
    profiles_data = response.data
    meta_data = meta.data  
    # inventory rooms
    response = supabase.table("inventory_rooms").select("id, name, pos_x, pos_y").eq("user_id", data.get("user_id")).execute()
    rooms_data = response.data
    rooms_error = getattr(response, "error", None) 
    room_ids = [room["id"] for room in rooms_data]  
    # invemtory items
    response = supabase.table("inventory_items").select("*, item_batches:inventory_item_batches(*)").in_("room_id", room_ids).execute()
    itemsData = response.data  
    # inventory purchase history
    response = supabase.table("inventory_purchase_history").select("*").eq("user_id", data.get("user_id")).order("occurred_at", desc=True).execute()
    history_data = response.data  
    # inventory_activity_logs
    response = supabase.table("inventory_activity_logs").select("*").eq("user_id", data.get("user_id")).order("created_at", desc=True).execute()
    logData = response.data  
    # settings data
    response = supabase.table("apt_settings").select("*").eq("clinic_id", data.get("clinic_id")).maybe_single().execute()
    setting_data = response.data
    return {"profiles": profiles_data,"setting_data": setting_data, "meta": meta_data, "rooms": rooms_data, "rooms_error":rooms_error, "items_data":itemsData, "history_data":history_data, "log_data":logData}


# -----------------------------
# JWT Helper
# -----------------------------
def verify_jwt(token: str):
    try:
        payload = jwt.decode(token, ODOO_JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return {"error": "Token expired"}
    except jwt.InvalidTokenError:
        return {"error": "Invalid token"}
    except Exception:
        _logger.exception("JWT verify failed")
        return {"error": "Invalid token"}


def _get_token_from_request():
    """
    Prefer Authorization: Bearer <token>, fallback to HttpOnly cookie 'access_token'
    """
    auth_header = request.httprequest.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return request.httprequest.cookies.get("access_token")


# -----------------------------
# Odoo Controller
# -----------------------------
class SupabaseUserController(http.Controller):

    @http.route("/api/supabase/clinic", type="http", auth="none", csrf=False, methods=["GET"])
    def get_supabase_clinic(self, **kwargs):
        token = _get_token_from_request()
        if not token:
            return request.make_response(
                json.dumps({"error": "Authentication required"}),
                headers=[("Content-Type", "application/json")],
                status=401,
            )

        payload = verify_jwt(token)
        if "error" in payload:
            return request.make_response(
                json.dumps({"error": payload["error"]}),
                headers=[("Content-Type", "application/json")],
                status=401,
            )

        response = supabase.table("clinics").select("*").order("created_at").execute()
        clinics_data = response.data or []

        return request.make_response(
            json.dumps({"clinics": clinics_data}),
            headers=[("Content-Type", "application/json")],
        )

    @http.route("/api/supabase/user", type="http", auth="none", csrf=False, methods=["GET"])
    def get_user(self, **kwargs):
        token = _get_token_from_request()
        if not token:
            return request.make_response(
                json.dumps({"error": "Authentication required"}),
                headers=[("Content-Type", "application/json")],
                status=401,
            )

        payload = verify_jwt(token)
        if "error" in payload:
            return request.make_response(
                json.dumps({"error": payload["error"]}),
                headers=[("Content-Type", "application/json")],
                status=401,
            )

        uid = payload.get("uid")
        if not uid:
            return request.make_response(
                json.dumps({"error": "Token missing uid"}),
                headers=[("Content-Type", "application/json")],
                status=401,
            )

        user = request.env["res.users"].sudo().browse(int(uid))
        if not user.exists():
            return request.make_response(
                json.dumps({"error": "User not found"}),
                headers=[("Content-Type", "application/json")],
                status=404,
            )

        # ✅ Option B: ensure Supabase Auth user (UUID) + profiles row (user_id UUID)
        try:
            ensured = ensure_supabase_identity_and_profile(user)
        except Exception:
            _logger.exception("Supabase provisioning failed for %s", user.login)
            ensured = None  # do not block login

        profile = supabase_get_profile_by_email(user.login)

        return request.make_response(
            json.dumps(
                {
                    "odoo_user": {"uid": user.id, "name": user.name, "email": user.login},
                    "supabase_auth_user_id": ensured["auth_user_id"] if ensured else None,
                    "supabase_profile": profile,
                    "provisioning_ok": bool(ensured),
                }
            ),
            headers=[("Content-Type", "application/json")],
        )

    # ✅ NEW ENDPOINT: inventory bootstrap (auto-provision on presence of access_token)
    @http.route("/api/inventory/bootstrap", type="http", auth="none", csrf=False, methods=["POST"])
    def inventory_bootstrap(self, **kwargs):
        """
        If access_token is present and valid:
        - identify Odoo user from JWT
        - ensure Supabase Auth user + profiles row exist
        - return minimal identity payload for inventory app
        """
        token = _get_token_from_request()
        if not token:
            return request.make_response(
                json.dumps({"ok": False, "error": "missing_access_token"}),
                headers=[("Content-Type", "application/json")],
                status=401,
            )

        payload = verify_jwt(token)
        if "error" in payload:
            return request.make_response(
                json.dumps({"ok": False, "error": payload["error"]}),
                headers=[("Content-Type", "application/json")],
                status=401,
            )

        uid = payload.get("uid")
        if not uid:
            return request.make_response(
                json.dumps({"ok": False, "error": "token_missing_uid"}),
                headers=[("Content-Type", "application/json")],
                status=401,
            )

        user = request.env["res.users"].sudo().browse(int(uid))
        if not user.exists():
            return request.make_response(
                json.dumps({"ok": False, "error": "odoo_user_not_found"}),
                headers=[("Content-Type", "application/json")],
                status=404,
            )

        try:
            ensured = ensure_supabase_identity_and_profile(user)
            profile = ensured["profile"]
            auth_user_id = ensured["auth_user_id"]
        except Exception:
            _logger.exception("Supabase provisioning failed for %s", user.login)
            return request.make_response(
                json.dumps({"ok": False, "error": "supabase_provision_failed"}),
                headers=[("Content-Type", "application/json")],
                status=500,
            )

        return request.make_response(
            json.dumps(
                {
                    "ok": True,
                    "odoo_user": {"uid": user.id, "email": user.login, "name": user.name},
                    "supabase_auth_user_id": auth_user_id,
                    "supabase_profile": profile,
                }
            ),
            headers=[("Content-Type", "application/json")],
        )
