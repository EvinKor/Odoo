# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class EventExternalRegisterController(http.Controller):

    @http.route("/api/event/register", type="json", auth="public", website=True, csrf=False)
    def api_event_register(self, **payload):

        event_id = payload.get("event_id")
        attendees = payload.get("attendees") or []
        ticket_id = payload.get("ticket_id")
        tickets_qty = int(payload.get("tickets_qty") or len(attendees) or 0)

        if not event_id:
            return {"ok": False, "error": "Missing event_id"}
        if tickets_qty <= 0:
            return {"ok": False, "error": "tickets_qty must be > 0"}
        if len(attendees) != tickets_qty:
            return {"ok": False, "error": "attendees length must match tickets_qty"}

        event = request.env["event.event"].sudo().browse(int(event_id))
        if not event.exists():
            return {"ok": False, "error": "Event not found"}

        created = request.env["event.registration"]
        for a in attendees:
            name = (a.get("name") or "").strip()
            email = (a.get("email") or "").strip()
            phone = (a.get("phone") or "").strip()

            if not name or not email:
                return {"ok": False, "error": "Each attendee requires name and email"}

            vals = {"event_id": event.id, "name": name, "email": email, "phone": phone}
            if ticket_id:
                vals["event_ticket_id"] = int(ticket_id)

            created += request.env["event.registration"].sudo().create(vals)

        base = request.env["ir.config_parameter"].sudo().get_param("web.base.url", "")

        tickets = []
        for reg in created:
            # ensure token exists
            if not reg.x_ticket_token:
                reg.sudo().write({"x_ticket_token": reg.x_ticket_token})

            tickets.append({
                "id": reg.id,
                "pdf_url": f"{base}/api/event/ticket/{reg.id}?token={reg.x_ticket_token}",
            })

        return {
            "ok": True,
            "registration_ids": created.ids,
            "tickets": tickets,
        }

    @http.route("/api/event/register", type="json", auth="public", website=True, csrf=False)
    def api_event_register(self, **payload):
        """
        Expected JSON payload:
        {
          "event_id": 12,
          "ticket_id": 3,     # optional
          "tickets_qty": 2,
          "attendees": [
            {"name":"A", "email":"a@x.com", "phone":"+60..."},
            {"name":"B", "email":"b@x.com", "phone":"+60..."}
          ]
        }
        """

        # --- Basic validation ---
        event_id = payload.get("event_id")
        attendees = payload.get("attendees") or []
        ticket_id = payload.get("ticket_id")
        tickets_qty = int(payload.get("tickets_qty") or len(attendees) or 0)

        if not event_id:
            return {"ok": False, "error": "Missing event_id"}
        if tickets_qty <= 0:
            return {"ok": False, "error": "tickets_qty must be > 0"}
        if len(attendees) != tickets_qty:
            return {"ok": False, "error": "attendees length must match tickets_qty"}

        # --- Fetch event ---
        event = request.env["event.event"].sudo().browse(int(event_id))
        if not event.exists():
            return {"ok": False, "error": "Event not found"}

        # Optional: block unpublished events
        if hasattr(event, "website_published") and not event.website_published:
            return {"ok": False, "error": "Event is not published"}

        # --- Create registrations ---
        created_ids = []
        for a in attendees:
            name = (a.get("name") or "").strip()
            email = (a.get("email") or "").strip()
            phone = (a.get("phone") or "").strip()

            if not name or not email:
                return {"ok": False, "error": "Each attendee requires name and email"}

            vals = {
                "event_id": event.id,
                "name": name,
                "email": email,
                "phone": phone,
            }

            if ticket_id:
                vals["event_ticket_id"] = int(ticket_id)

            reg = request.env["event.registration"].sudo().create(vals)
            created_ids.append(reg.id)

        # --- Build tickets_url AFTER creation ---
        tickets_url = False
        if created_ids:
            base = request.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
            ids_str = "[" + ",".join(str(i) for i in created_ids) + "]"

            reg0 = request.env["event.registration"].sudo().browse(created_ids[0])

            # Try common token/hash field names
            tickets_hash = (
                getattr(reg0, "tickets_hash", False)
                or getattr(reg0, "access_token", False)
                or getattr(reg0, "ticket_hash", False)
                or getattr(reg0, "website_ticket_hash", False)
                or False
            )

            if tickets_hash:
                tickets_url = f"{base}/event/{event.id}/my_tickets?registration_ids={ids_str}&tickets_hash={tickets_hash}"

        return {
            "ok": True,
            "registration_ids": created_ids,
            "tickets_url": tickets_url,
        }

    @http.route("/api/debug/reg/<int:rid>", type="json", auth="public", csrf=False)
    def debug_reg(self, rid, **kw):
        reg = request.env["event.registration"].sudo().browse(rid)
        if not reg.exists():
            return {"ok": False, "error": "not found"}

        hits = {}
        for fname in reg._fields:
            if "hash" in fname or "token" in fname or "access" in fname:
                try:
                    hits[fname] = reg[fname]
                except Exception:
                    hits[fname] = "error_reading"

        return {"ok": True, "candidates": hits}
