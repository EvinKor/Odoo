# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class EventTicketController(http.Controller):

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
        if not reg.exists() or reg.partner_id.id != request.env.user.partner_id.id:
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

