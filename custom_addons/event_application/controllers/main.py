# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class EventExternalRegisterController(http.Controller):

    @http.route("/api/event/register", type="json", auth="public", website=True, csrf=False)
    def api_event_register(self, **payload):
        """
        Expected JSON payload:
        {
          "event_id": 12,
          "ticket_id": 3,     # optional (if you use event.event.ticket)
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

            # If your Odoo uses tickets (event.event.ticket), set it
            if ticket_id:
                vals["event_ticket_id"] = int(ticket_id)

            reg = request.env["event.registration"].sudo().create(vals)
            created_ids.append(reg.id)

        return {"ok": True, "registration_ids": created_ids}
