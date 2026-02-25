from odoo import fields, models


class EventApplicationNotification(models.Model):
    _name = 'event.application.notification'
    _description = 'Event Application Notification'
    _order = 'create_date desc, id desc'

    partner_id = fields.Many2one('res.partner', required=True, index=True, ondelete='cascade')
    application_id = fields.Many2one('event.application', string='Application', ondelete='set null', index=True)
    title = fields.Char(required=True)
    message = fields.Text(required=True)
    notification_type = fields.Selection([
        ('approval', 'Approval'),
        ('rejection', 'Rejection'),
        ('system', 'System'),
    ], default='system', required=True)
    action_url = fields.Char()
    is_read = fields.Boolean(default=False, index=True)

    def action_mark_read(self):
        self.write({'is_read': True})

