import json
from odoo import http
from odoo.http import request

from ..supabase_helpers import (
    supabase_get_user_id_by_email,
    supabase_get_profile_by_user_id,
)
from ..jwt import verify_jwt   # your existing JWT verifier


class SupabaseAPI(http.Controller):

    @http.route(
        "/api/supabase/user",
        type="http",
        auth="none",
        csrf=False,
        methods=["GET"],
    )
    def get_user(self, **kwargs):

        # 1️⃣ Get token
        token = None
        auth_header = request.httprequest.headers.get("Authorization")

        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
        else:
            token = request.httprequest.cookies.get("access_token")

        if not token:
            return request.make_response(
                json.dumps({"error": "Authentication required"}),
                [("Content-Type", "application/json")],
                401,
            )

        # 2️⃣ Verify JWT
        payload = verify_jwt(token)
        if "error" in payload:
            return request.make_response(
                json.dumps({"error": payload["error"]}),
                [("Content-Type", "application/json")],
                401,
            )

        # 3️⃣ Odoo user
        uid = payload["uid"]
        user = request.env["res.users"].sudo().browse(uid)

        if not user.exists():
            return request.make_response(
                json.dumps({"error": "User not found"}),
                [("Content-Type", "application/json")],
                404,
            )

        # 4️⃣ Ensure Supabase UUID exists
        if not user.supabase_uid:
            supabase_uid = supabase_get_user_id_by_email(user.login)
            if not supabase_uid:
                return request.make_response(
                    json.dumps({"error": "Supabase user not found"}),
                    [("Content-Type", "application/json")],
                    404,
                )

            user.sudo().write({"supabase_uid": supabase_uid})

        # 5️⃣ Fetch Supabase profile
        profile = supabase_get_profile_by_user_id(user.supabase_uid)
        if not profile:
            return request.make_response(
                json.dumps({"error": "Supabase profile not found"}),
                [("Content-Type", "application/json")],
                404,
            )

        # 6️⃣ Response
        return request.make_response(
            json.dumps(
                {
                    "odoo_user": {
                        "uid": user.id,
                        "name": user.name,
                        "email": user.login,
                        "supabase_uid": user.supabase_uid,
                    },
                    "supabase_profile": profile,
                }
            ),
            [("Content-Type", "application/json")],
            200,
        )

