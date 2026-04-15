# -*- coding: utf-8 -*-
import base64
import secrets
from collections import Counter

from odoo import http
from odoo.http import request


# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class EventExternalRegisterController(http.Controller):
    def _get_points_wallet(self):
        if request.env.user._is_public():
            return False
        if "event.points.wallet" not in request.env:
            return False
        try:
            return request.env["event.points.wallet"].get_or_create_wallet(request.env.user.partner_id)
        except Exception:
            return False

    @http.route("/event/points/balance", type="json", auth="user", website=False, csrf=False)
    def event_points_balance(self):
        wallet = self._get_points_wallet()
        return {
            "balance": int(wallet.balance or 0) if wallet else 0,
        }

    @http.route("/api/event/register", type="json", auth="public", website=True, csrf=False)
    def api_event_register(self, **payload):
        """
        Expected JSON payload:
        {
          "event_id": 12,
          "ticket_id": 3,     # optional
          "tickets_qty": 4,
          "buyer": {
            "name": "Buyer Name",
            "email": "buyer@example.com",
            "phone": "+60..."
          },
          "ticket_names": ["A", "B", "C", "D"]
        }
        """
        if not payload:
            try:
                payload = request.httprequest.get_json(silent=True) or {}
            except Exception:
                payload = {}

        # --- Basic validation ---
        event_id = payload.get("event_id")
        tickets_qty = int(payload.get("tickets_qty") or 0)
        buyer = payload.get("buyer") or {}
        ticket_names = payload.get("ticket_names") or []
        ticket_id = payload.get("ticket_id")
        ticket_lines = payload.get("ticket_lines") or []

        if not event_id:
            return {"ok": False, "error": "Missing event_id"}

        buyer_name = (buyer.get("name") or "").strip()
        buyer_email = (buyer.get("email") or "").strip()
        buyer_phone = (buyer.get("phone") or "").strip()
        if not buyer_name or not buyer_email:
            return {"ok": False, "error": "buyer name and email are required"}

        # --- Fetch event ---
        event = request.env["event.event"].sudo().browse(int(event_id))
        if not event.exists():
            return {"ok": False, "error": "Event not found"}

        # Optional: block unpublished events
        if hasattr(event, "website_published") and not event.website_published:
            return {"ok": False, "error": "Event is not published"}

        # --- Build registration entries, supporting multiple ticket lines ---
        registration_entries = []  # [{"ticket_id": int or 0, "name": "Attendee Name"}]
        if ticket_lines:
            for line in ticket_lines:
                line_ticket_id = int(line.get("ticket_id") or 0)
                line_qty = int(line.get("qty") or 0)
                line_names = line.get("ticket_names") or []
                if not line_ticket_id or not line_qty:
                    return {"ok": False, "error": "Each ticket line requires ticket_id and qty"}
                if len(line_names) != line_qty:
                    return {"ok": False, "error": "ticket_names must match qty for each ticket line"}
                ticket = request.env["event.event.ticket"].sudo().browse(line_ticket_id)
                if not ticket.exists() or ticket.event_id.id != event.id:
                    return {"ok": False, "error": "Invalid ticket_id in ticket_lines"}
                for tname in line_names:
                    name = (tname or "").strip()
                    if not name:
                        return {"ok": False, "error": "Each ticket name is required"}
                    registration_entries.append({"ticket_id": line_ticket_id, "name": name})
        else:
            # Backward compatibility: single ticket_id + tickets_qty + ticket_names
            if not tickets_qty:
                return {"ok": False, "error": "Missing tickets_qty"}
            if not ticket_names:
                return {"ok": False, "error": "ticket_names is required"}
            if len(ticket_names) != tickets_qty:
                return {"ok": False, "error": "ticket_names must match tickets_qty"}
            if ticket_id:
                ticket = request.env["event.event.ticket"].sudo().browse(int(ticket_id))
                if not ticket.exists() or ticket.event_id.id != event.id:
                    return {"ok": False, "error": "Invalid ticket_id for this event"}
            for tname in ticket_names:
                name = (tname or "").strip()
                if not name:
                    return {"ok": False, "error": "Each ticket name is required"}
                registration_entries.append({"ticket_id": int(ticket_id) if ticket_id else 0, "name": name})

        # --- Resolve buyer partner (by email) ---
        user = request.env.user
        partner = request.env["res.partner"].sudo().search([
            ("email", "=", buyer_email)
        ], limit=1)
        if not partner:
            partner = request.env["res.partner"].sudo().create({
                "name": buyer_name,
                "email": buyer_email,
                "phone": buyer_phone,
            })
        else:
            partner.write({
                "name": buyer_name or partner.name,
                "phone": buyer_phone or partner.phone,
            })

        # --- Seat availability + point deduction for selected tickets ---
        registration_tickets = Counter(entry["ticket_id"] for entry in registration_entries if entry["ticket_id"])
        event_tickets = request.env["event.event.ticket"].sudo().browse(list(registration_tickets.keys()))
        if any(t.seats_limited and t.seats_available < registration_tickets.get(t.id, 0) for t in event_tickets):
            return {"ok": False, "error": "Insufficient seats for selected ticket(s)"}

        points_by_ticket = {}
        if "point_cost" in request.env["event.event.ticket"]._fields:
            points_by_ticket = {t.id: int(t.point_cost or 0) for t in event_tickets}
            total_points = sum(points_by_ticket.get(tid, 0) * qty for tid, qty in registration_tickets.items())
            wallet = self._get_points_wallet()
            if total_points > 0 and wallet:
                wallet.spend_points(total_points, "API event registration purchase", reference=event.name)

        # --- Create registrations (one per ticket entry) ---
        batch_id = secrets.token_urlsafe(12)
        EventRegistration = request.env["event.registration"].sudo()
        created = EventRegistration.browse()
        has_batch_id = "x_register_batch_id" in EventRegistration._fields
        has_token = "x_ticket_token" in EventRegistration._fields
        for entry in registration_entries:
            vals = {
                "event_id": event.id,
                "name": entry["name"],
                "email": buyer_email,
                "phone": buyer_phone,
            }
            if has_batch_id:
                vals["x_register_batch_id"] = batch_id
            if entry["ticket_id"]:
                vals["event_ticket_id"] = entry["ticket_id"]
            vals["partner_id"] = partner.id
            if "points_spent" in EventRegistration._fields and entry["ticket_id"]:
                vals["points_spent"] = points_by_ticket.get(entry["ticket_id"], 0)

            created |= EventRegistration.create(vals)

        base = request.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        tokens = []
        if has_token:
            for reg in created:
                if not reg.x_ticket_token:
                    reg.sudo().write({"x_ticket_token": secrets.token_urlsafe(24)})
                tokens.append(reg.x_ticket_token or "")

        combined_url = ""
        if created.ids:
            ids_param = ",".join(map(str, created.ids))
            tokens_param = ",".join(tokens) if tokens else ""
            combined_url = f"{base}/api/event/tickets?ids={ids_param}"
            if tokens_param:
                combined_url += f"&tokens={tokens_param}"
            report_xmlid = "event.action_report_event_registration_full_page_ticket"
            report_id = request.env["ir.model.data"].sudo()._xmlid_to_res_id(
                report_xmlid, raise_if_not_found=False
            )
            report = request.env["ir.actions.report"].sudo().browse(report_id) if report_id else False
            if report:
                report = report.sudo()
                pdf_bytes, _ = report._render_qweb_pdf(
                    report.report_name,
                    res_ids=created.ids,
                )
                filename = f"tickets_{batch_id}.pdf"
                request.env["ir.attachment"].sudo().create({
                    "name": filename,
                    "type": "binary",
                    "datas": base64.b64encode(pdf_bytes),
                    "mimetype": "application/pdf",
                    "res_model": "res.partner",
                    "res_id": partner.id,
                })

        return {
            "ok": True,
            "registration_ids": created.ids,
            "pdf_url_combined": combined_url,
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
