# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class EventTicketController(http.Controller):
    def _get_ticket_report(self):
        report_xmlid = "event.action_report_event_registration_full_page_ticket"
        report_id = request.env["ir.model.data"].sudo()._xmlid_to_res_id(
            report_xmlid, raise_if_not_found=False
        )
        if not report_id:
            return False
        return request.env["ir.actions.report"].sudo().browse(report_id)

    def _registration_owner_domain(self):
        partner = request.env.user.partner_id
        user_email = (request.env.user.email or partner.email or '').strip()
        domain = [('partner_id', '=', partner.id)]
        if user_email:
            domain = ['|', ('partner_id', '=', partner.id), ('email', '=ilike', user_email)]
        return domain

    def _can_access_registration(self, registration):
        if not registration:
            return False
        partner = request.env.user.partner_id
        user_email = (request.env.user.email or partner.email or '').strip().lower()
        reg_email = (registration.email or '').strip().lower()
        return registration.partner_id.id == partner.id or (user_email and reg_email == user_email)

    def _self_check_registration(self, token=None, registration_id=None, mark_attended=False):
        """Validate a registration by token or id and optionally mark attendance."""
        Registration = request.env["event.registration"].sudo()
        registration = Registration.browse()
        if token and "x_ticket_token" in Registration._fields:
            registration = Registration.search([("x_ticket_token", "=", token)], limit=1)
        elif registration_id:
            registration = Registration.browse(int(registration_id))

        if not registration or not registration.exists():
            return None, "not_found"

        status = "already_checked_in" if registration.state == "done" else "pending"
        if mark_attended and registration.state != "done":
            registration.action_mark_attended()
            status = "checked_in"

        return registration, status

    @http.route(
        "/api/event/tickets",
        type="http",
        auth="public",
        website=True,
        csrf=False
    )
    def download_tickets_pdf(self, ids=None, tokens=None, **kw):
        ids_list = []
        if ids:
            ids_list = [int(x) for x in str(ids).split(",") if x.strip().isdigit()]
        if not ids_list:
            return request.not_found()

        regs = request.env["event.registration"].sudo().browse(ids_list).exists()
        if not regs:
            return request.not_found()

        tokens_list = []
        if tokens:
            tokens_list = [x for x in str(tokens).split(",")]

        # If token field exists, require matching token per registration
        has_token = "x_ticket_token" in regs._fields
        if has_token:
            if len(tokens_list) != len(regs):
                return request.make_response(
                    "Missing or invalid tokens",
                    headers=[("Content-Type", "text/plain; charset=utf-8")],
                    status=403,
                )
            for reg, token in zip(regs, tokens_list):
                if not reg.x_ticket_token or reg.x_ticket_token != token:
                    return request.make_response(
                        "Missing or invalid tokens",
                        headers=[("Content-Type", "text/plain; charset=utf-8")],
                        status=403,
                    )

        report = self._get_ticket_report()
        if not report:
            return request.make_response(
                "Ticket report not found",
                headers=[("Content-Type", "text/plain; charset=utf-8")],
            )

        pdf_bytes, _ = report.sudo()._render_qweb_pdf(
            report.report_name,
            res_ids=regs.ids,
        )

        filename = "tickets.pdf"
        headers = [
            ("Content-Type", "application/pdf"),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
        ]
        return request.make_response(pdf_bytes, headers=headers)

    @http.route(
        "/api/event/ticket/<int:registration_id>",
        type="http",
        auth="public",
        website=True,
        csrf=False
    )
    def download_ticket_pdf(self, registration_id, **kw):
        reg = request.env["event.registration"].sudo().browse(registration_id)
        if not reg.exists():
            return request.not_found()

        # ✅ Correct report XML ID (from your list)
        report = self._get_ticket_report()

        if not report:
            return request.make_response(
                "Ticket report not found",
                headers=[("Content-Type", "text/plain; charset=utf-8")],
            )

        pdf_bytes, _ = report.sudo()._render_qweb_pdf(
            report.report_name,
            res_ids=[registration_id],
        )

        filename = f"ticket_{registration_id}.pdf"
        headers = [
            ("Content-Type", "application/pdf"),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
        ]
        return request.make_response(pdf_bytes, headers=headers)

    @http.route(
        "/my/event-registration/<int:registration_id>/ticket",
        type="http",
        auth="user",
        website=True,
    )
    def download_ticket_pdf_portal(self, registration_id, **kw):
        reg = request.env["event.registration"].sudo().browse(registration_id)
        if not reg.exists() or not self._can_access_registration(reg):
            return request.redirect("/my/event-registrations")

        report = self._get_ticket_report()
        if not report:
            return request.make_response(
                "Ticket report not found",
                headers=[("Content-Type", "text/plain; charset=utf-8")],
            )

        pdf_bytes, _ = report.sudo()._render_qweb_pdf(
            report.report_name,
            res_ids=[registration_id],
        )
        filename = f"ticket_{registration_id}.pdf"
        headers = [
            ("Content-Type", "application/pdf"),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
        ]
        return request.make_response(pdf_bytes, headers=headers)

    @http.route(
        "/my/event-registrations/batch/<string:batch_id>/ticket",
        type="http",
        auth="user",
        website=True,
    )
    def download_ticket_pdf_batch_portal(self, batch_id, **kw):
        regs = request.env["event.registration"].sudo().search(
            [("x_register_batch_id", "=", batch_id)] + self._registration_owner_domain()
        )
        if not regs:
            return request.redirect("/my/event-registrations")

        report = self._get_ticket_report()
        if not report:
            return request.make_response(
                "Ticket report not found",
                headers=[("Content-Type", "text/plain; charset=utf-8")],
            )

        pdf_bytes, _ = report.sudo()._render_qweb_pdf(
            report.report_name,
            res_ids=regs.ids,
        )
        filename = f"tickets_{batch_id}.pdf"
        headers = [
            ("Content-Type", "application/pdf"),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
        ]
        return request.make_response(pdf_bytes, headers=headers)

    @http.route(
        "/event/registration/checkin/<string:token>",
        type="http",
        auth="public",
        website=True,
        csrf=False,
    )
    def checkin_registration(self, token, **kw):
        registration = request.env["event.registration"].sudo().search([
            ("x_ticket_token", "=", token)
        ], limit=1)
        if not registration:
            return request.render("event_application.registration_checkin_result", {
                "status": "invalid",
            })

        if registration.state != "done":
            registration.action_mark_attended()
            status = "checked_in"
        else:
            status = "already_checked_in"

        return request.render("event_application.registration_checkin_result", {
            "status": status,
            "registration": registration,
            "event": registration.event_id,
        })

    @http.route(
        "/api/event/ticket/self_check",
        type="json",
        auth="public",
        website=True,
        csrf=False,
    )
    def api_self_check_ticket(self, token=None, registration_id=None, mark_attended=True, **kw):
        """
        Public endpoint for kiosks/self-service scanners to validate ticket tokens.
        Parameters:
            token: external ticket token (preferred)
            registration_id: fallback lookup by registration id
            mark_attended: truthy/falsey flag to mark attendance (default True)
        """
        mark_attended_flag = str(mark_attended).lower() not in ("0", "false", "no", "off")
        registration, status = self._self_check_registration(
            token=token,
            registration_id=registration_id,
            mark_attended=mark_attended_flag,
        )
        if status == "not_found":
            return {"ok": False, "status": status, "message": "Ticket not found or invalid."}

        return {
            "ok": True,
            "status": status,
            "registration_id": registration.id,
            "attendee_name": registration.name,
            "attendee_email": registration.email,
            "event": {
                "id": registration.event_id.id,
                "name": registration.event_id.name,
            },
            "checked_in": status in ("checked_in", "already_checked_in"),
        }
