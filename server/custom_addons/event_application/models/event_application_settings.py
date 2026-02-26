from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class EventApplicationSettings(models.TransientModel):
    _name = "event.application.settings"
    _description = "Event Application Settings"

    submission_point_cost = fields.Integer(
        string="Submission Point Cost",
        help="Points charged when a user submits an event application.",
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        raw_value = self.env["ir.config_parameter"].sudo().get_param(
            "event_application.submission_point_cost",
            default="75",
        )
        try:
            values["submission_point_cost"] = int(raw_value or 0)
        except (TypeError, ValueError):
            values["submission_point_cost"] = 75
        return values

    def action_save(self):
        self.ensure_one()
        if self.submission_point_cost < 0:
            raise ValidationError(_("Submission point cost cannot be negative."))
        self.env["ir.config_parameter"].sudo().set_param(
            "event_application.submission_point_cost",
            str(int(self.submission_point_cost)),
        )
        return {"type": "ir.actions.act_window_close"}
