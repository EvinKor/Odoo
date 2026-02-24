from odoo import fields, models


class DentalNotification(models.Model):
    _name = "dental.notification"
    _description = "Dental Notification"
    _order = "create_date desc, id desc"

    partner_id = fields.Many2one("res.partner", required=True, index=True)
    title = fields.Char(required=True)
    message = fields.Text(required=True)
    notification_type = fields.Selection([
        ("submission", "Submission"),
        ("approval", "Approval"),
        ("payment", "Payment"),
        ("published", "Published"),
        ("modification", "Modification"),
        ("rejection", "Rejection"),
        ("purchase", "Purchase"),
        ("reminder", "Reminder"),
        ("system", "System"),
    ], default="system", required=True)
    action_url = fields.Char()
    is_read = fields.Boolean(default=False)

    def action_mark_read(self):
        self.write({"is_read": True})
