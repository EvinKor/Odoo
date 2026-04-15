# -*- coding: utf-8 -*-
import base64
import secrets
from collections import Counter

from odoo import http
from odoo.http import request


class EventReactApi(http.Controller):
    _TOKEN_PARAM = "event_react_api.token"

    def _json_ticket(self, ticket):
        ticket_fields = ticket._fields
        return {
            "id": ticket.id,
            "name": ticket.name,
            "point_cost": int(getattr(ticket, "point_cost", 0) or 0),
            "seats_available": ticket.seats_available if ticket.seats_limited else None,
            "seats_limited": bool(ticket.seats_limited),
            "start_sale": ticket.start_sale_datetime,
            "end_sale": ticket.end_sale_datetime,
        }

    def _json_event(self, event):
        # Use incoming host to avoid web.base.url mismatches (dev / port changes)
        base = request.httprequest.host_url.rstrip("/")

        # Always point to the model image; /web/image will serve a placeholder if empty.
        image_url = f"{base}/web/image/event.event/{event.id}/image_1920"
        thumb_url = f"{base}/web/image/event.event/{event.id}/image_512"
        api_url = f"{base}/api/app/events/{event.id}/image"
        thumb_api_url = f"{base}/api/app/events/{event.id}/thumb"

        # Data URI fallback for clients without cookie access to Odoo
        image_data = ""
        if hasattr(event, "image_512") and event.image_512:
            raw = event.image_512.decode() if isinstance(event.image_512, bytes) else event.image_512
            image_data = f"data:image/png;base64,{raw}"

        badge_url = ""
        badge_data = ""
        if hasattr(event, "badge_image") and event.badge_image:
            badge_url = f"{base}/web/image/event.event/{event.id}/badge_image"
            raw_badge = event.badge_image.decode() if isinstance(event.badge_image, bytes) else event.badge_image
            badge_data = f"data:image/png;base64,{raw_badge}"

        card_bg_url = ""
        card_bg_data = ""
        if hasattr(event, "card_bg_image") and event.card_bg_image:
            card_bg_url = f"{base}/web/image/event.event/{event.id}/card_bg_image"
            raw_card = event.card_bg_image.decode() if isinstance(event.card_bg_image, bytes) else event.card_bg_image
            card_bg_data = f"data:image/png;base64,{raw_card}"

        return {
            "id": event.id,
            "name": event.name,
            "date_begin": event.date_begin,
            "date_end": event.date_end,
            "location": event.full_address or event.venue_full_address or event.location,
            "image": image_url,
            "image_thumb": thumb_url,
            "image_api": api_url,
            "image_thumb_api": thumb_api_url,
            "image_data": image_data,
            "badge_image": badge_url,
            "badge_image_data": badge_data,
            "card_bg_image": card_bg_url,
            "card_bg_image_data": card_bg_data,
            "tickets": [self._json_ticket(t) for t in event.event_ticket_ids],
        }

    @http.route("/api/app/events/<int:event_id>/image", type="http", auth="public", csrf=False)
    def app_event_image(self, event_id, **kwargs):
        """Serve the event image without requiring session cookies (for React fetch)."""
        try:
            event = request.env["event.event"].sudo().browse(event_id)
            if not event.exists() or not (event.website_published or event.is_published):
                return request.make_response("Not Found", status=404)

            # Look for any available image field on the model, highest resolution first.
            img_b64 = None
            for field in ("card_bg_image", "badge_image", "image_1920", "image", "image_1024", "image_512", "image_medium", "image_small"):
                if hasattr(event, field):
                    val = getattr(event, field)
                    if val:
                        img_b64 = val
                        break

            if not img_b64:
                return request.make_response("", status=204)

            # Field may already be a base64 string or bytes; ensure we decode safely.
            if isinstance(img_b64, bytes):
                img_b64 = img_b64.decode()

            binary = base64.b64decode(img_b64)

            headers = [
                ("Content-Type", "image/png"),
                ("Cache-Control", "public, max-age=3600"),
            ]
            return request.make_response(binary, headers=headers)
        except Exception as e:
            # Return the error in dev so we can see the root cause quickly.
            return request.make_response(f"Error: {e}", status=500)

    @http.route("/api/app/events/<int:event_id>/thumb", type="http", auth="public", csrf=False)
    def app_event_thumb(self, event_id, **kwargs):
        """Serve a small/thumbnail image for the event."""
        try:
            event = request.env["event.event"].sudo().browse(event_id)
            if not event.exists() or not (event.website_published or event.is_published):
                return request.make_response("Not Found", status=404)

            img_b64 = None
            for field in ("card_bg_image", "badge_image", "image_512", "image_256", "image_small", "image_1920", "image"):
                if hasattr(event, field):
                    val = getattr(event, field)
                    if val:
                        img_b64 = val
                        break

            if not img_b64:
                return request.make_response("", status=204)

            if isinstance(img_b64, bytes):
                img_b64 = img_b64.decode()
            binary = base64.b64decode(img_b64)

            headers = [
                ("Content-Type", "image/png"),
                ("Cache-Control", "public, max-age=1800"),
            ]
            return request.make_response(binary, headers=headers)
        except Exception as e:
            return request.make_response(f"Error: {e}", status=500)

    @http.route("/api/app/events/<int:event_id>/image/set", type="json", auth="public", csrf=False, cors="*")
    def app_event_image_set(self, event_id, **payload):
        """Update event images (cover, background, badge, thumbnail) via base64.

        Accepts keys:
        - image_base64: main image (stored on image_1920)
        - card_bg_base64: background/cover (stored on card_bg_image when available)
        - badge_base64: badge overlay (stored on badge_image when available)
        - thumb_base64: thumbnail (stored on image_512 when available)

        Security: requires a shared token stored in system parameter ``event_react_api.token``.
        """
        event = request.env["event.event"].sudo().browse(event_id)
        if not event.exists():
            return {"ok": False, "error": "event_not_found"}

        expected_token = request.env["ir.config_parameter"].sudo().get_param(self._TOKEN_PARAM)
        token = payload.get("token")
        if expected_token and token != expected_token:
            return {"ok": False, "error": "unauthorized"}

        to_write = {}
        errors = {}

        def validate(field_key, field_name):
            raw = (payload.get(field_key) or "").strip()
            if not raw:
                return
            value = raw.split(",", 1)[1] if "," in raw else raw
            try:
                base64.b64decode(value, validate=True)
            except Exception:
                errors[field_key] = "invalid_base64"
                return
            if field_name not in event._fields:
                errors[field_key] = "field_not_found"
                return
            to_write[field_name] = value

        validate("image_base64", "image_1920")
        validate("card_bg_base64", "card_bg_image")
        validate("badge_base64", "badge_image")
        validate("thumb_base64", "image_512")

        if errors and not to_write:
            return {"ok": False, "error": errors}
        if to_write:
            event.write(to_write)
        return {"ok": True, "written": list(to_write.keys()), "errors": errors}

    @http.route("/api/app/events", type="json", auth="public", csrf=False, cors="*")
    def app_events(self, **payload):
        domain = [
            "|",
            ("website_published", "=", True),
            ("is_published", "=", True),
        ]
        events = request.env["event.event"].sudo().search(domain, limit=50, order="date_begin asc, id asc")
        return {"ok": True, "events": [self._json_event(ev) for ev in events]}

    @http.route("/api/app/events/<int:event_id>", type="json", auth="public", csrf=False, cors="*")
    def app_event_detail(self, event_id, **payload):
        event = request.env["event.event"].sudo().browse(event_id)
        if not event.exists():
            return {"ok": False, "error": "event_not_found"}
        return {"ok": True, "event": self._json_event(event)}

    @http.route("/api/app/events/<int:event_id>/register", type="json", auth="public", csrf=False, cors="*")
    def app_register(self, event_id, **payload):
        event = request.env["event.event"].sudo().browse(event_id)
        if not event.exists():
            return {"ok": False, "error": "event_not_found"}

        buyer = payload.get("buyer") or {}
        tickets = payload.get("tickets") or []
        if not tickets:
            return {"ok": False, "error": "tickets_required"}

        buyer_name = (buyer.get("name") or "").strip()
        buyer_email = (buyer.get("email") or "").strip()
        buyer_phone = (buyer.get("phone") or "").strip()
        if not buyer_name or not buyer_email:
            return {"ok": False, "error": "buyer_name_email_required"}

        partner = request.env["res.partner"].sudo().search([("email", "=", buyer_email)], limit=1)
        if not partner:
            partner = request.env["res.partner"].sudo().create({
                "name": buyer_name,
                "email": buyer_email,
                "phone": buyer_phone,
            })
        else:
            partner.write({"name": buyer_name or partner.name, "phone": buyer_phone or partner.phone})

        # Validate seats per ticket
        registration_tickets = Counter()
        ticket_model = request.env["event.event.ticket"].sudo()
        for line in tickets:
            tid = int(line.get("ticket_id") or 0)
            qty = int(line.get("qty") or 0)
            if not tid or qty <= 0:
                return {"ok": False, "error": "invalid_ticket_line"}
            ticket = ticket_model.browse(tid)
            if not ticket.exists() or ticket.event_id.id != event.id:
                return {"ok": False, "error": "ticket_not_for_event"}
            registration_tickets[tid] += qty

        event_tickets = ticket_model.browse(list(registration_tickets.keys()))
        if any(t.seats_limited and t.seats_available < registration_tickets.get(t.id, 0) for t in event_tickets):
            return {"ok": False, "error": "insufficient_seats"}

        batch_id = secrets.token_urlsafe(12)
        EventRegistration = request.env["event.registration"].sudo()
        has_batch = "x_register_batch_id" in EventRegistration._fields
        has_token = "x_ticket_token" in EventRegistration._fields
        created = EventRegistration.browse()

        for line in tickets:
            tid = int(line.get("ticket_id") or 0)
            qty = int(line.get("qty") or 0)
            attendee_names = line.get("names") or []
            if attendee_names and len(attendee_names) != qty:
                return {"ok": False, "error": "names_qty_mismatch"}
            for idx in range(qty):
                reg_vals = {
                    "event_id": event.id,
                    "partner_id": partner.id,
                    "name": (attendee_names[idx] if idx < len(attendee_names) else buyer_name) or partner.name,
                    "email": buyer_email,
                    "phone": buyer_phone,
                    "event_ticket_id": tid,
                }
                if has_batch:
                    reg_vals["x_register_batch_id"] = batch_id
                created |= EventRegistration.create(reg_vals)

        tokens = []
        if has_token:
            for reg in created:
                if not reg.x_ticket_token:
                    reg.sudo().write({"x_ticket_token": secrets.token_urlsafe(24)})
                tokens.append(reg.x_ticket_token)

        base = request.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        download_url = ""
        if created:
            ids_param = ",".join(map(str, created.ids))
            tokens_param = ",".join(tokens) if tokens else ""
            download_url = f"{base}/api/event/tickets?ids={ids_param}"
            if tokens_param:
                download_url += f"&tokens={tokens_param}"

        return {
            "ok": True,
            "registration_ids": created.ids,
            "batch_id": batch_id,
            "download_url": download_url,
        }

    @http.route("/api/app/registration/checkin", type="json", auth="public", csrf=False, cors="*")
    def app_checkin(self, **payload):
        token = payload.get("token")
        registration_id = payload.get("registration_id")
        Registration = request.env["event.registration"].sudo()
        reg = Registration.browse()
        if token and "x_ticket_token" in Registration._fields:
            reg = Registration.search([("x_ticket_token", "=", token)], limit=1)
        elif registration_id:
            reg = Registration.browse(int(registration_id))

        if not reg or not reg.exists():
            return {"ok": False, "status": "not_found"}

        if (reg.event_id.stage_id.name or "").strip().lower() == "cancelled":
            return {
                "ok": False,
                "status": "cancelled",
                "message": "This event has been cancelled. Check-in is unavailable.",
            }

        status = "already_checked_in"
        if reg.state != "done":
            reg.action_mark_attended()
            status = "checked_in"

        return {
            "ok": True,
            "status": status,
            "registration_id": reg.id,
            "event_id": reg.event_id.id,
            "attendee": {
                "name": reg.name,
                "email": reg.email,
                "ticket": reg.event_ticket_id.name,
            },
        }
