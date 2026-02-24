from odoo import fields, models

class RejectApplicationWizard(models.TransientModel):
    _name = 'reject.application.wizard'
    _description = 'Reject Application Wizard'
    
    application_id = fields.Many2one('event.application', string='Application', required=True)
    rejection_reason = fields.Text(string='Rejection Reason', required=True)
    
    def action_reject(self):
        self.application_id.write({
            'state': 'rejected',
            'rejection_reason': self.rejection_reason
        })
        return {'type': 'ir.actions.act_window_close'}
