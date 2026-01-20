from odoo import models, fields, api
from odoo import http
from odoo.http import request
from supabase import create_client, Client
import os
import requests
import json
import jwt

# -----------------------------
# Config
# -----------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
ODOO_JWT_SECRET = os.environ.get("ODOO_JWT_SECRET")
ALGORITHM = "HS256"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
# -----------------------------
# Supabase Helper
# -----------------------------

class ResUsers(models.Model):
    _inherit = 'res.users'

    supabase_uid = fields.Char(index=True)

def supabase_get_user_by_email(email: str):
    if not supabase:
        return None # safety check
    res = supabase.auth.admin.list_users(per_page=1000)
    for u in res:
        if u.email and u.email.lower() == email.lower():
            odoo = {
		"id": u.id,
		"email": u.email,
		"role": getattr(u, "role", None),
		"confirmed_at": getattr(u, "confirmed_at", None).isoformat() if getattr(u, "confirmed_at", None) else None
    	    }

	    # profiles
            response = supabase.table("profiles").select("*").eq("email", u.email).execute()
            meta = supabase.table("inventory_meta").select("*").eq("user_id", u.id).execute()
            profiles_data = response.data
            meta_data = meta.data

            # inventory rooms
            response = supabase.table("inventory_rooms").select("id, name, pos_x, pos_y").eq("user_id", u.id).execute()
            rooms_data = response.data
            rooms_error = getattr(response, "error", None) 
            room_ids = [room["id"] for room in rooms_data]

            # invemtory items
            response = supabase.table("inventory_items").select("*, item_batches:inventory_item_batches(*)").in_("room_id", room_ids).execute()
            itemsData = response.data

            # inventory purchase history
            response = supabase.table("inventory_purchase_history").select("*").eq("user_id", u.id).order("occurred_at", desc=True).execute()
            history_data = response.data

            # inventory_activity_logs
            response = supabase.table("inventory_activity_logs").select("*").eq("user_id", u.id).order("created_at", desc=True).execute()
            logData = response.data

            return {"profiles": profiles_data, "meta": meta_data, "rooms": rooms_data, "rooms_error":rooms_error, "items_data":itemsData, "history_data":history_data, "log_data":logData}

    return None

def GetClinics():
    # appointment
    #get clinics
    response = supabase.table("clinics").select("*").order("created_at").execute()
    clinicsData=response.data


# -----------------------------
# JWT Helper
# -----------------------------
def verify_jwt(token):
    try:
        payload = jwt.decode(token, ODOO_JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return {"error": "Token expired"}
    except jwt.InvalidTokenError:
        return {"error": "Invalid token"}

# -----------------------------
# Odoo Controller
# -----------------------------
class SupabaseUserController(http.Controller):
    @http.route('/api/supabase/clinic', type='http', auth='none', csrf=False, methods=['GET'])
    def get_supabase_clinic(self, **kwargs):
        token = None
        auth_header = request.httprequest.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")  
        else:
            token = request.httprequest.cookies.get("access_token")
                
        if not token:
            return request.make_response(
                json.dumps({"error": "Authentication required"}),
                headers=[('Content-Type', 'application/json')]
            )
            
        # 2️⃣ Verify JWT
        payload = verify_jwt(token)
        if "error" in payload:
            return request.make_response(
                json.dumps({"error": payload["error"]}),
                headers=[('Content-Type', 'application/json')]
            )

        #get clinics
        response = supabase.table("clinics").select("*").order("created_at").execute()
        clinicsData=response.data 
       
        # 5️⃣ Return combined data
        return request.make_response(
            json.dumps({
                    "clinics":clinicsData
            }),
            headers=[('Content-Type', 'application/json')]
        )

    @http.route('/api/supabase/user', type='http', auth='none', csrf=False, methods=['GET'])
    def get_user(self, **kwargs):
        # 1️⃣ Get token from Authorization header or cookie
        token = None
        auth_header = request.httprequest.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
        else:
            token = request.httprequest.cookies.get("access_token")

        if not token:
            return request.make_response(
                json.dumps({"error": "Authentication required"}),
                headers=[('Content-Type', 'application/json')]
            )

        # 2️⃣ Verify JWT
        payload = verify_jwt(token)
        if "error" in payload:
            return request.make_response(
                json.dumps({"error": payload["error"]}),
                headers=[('Content-Type', 'application/json')]
            )

        # 3️⃣ Get Odoo user info
        uid = payload["uid"]
        user = request.env['res.users'].sudo().browse(uid)
        if not user.exists():
            return request.make_response(
                json.dumps({"error": "User not found"}),
                headers=[('Content-Type', 'application/json')]
            )

        # 4️⃣ Get Supabase profile
        profile = supabase_get_user_by_email(user.login)
        if not profile:
            return request.make_response(
                json.dumps({"error": "Supabase profile not found"}),
                headers=[('Content-Type', 'application/json')]
            )

        # 5️⃣ Return combined data
        return request.make_response(
            json.dumps({
                "odoo_user": {
                    "uid": uid,
                    "name": user.name,
                    "email": user.login,
                },
                "supabase_profile": profile
            }),
            headers=[('Content-Type', 'application/json')]
        )

