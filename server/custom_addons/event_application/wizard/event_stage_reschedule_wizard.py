from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class EventStageRescheduleWizard(models.TransientModel):
    _name = "event.stage.reschedule.wizard"
    _description = "Event Stage Reschedule Wizard"

    FUTURE_FACING_STAGES = {"new", "booked", "announced"}

    event_id = fields.Many2one("event.event", required=True, readonly=True)
    target_stage_id = fields.Many2one("event.stage", required=True, readonly=True)
    needs_reschedule = fields.Boolean(readonly=True)
    needs_republish = fields.Boolean(readonly=True)
    should_reschedule = fields.Boolean(string="Move event dates to the future")
    should_republish = fields.Boolean(string="Show event again on the public event page")
    date_begin = fields.Datetime()
    date_end = fields.Datetime()
    warning_message = fields.Text(readonly=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        event = self.env["event.event"].browse(self.env.context.get("default_event_id"))
        target_stage = self.env["event.stage"].browse(self.env.context.get("default_target_stage_id"))
        if not event.exists() or not target_stage.exists():
            return values

        stage_name = (target_stage.name or "").strip().lower()
        now = fields.Datetime.now()
        start = event.date_begin or now
        end = event.date_end or start
        duration = end - start if end and start and end >= start else timedelta(hours=1)
        is_past = bool(event.date_end and event.date_end < now)
        ends_in_present_or_future = not event.date_end or event.date_end >= now
        is_hidden = (
            not event.active
            or not bool(getattr(event, "website_published", False) or getattr(event, "is_published", False))
        )
        should_review_future_stage = stage_name in self.FUTURE_FACING_STAGES and (is_past or is_hidden)
        should_review_ended_stage = stage_name == "ended" and ends_in_present_or_future

        if stage_name in self.FUTURE_FACING_STAGES and is_past and start <= now:
            start = now + timedelta(days=1)
            end = start + duration
        elif stage_name == "ended":
            end = min(end, now)
            if start > end:
                start = end - duration if duration.total_seconds() > 0 else end - timedelta(hours=1)

        warning_parts = []
        if should_review_future_stage:
            if is_past:
                warning_parts.append(_("This event has already ended."))
            if is_hidden:
                warning_parts.append(_("This event is currently hidden from the public event page."))
        elif should_review_ended_stage:
            warning_parts.append(_("This event is being marked as ended, but its current dates are still ongoing or in the future."))

        values.update({
            "event_id": event.id,
            "target_stage_id": target_stage.id,
            "needs_reschedule": should_review_future_stage or should_review_ended_stage,
            "needs_republish": stage_name in self.FUTURE_FACING_STAGES and is_hidden,
            "should_reschedule": should_review_future_stage or should_review_ended_stage,
            "should_republish": stage_name in self.FUTURE_FACING_STAGES and is_hidden,
            "date_begin": start if (should_review_future_stage or should_review_ended_stage) else event.date_begin,
            "date_end": end if (should_review_future_stage or should_review_ended_stage) else event.date_end,
            "warning_message": " ".join(warning_parts),
        })
        return values

    def action_confirm(self):
        self.ensure_one()
        vals = {"stage_id": self.target_stage_id.id}
        stage_name = (self.target_stage_id.name or "").strip().lower()
        if self.should_reschedule:
            now = fields.Datetime.now()
            if not self.date_begin:
                raise ValidationError(_("The start date is required."))
            if not self.date_end:
                raise ValidationError(_("The end date is required."))
            if self.date_end < self.date_begin:
                raise ValidationError(_("The end date must be after the start date."))
            if stage_name in self.FUTURE_FACING_STAGES:
                if self.date_begin <= now:
                    raise ValidationError(_("The new start date must be in the future."))
            elif stage_name == "ended":
                if self.date_end > now:
                    raise ValidationError(_("An ended event cannot have an end date in the future."))
            vals.update({
                "date_begin": self.date_begin,
                "date_end": self.date_end,
            })
        if self.should_republish:
            vals["active"] = True
            if "website_published" in self.event_id._fields:
                vals["website_published"] = True
            if "is_published" in self.event_id._fields:
                vals["is_published"] = True

        self.event_id.sudo().write(vals)
        return {
            "type": "ir.actions.act_window_close",
            "infos": {"stage_updated": True},
        }

    def action_leave_as_is(self):
        self.ensure_one()
        self.event_id.sudo().write({
            "stage_id": self.target_stage_id.id,
        })
        return {
            "type": "ir.actions.act_window_close",
            "infos": {"stage_updated": True},
        }
