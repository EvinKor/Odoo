# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class EventTicketController(http.Controller):
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

        report = request.env.ref(
            "event.action_report_event_registration_full_page_ticket",
            raise_if_not_found=False,
        )
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
        report = request.env.ref(
            "event.action_report_event_registration_full_page_ticket",
            raise_if_not_found=False,
        )

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

        report = request.env.ref(
            "event.action_report_event_registration_full_page_ticket",
            raise_if_not_found=False,
        )
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

        report = request.env.ref(
            "event.action_report_event_registration_full_page_ticket",
            raise_if_not_found=False,
        )
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
