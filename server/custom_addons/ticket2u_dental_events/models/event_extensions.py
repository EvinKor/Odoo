from odoo import api, fields, models


class EventEventTicket(models.Model):
    _inherit = "event.event.ticket"

    point_cost = fields.Integer(string="Point Cost", default=0)
    ce_credit_hours = fields.Float(string="CE Credit Hours", default=0.0)


class EventRegistration(models.Model):
    _inherit = "event.registration"

    points_spent = fields.Integer(string="Points Spent", default=0)
    ce_credits_earned = fields.Float(string="CE Credits Earned", default=0.0)


class EventEvent(models.Model):
    _inherit = "event.event"

    dental_submission_id = fields.Many2one("dental.event.submission", readonly=True)
    dental_category = fields.Selection(selection=lambda self: self.env["dental.event.submission"]._get_category_selection())
    ce_credits = fields.Float(string="CE Credits")
    badge_image = fields.Binary(string="Badge Image")
    media_ids = fields.One2many("dental.event.media", "event_id", string="Event Media")

    @api.model
    def _ticket2u_image_field(self):
        for fname in ("image_1920", "image_1024", "image_512", "image_256", "image"):
            if fname in self._fields:
                return fname
        return False

    def _ticket2u_get_header_image(self):
        self.ensure_one()
        image_field = self._ticket2u_image_field()
        return self[image_field] if image_field else False

    def _ticket2u_set_header_image(self, image_binary):
        image_field = self._ticket2u_image_field()
        if not image_field or not image_binary:
            return
        for event in self:
            event.write({image_field: image_binary})
