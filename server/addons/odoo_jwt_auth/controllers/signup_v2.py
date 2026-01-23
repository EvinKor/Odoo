# -*- coding: utf-8 -*-
import json
from odoo import http
from odoo.http import request

class SignupV2(http.Controller):

    @http.route("/api/public/signup_v2", type="http", auth="public", csrf=False, methods=["POST"])
    def signup_v2(self, **kw):
        payload = request.get_json_data(silent=True) or {}
        email = (payload.get("email") or "").strip().lower()
        full_name = (payload.get("fullName") or "").strip()

        resp = request.make_response(
            json.dumps({"ok": True, "email": email, "fullName": full_name}),
            headers=[("Content-Type","application/json")],
            status=200
        )
        resp.headers["X-SNABBB-SIGNUP"] = "v2"
        return resp
