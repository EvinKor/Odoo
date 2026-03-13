from odoo import api, fields, models

class EventApplicationImage(models.Model):
    _name = 'event.application.image'
    _description = 'Event Application Image'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer(default=10)
    image = fields.Image(string='Image', required=True)
    application_id = fields.Many2one('event.application', string='Application', ondelete='cascade', index=True)
    is_thumbnail = fields.Boolean(string='Thumbnail', compute='_compute_is_thumbnail', store=False)

    @api.depends('application_id.thumbnail_image', 'image')
    def _compute_is_thumbnail(self):
        for rec in self:
            rec.is_thumbnail = bool(rec.application_id.thumbnail_image) and rec.application_id.thumbnail_image == rec.image

    def action_set_thumbnail(self):
        self.ensure_one()
        if self.application_id:
            self.application_id.thumbnail_image = self.image
        return True


class EventImage(models.Model):
    _name = 'event.image'
    _description = 'Event Image'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer(default=10)
    image = fields.Image(string='Image', required=True)
    event_id = fields.Many2one('event.event', string='Event', ondelete='cascade', index=True)
