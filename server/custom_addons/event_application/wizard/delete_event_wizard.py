from odoo import fields, models


class DeleteEventWizard(models.TransientModel):
    _name = 'delete.event.wizard'
    _description = 'Delete Event Wizard'

    event_id = fields.Many2one('event.event', string='Event', required=True)
    refund_points = fields.Boolean(string='Refund registration points', default=True)

    def action_confirm_delete(self):
        self.ensure_one()
        return self.event_id.action_delete_event_with_refund_option(
            refund_points=self.refund_points,
        )
