from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class DentalEventSubmission(models.Model):
    _name = "dental.event.submission"
    _description = "Dental Event Submission"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(required=True, tracking=True)
    organizer_partner_id = fields.Many2one("res.partner", required=True, default=lambda self: self.env.user.partner_id, tracking=True)
    organizer_user_id = fields.Many2one("res.users", default=lambda self: self.env.user, readonly=True)
    category = fields.Selection(selection="_get_category_selection", required=True, tracking=True)
    category_label = fields.Char(compute="_compute_labels")
    description = fields.Html()
    date_begin = fields.Datetime(required=True)
    date_end = fields.Datetime(required=True)
    venue_name = fields.Char()
    venue_address = fields.Char()
    city = fields.Char()
    state = fields.Char()
    country = fields.Char()
    image = fields.Binary()
    badge_image = fields.Binary()
    promo_material = fields.Binary()
    speaker_name = fields.Char()
    speaker_credentials = fields.Text()
    speaker_topics = fields.Text()
    ce_credits = fields.Float(default=0.0)

    status = fields.Selection([
        ("draft", "Draft"),
        ("pending_review", "Pending Review"),
        ("modification_requested", "Modification Requested"),
        ("approved_awaiting_payment", "Approved - Awaiting Payment"),
        ("published", "Published"),
        ("rejected", "Rejected"),
    ], default="draft", tracking=True, required=True)
    status_label = fields.Char(compute="_compute_labels")

    submission_point_cost = fields.Integer(default=lambda self: self._default_submission_cost(), required=True)
    spent_tx_id = fields.Many2one("dental.points.transaction", readonly=True)
    refund_tx_id = fields.Many2one("dental.points.transaction", readonly=True)
    rejection_reason = fields.Text()
    admin_note = fields.Text()
    payment_confirmed = fields.Boolean(default=False)
    event_id = fields.Many2one("event.event", readonly=True)
    media_ids = fields.One2many("dental.event.media", "submission_id", string="Submission Media")

    ticket_line_ids = fields.One2many("dental.event.ticket.config", "submission_id")

    @api.depends("category", "status")
    def _compute_labels(self):
        category_map = dict(self._get_category_selection())
        status_map = dict(self._fields["status"].selection)
        for rec in self:
            rec.category_label = category_map.get(rec.category, rec.category or "")
            rec.status_label = status_map.get(rec.status, rec.status or "")

    def _default_submission_cost(self):
        return int(self.env["ir.config_parameter"].sudo().get_param("ticket2u_dental_events.submission_cost", default="75"))

    @api.model
    def _get_category_selection(self):
        return [
            ("ce", "Continuing Education (CE) Courses"),
            ("conference", "Dental Conferences & Symposiums"),
            ("workshop", "Hands-On Workshops"),
            ("product", "Product Launches & Demonstrations"),
            ("practice", "Dental Practice Management Seminars"),
            ("clinical_case", "Clinical Case Presentations"),
            ("study_club", "Study Club Meetings"),
            ("implant", "Implant Training Sessions"),
            ("orthodontic", "Orthodontic Courses"),
            ("endodontic", "Endodontic Workshops"),
            ("periodontic", "Periodontics Seminars"),
            ("pediatric", "Pediatric Dentistry Events"),
            ("cosmetic", "Cosmetic Dentistry Masterclasses"),
            ("digital", "Digital Dentistry Training"),
            ("networking", "Practice Networking Events"),
        ]

    def _notify_partner(self, partner, title, message, ntype="system", action_url=None):
        self.env["dental.notification"].sudo().create({
            "partner_id": partner.id,
            "title": title,
            "message": message,
            "notification_type": ntype,
            "action_url": action_url,
        })

    def _notify_admins(self, title, message, ntype="system", action_url=None):
        admin_group = self.env.ref("base.group_system")
        partners = admin_group.users.mapped("partner_id")
        for partner in partners:
            self._notify_partner(partner, title, message, ntype=ntype, action_url=action_url)

    def action_submit(self):
        system_group = self.env.ref("base.group_system")
        for submission in self:
            if submission.status not in ("draft", "modification_requested"):
                continue
            if submission.date_end and submission.date_begin and submission.date_end < submission.date_begin:
                raise ValidationError(_("End date must be after start date."))
            if not submission.ticket_line_ids:
                raise ValidationError(_("Configure at least one ticket type before submission."))

            organizer_is_admin = bool(
                submission.organizer_user_id
                and system_group in submission.organizer_user_id.sudo().groups_id
            )
            current_user_is_admin = self.env.user.has_group("base.group_system")
            is_admin_submission = organizer_is_admin or current_user_is_admin

            # Admin submissions skip points and skip review.
            vals = {"status": "approved_awaiting_payment" if is_admin_submission else "pending_review"}
            if not is_admin_submission:
                wallet = self.env["dental.points.wallet"].get_or_create_wallet(submission.organizer_partner_id)
                tx = wallet.spend_points(
                    submission.submission_point_cost,
                    _("Event submission points"),
                    reference=submission.name,
                )
                vals["spent_tx_id"] = tx.id
            submission.write(vals)

            submission._notify_partner(
                submission.organizer_partner_id,
                _("Submission confirmed"),
                _("Your event '%s' has been submitted for review.") % submission.name,
                ntype="submission",
            )
            if not is_admin_submission:
                submission._notify_admins(
                    _("New dental event submission"),
                    _("New submission '%s' is awaiting review.") % submission.name,
                    ntype="submission",
                )

    def action_admin_approve(self):
        for submission in self:
            submission.write({"status": "approved_awaiting_payment"})
            submission._notify_partner(
                submission.organizer_partner_id,
                _("Event approved"),
                _("Your event '%s' was approved. Confirm payment to publish.") % submission.name,
                ntype="approval",
            )

    def action_request_modification(self):
        for submission in self:
            submission.write({"status": "modification_requested"})
            submission._notify_partner(
                submission.organizer_partner_id,
                _("Modification requested"),
                _("Admin requested changes for '%s'. Please update and resubmit.") % submission.name,
                ntype="modification",
            )

    def action_reject(self):
        refund_ratio = float(self.env["ir.config_parameter"].sudo().get_param("ticket2u_dental_events.rejection_refund_ratio", default="1.0"))
        for submission in self:
            submission.write({"status": "rejected"})
            refunded = 0
            if submission.spent_tx_id and refund_ratio > 0:
                refunded = int(abs(submission.spent_tx_id.amount) * refund_ratio)
                if refunded > 0:
                    wallet = self.env["dental.points.wallet"].get_or_create_wallet(submission.organizer_partner_id)
                    tx = wallet.add_points(refunded, _("Refund for rejected event submission"), reference=submission.name)
                    submission.refund_tx_id = tx.id
            submission._notify_partner(
                submission.organizer_partner_id,
                _("Event rejected"),
                _("Your event '%s' was rejected. Refunded points: %s") % (submission.name, refunded),
                ntype="rejection",
            )

    def action_confirm_payment(self):
        for submission in self:
            if submission.status != "approved_awaiting_payment":
                continue
            event_vals = {
                "name": submission.name,
                "date_begin": submission.date_begin,
                "date_end": submission.date_end,
                "description": submission.description,
                "badge_image": submission.badge_image,
                "is_published": True,
                "website_published": True,
                "user_id": submission.organizer_user_id.id or self.env.user.id,
                "dental_submission_id": submission.id,
                "dental_category": submission.category,
                "ce_credits": submission.ce_credits,
                "event_ticket_ids": [],
            }
            image_field = False
            event_fields = self.env["event.event"]._fields
            for fname in ("image_1920", "image_1024", "image_512", "image_256", "image"):
                if fname in event_fields:
                    image_field = fname
                    break
            header_image = False
            header_media = submission.media_ids.filtered(lambda m: m.is_header)[:1]
            if header_media:
                header_image = header_media.image
            elif submission.media_ids:
                header_image = submission.media_ids[0].image
            elif submission.image:
                header_image = submission.image

            if image_field and header_image:
                event_vals[image_field] = header_image
            for line in submission.ticket_line_ids:
                ticket_vals = {
                    "name": line.name,
                    "seats_max": line.quantity,
                    "start_sale_datetime": line.sale_start,
                    "end_sale_datetime": line.sale_end,
                    "point_cost": line.point_cost,
                    "ce_credit_hours": line.ce_credit_hours,
                }
                event_vals["event_ticket_ids"].append((0, 0, ticket_vals))

            event = self.env["event.event"].create(event_vals)
            if submission.media_ids:
                submission.media_ids.write({
                    "event_id": event.id,
                })
                if not submission.media_ids.filtered(lambda m: m.is_header):
                    submission.media_ids[:1].action_set_as_header()
            submission.write({
                "status": "published",
                "payment_confirmed": True,
                "event_id": event.id,
            })
            submission._notify_partner(
                submission.organizer_partner_id,
                _("Event published"),
                _("Your event '%s' is now live and tickets are available.") % submission.name,
                ntype="published",
                action_url="/event/%s" % event.id,
            )


class DentalEventTicketConfig(models.Model):
    _name = "dental.event.ticket.config"
    _description = "Dental Event Ticket Configuration"

    submission_id = fields.Many2one("dental.event.submission", required=True, ondelete="cascade")
    name = fields.Char(required=True)
    price = fields.Float(string="Monetary Price", default=0.0)
    point_cost = fields.Integer(required=True)
    quantity = fields.Integer(default=1, required=True)
    min_per_order = fields.Integer(default=1)
    max_per_order = fields.Integer(default=10)
    sale_start = fields.Datetime()
    sale_end = fields.Datetime()
    ce_credit_hours = fields.Float(default=0.0)
    benefits = fields.Text()

    @api.constrains("point_cost", "quantity")
    def _check_positive_values(self):
        for rec in self:
            if rec.point_cost < 0:
                raise ValidationError(_("Point cost cannot be negative."))
            if rec.quantity <= 0:
                raise ValidationError(_("Quantity must be greater than zero."))
