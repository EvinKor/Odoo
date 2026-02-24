from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request


class Ticket2UDentalWebsite(http.Controller):
    @http.route(["/dental/events"], type="http", auth="public", website=True)
    def dental_browse_events(self, **kwargs):
        domain = [
            ("dental_submission_id", "!=", False),
            "|",
            ("website_published", "=", True),
            ("is_published", "=", True),
        ]
        events = request.env["event.event"].sudo().search(domain, order="date_begin asc, id asc")
        point_balance = 0
        if request.env.user and not request.env.user._is_public():
            wallet = request.env["dental.points.wallet"].get_or_create_wallet(request.env.user.partner_id)
            point_balance = wallet.balance
        return request.render("ticket2u_dental_events.website_dental_browse_events", {
            "events": events,
            "point_balance": point_balance,
            "is_public_user": request.env.user._is_public(),
        })

    @http.route(["/dental/event/<int:event_id>/points-register"], type="http", auth="user", website=True, methods=["POST"], csrf=False)
    def points_register(self, event_id, **post):
        event = request.env["event.event"].sudo().browse(event_id)
        if not event.exists():
            return request.redirect("/event")

        ticket_id = int(post.get("ticket_id") or 0)
        ticket = request.env["event.event.ticket"].sudo().browse(ticket_id)
        if not ticket.exists() or ticket.event_id.id != event.id:
            return request.redirect("/event/%s" % event.id)

        partner = request.env.user.partner_id
        wallet = request.env["dental.points.wallet"].get_or_create_wallet(partner)

        qty = int(post.get("qty") or 1)
        point_cost = (ticket.point_cost or 0) * qty
        if point_cost <= 0:
            raise ValidationError(_("Point cost is not configured for this ticket."))

        wallet.spend_points(point_cost, _("Ticket purchase"), reference=event.name)

        for _i in range(qty):
            request.env["event.registration"].sudo().create({
                "event_id": event.id,
                "event_ticket_id": ticket.id,
                "name": partner.name,
                "email": partner.email,
                "phone": partner.phone,
                "partner_id": partner.id,
                "points_spent": ticket.point_cost,
                "ce_credits_earned": ticket.ce_credit_hours,
            })

        request.env["dental.notification"].sudo().create({
            "partner_id": partner.id,
            "title": _("Registration confirmed"),
            "message": _("You spent %s points for '%s'.") % (point_cost, event.name),
            "notification_type": "purchase",
            "action_url": "/my/dental/events",
        })
        return request.redirect("/my/dental/events")
