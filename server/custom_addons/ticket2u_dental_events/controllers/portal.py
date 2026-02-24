import base64

from odoo import fields, http
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class Ticket2UDentalPortal(CustomerPortal):
    def _point_balance(self):
        partner = request.env.user.partner_id
        wallet = request.env["dental.points.wallet"].get_or_create_wallet(partner)
        return wallet.balance

    @http.route(["/my/dental/points/adjust"], type="http", auth="user", website=True, methods=["GET", "POST"], csrf=False)
    def portal_adjust_points(self, **post):
        """Testing helper: quickly add or subtract points for current user."""
        try:
            delta = int((post.get("delta") or request.params.get("delta") or 0))
        except (TypeError, ValueError):
            delta = 0
        redirect_url = (
            post.get("redirect_url")
            or request.params.get("redirect_url")
            or request.httprequest.referrer
            or "/my/dental/events"
        )
        if not isinstance(redirect_url, str) or not redirect_url.startswith("/"):
            redirect_url = "/my/dental/events"
        if redirect_url.startswith("/my/dental/points/adjust"):
            redirect_url = "/my/dental/events"
        if not delta:
            return request.redirect(redirect_url)

        partner = request.env.user.partner_id
        wallet = request.env["dental.points.wallet"].get_or_create_wallet(partner)
        if delta > 0:
            wallet.add_points(delta, "Testing adjustment (+)")
        else:
            try:
                wallet.spend_points(abs(delta), "Testing adjustment (-)")
            except ValidationError:
                pass
        return request.redirect(redirect_url)

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id
        values["dental_point_balance"] = self._point_balance()
        if "dental_submission_count" in counters:
            values["dental_submission_count"] = request.env["dental.event.submission"].search_count([
                ("organizer_partner_id", "=", partner.id)
            ])
        if "dental_notification_count" in counters:
            values["dental_notification_count"] = request.env["dental.notification"].search_count([
                ("partner_id", "=", partner.id),
                ("is_read", "=", False),
            ])
        return values

    @http.route(["/my/dental/events"], type="http", auth="user", website=True)
    def portal_dental_events(self, **kwargs):
        partner = request.env.user.partner_id
        submissions = request.env["dental.event.submission"].search([
            ("organizer_partner_id", "=", partner.id)
        ])
        published_events = request.env["event.event"].search([
            ("dental_submission_id.organizer_partner_id", "=", partner.id),
            "|",
            ("website_published", "=", True),
            ("is_published", "=", True),
        ])
        return request.render("ticket2u_dental_events.portal_my_dental_events", {
            "submissions": submissions,
            "published_events": published_events,
            "point_balance": self._point_balance(),
        })

    @http.route(["/my/dental/event/<int:event_id>"], type="http", auth="user", website=True)
    def portal_dental_event_detail(self, event_id, **kwargs):
        partner = request.env.user.partner_id
        event = request.env["event.event"].sudo().browse(event_id)
        if not event.exists() or event.dental_submission_id.organizer_partner_id.id != partner.id:
            return request.redirect("/my/dental/events")
        return request.render("ticket2u_dental_events.portal_dental_event_detail", {
            "event": event,
            "point_balance": self._point_balance(),
        })

    @http.route(["/my/dental/event/<int:event_id>/upload-media"], type="http", auth="user", website=True, methods=["POST"], csrf=False)
    def portal_dental_event_upload_media(self, event_id, **post):
        partner = request.env.user.partner_id
        event = request.env["event.event"].sudo().browse(event_id)
        if not event.exists() or event.dental_submission_id.organizer_partner_id.id != partner.id:
            return request.redirect("/my/dental/events")

        badge_file = request.httprequest.files.get("badge_image")
        if badge_file and badge_file.filename:
            event.write({"badge_image": base64.b64encode(badge_file.read())})

        upload_files = request.httprequest.files.getlist("gallery_images")
        for idx, img in enumerate(upload_files, start=1):
            if not img or not img.filename:
                continue
            media = request.env["dental.event.media"].sudo().create({
                "name": img.filename,
                "image": base64.b64encode(img.read()),
                "event_id": event.id,
                "sequence": 10 + idx,
            })
            has_header = False
            for fname in ("image_1920", "image_1024", "image_512", "image_256", "image"):
                if fname in event._fields and event[fname]:
                    has_header = True
                    break
            if not has_header:
                media.action_set_as_header()
        return request.redirect(f"/my/dental/event/{event.id}")

    @http.route(["/my/dental/event/media/<int:media_id>/set-header"], type="http", auth="user", website=True, methods=["POST"], csrf=False)
    def portal_dental_event_set_header(self, media_id, **post):
        media = request.env["dental.event.media"].sudo().browse(media_id)
        if not media.exists() or not media.event_id:
            return request.redirect("/my/dental/events")
        if media.event_id.dental_submission_id.organizer_partner_id.id != request.env.user.partner_id.id:
            return request.redirect("/my/dental/events")
        media.action_set_as_header()
        return request.redirect(f"/my/dental/event/{media.event_id.id}")

    @http.route(["/my/dental/points"], type="http", auth="user", website=True)
    def portal_dental_points(self, **kwargs):
        partner = request.env.user.partner_id
        wallet = request.env["dental.points.wallet"].get_or_create_wallet(partner)
        return request.render("ticket2u_dental_events.portal_my_dental_points", {
            "wallet": wallet,
            "transactions": wallet.transaction_ids,
            "point_balance": wallet.balance,
        })

    @http.route(["/my/dental/notifications"], type="http", auth="user", website=True)
    def portal_dental_notifications(self, **kwargs):
        notifications = request.env["dental.notification"].search([
            ("partner_id", "=", request.env.user.partner_id.id)
        ])
        return request.render("ticket2u_dental_events.portal_my_dental_notifications", {
            "notifications": notifications,
            "point_balance": self._point_balance(),
        })

    @http.route(["/my/dental/notifications/read/<int:notification_id>"], type="http", auth="user", website=True)
    def portal_mark_notification(self, notification_id, **kwargs):
        n = request.env["dental.notification"].browse(notification_id)
        if n.partner_id.id == request.env.user.partner_id.id:
            n.action_mark_read()
        return request.redirect("/my/dental/notifications")

    @http.route(["/dental/event/submit"], type="http", auth="user", website=True)
    def website_dental_submit_form(self, **kwargs):
        categories = request.env["dental.event.submission"]._get_category_selection()
        return request.render("ticket2u_dental_events.website_dental_submit_form", {
            "categories": categories,
            "point_balance": self._point_balance(),
        })

    @http.route(["/dental/event/submit/post"], type="http", auth="user", website=True, methods=["POST"], csrf=False)
    def website_dental_submit_post(self, **post):
        category = post.get("category")
        vals = {
            "name": post.get("name"),
            "category": category,
            "description": post.get("description"),
            "date_begin": post.get("date_begin") and (post.get("date_begin").replace("T", " ") + ":00"),
            "date_end": post.get("date_end") and (post.get("date_end").replace("T", " ") + ":00"),
            "venue_name": post.get("venue_name"),
            "venue_address": post.get("venue_address"),
            "city": post.get("city"),
            "state": post.get("state"),
            "country": post.get("country"),
            "badge_image": False,
            "speaker_name": post.get("speaker_name"),
            "speaker_credentials": post.get("speaker_credentials"),
            "speaker_topics": post.get("speaker_topics"),
            "ce_credits": float(post.get("ce_credits") or 0),
            "organizer_partner_id": request.env.user.partner_id.id,
        }

        event_image_file = request.httprequest.files.get("event_image")
        if event_image_file and event_image_file.filename:
            vals["image"] = base64.b64encode(event_image_file.read())

        badge_image_file = request.httprequest.files.get("badge_image")
        if badge_image_file and badge_image_file.filename:
            vals["badge_image"] = base64.b64encode(badge_image_file.read())

        submission = request.env["dental.event.submission"].create(vals)

        media_files = request.httprequest.files.getlist("gallery_images")
        for idx, img in enumerate(media_files, start=1):
            if not img or not img.filename:
                continue
            request.env["dental.event.media"].create({
                "name": img.filename,
                "image": base64.b64encode(img.read()),
                "submission_id": submission.id,
                "sequence": 10 + idx,
                "is_header": idx == 1,
            })

        request.env["dental.event.ticket.config"].create({
            "submission_id": submission.id,
            "name": post.get("ticket_name") or "General Admission",
            "price": float(post.get("ticket_price") or 0),
            "point_cost": int(post.get("ticket_point_cost") or 0),
            "quantity": int(post.get("ticket_quantity") or 1),
            "ce_credit_hours": float(post.get("ticket_ce") or 0),
        })

        submission.action_submit()
        return request.redirect("/my/dental/events")

