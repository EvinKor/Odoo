from odoo import fields, models


class DentalEventMedia(models.Model):
    _name = "dental.event.media"
    _description = "Dental Event Media"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    image = fields.Binary(required=True)
    submission_id = fields.Many2one("dental.event.submission", ondelete="cascade")
    event_id = fields.Many2one("event.event", ondelete="cascade")
    is_header = fields.Boolean(default=False)

    def action_set_as_header(self):
        for media in self:
            if not media.event_id:
                continue
            siblings = self.search([("event_id", "=", media.event_id.id)])
            siblings.write({"is_header": False})
            media.write({"is_header": True})
            image_field = False
            for fname in ("image_1920", "image_1024", "image_512", "image_256", "image"):
                if fname in media.event_id._fields:
                    image_field = fname
                    break
            if image_field:
                media.event_id.write({image_field: media.image})
