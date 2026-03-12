from odoo import api, fields, models

class EventApplicationImage(models.Model):
    _name = 'event.application.image'
    _description = 'Event Application Image'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer(default=10)
    image = fields.Image(string='Image', required=True)
    application_id = fields.Many2one('event.application', string='Application', ondelete='cascade', index=True)


class EventImage(models.Model):
    _name = 'event.image'
    _description = 'Event Image'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer(default=10)
    image = fields.Image(string='Image', required=True)
    event_id = fields.Many2one('event.event', string='Event', ondelete='cascade', index=True)
