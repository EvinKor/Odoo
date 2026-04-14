from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class EventStageRescheduleWizard(models.TransientModel):
    _name = "event.stage.reschedule.wizard"
    _description = "Event Stage Reschedule Wizard"

    event_id = fields.Many2one("event.event", required=True, readonly=True)
    target_stage_id = fields.Many2one("event.stage", required=True, readonly=True)
    date_begin = fields.Datetime(required=True)
    date_end = fields.Datetime(required=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        event = self.env["event.event"].browse(self.env.context.get("default_event_id"))
        target_stage = self.env["event.stage"].browse(self.env.context.get("default_target_stage_id"))
        if not event.exists() or not target_stage.exists():
            return values

        now = fields.Datetime.now()
        start = event.date_begin or now
        end = event.date_end or start
        duration = end - start if end and start and end >= start else timedelta(hours=1)

        if start <= now:
            start = now + timedelta(days=1)
            end = start + duration

        values.update({
            "event_id": event.id,
            "target_stage_id": target_stage.id,
            "date_begin": start,
            "date_end": end if end >= start else start + timedelta(hours=1),
        })
        return values

    def action_confirm(self):
        self.ensure_one()
        now = fields.Datetime.now()
        if self.date_begin <= now:
            raise ValidationError(_("The new start date must be in the future."))
        if self.date_end < self.date_begin:
            raise ValidationError(_("The end date must be after the start date."))

        self.event_id.sudo().write({
            "stage_id": self.target_stage_id.id,
            "date_begin": self.date_begin,
            "date_end": self.date_end,
        })
        return {
            "type": "ir.actions.act_window_close",
            "infos": {"rescheduled": True},
        }
