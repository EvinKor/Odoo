from odoo import _, api, fields, models


class EventCancelWizard(models.TransientModel):
    _name = "event.cancel.wizard"
    _description = "Event Cancel Wizard"

    event_id = fields.Many2one("event.event", required=True, readonly=True)
    target_stage_id = fields.Many2one("event.stage", required=True, readonly=True)
    attendee_count = fields.Integer(readonly=True)
    refund_points = fields.Boolean(string="Refund all attendee credits", default=True)

    @api.model
    def _normalize_reference(self, value):
        return " ".join((str(value or "")).split()).strip().lower()

    def _get_event_reference_candidates(self, event):
        candidates = {
            self._normalize_reference(event.name),
            self._normalize_reference(event.display_name),
        }
        return {candidate for candidate in candidates if candidate}

    def _get_active_attendee_domain(self, event):
        domain = [
            ("event_id", "=", event.id),
            ("state", "!=", "cancel"),
        ]
        if "refund_processed" in self.env["event.registration"]._fields:
            domain.append(("refund_processed", "=", False))
        return domain

    def _get_refund_registration_domain(self, event):
        return list(self._get_active_attendee_domain(event))

    def _get_partner_outstanding_points(self, event, partner, transaction_model):
        if not transaction_model or not partner:
            return 0
        reference_candidates = self._get_event_reference_candidates(event)
        debit_transactions = transaction_model.search([
            ("partner_id", "=", partner.id),
            ("transaction_type", "=", "debit"),
            ("reason", "in", ["Event registration purchase", "API event registration purchase"]),
        ])
        credit_transactions = transaction_model.search([
            ("partner_id", "=", partner.id),
            ("transaction_type", "=", "credit"),
            ("reason", "in", ["Event cancellation refund", "Event registration refund"]),
        ])
        if reference_candidates:
            debit_transactions = debit_transactions.filtered(
                lambda tx: self._normalize_reference(tx.reference) in reference_candidates
            )
            credit_transactions = credit_transactions.filtered(
                lambda tx: self._normalize_reference(tx.reference) in reference_candidates
            )
        debit_total = sum(-int(tx.amount or 0) for tx in debit_transactions)
        credit_total = sum(int(tx.amount or 0) for tx in credit_transactions)
        return max(debit_total - credit_total, 0)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        event = self.env["event.event"].browse(self.env.context.get("default_event_id"))
        target_stage = self.env["event.stage"].browse(self.env.context.get("default_target_stage_id"))
        if not event.exists() or not target_stage.exists():
            return values
        attendee_count = self.env["event.registration"].with_context(active_test=False).search_count(
            self._get_active_attendee_domain(event)
        )
        values.update({
            "event_id": event.id,
            "target_stage_id": target_stage.id,
            "attendee_count": attendee_count,
        })
        return values

    def _refund_and_cancel_registrations(self, event, refund_points):
        registrations = self.env["event.registration"].with_context(active_test=False).search(
            self._get_refund_registration_domain(event)
        )
        if not registrations:
            return {
                "registration_count": 0,
                "refunded_people": 0,
                "refunded_points": 0,
                "unresolved_registrations": 0,
            }

        refunded_partner_ids = set()
        refunded_points = 0
        unresolved_registrations = 0
        updated_registrations = self.env["event.registration"].browse()
        has_wallet_model = "event.points.wallet" in self.env
        has_transaction_model = "event.points.transaction" in self.env
        wallet_model = self.env["event.points.wallet"].sudo() if has_wallet_model else False
        transaction_model = self.env["event.points.transaction"].sudo() if has_transaction_model else False
        partner_model = self.env["res.partner"].sudo()
        if refund_points and has_wallet_model:
            partner_registration_points = {}
            partner_registration_records = {}
            refunded_registrations = self.env["event.registration"].browse()
            for registration in registrations:
                partner = registration.partner_id
                if not partner and registration.email:
                    partner = partner_model.search([("email", "=ilike", registration.email)], limit=1)
                if not partner and registration.email:
                    partner_vals = {
                        "name": registration.name or registration.email,
                        "email": registration.email,
                    }
                    if "phone" in registration._fields and registration.phone:
                        partner_vals["phone"] = registration.phone
                    partner = partner_model.create(partner_vals)
                if not partner:
                    unresolved_registrations += 1
                    continue
                points = 0
                if "points_spent" in registration._fields:
                    points = int(registration.points_spent or 0)
                if points <= 0 and registration.event_ticket_id and "point_cost" in registration.event_ticket_id._fields:
                    points = int(registration.event_ticket_id.point_cost or 0)
                if not registration.partner_id and "partner_id" in registration._fields:
                    registration.sudo().write({"partner_id": partner.id})
                partner_registration_points[partner.id] = partner_registration_points.get(partner.id, 0) + max(points, 0)
                partner_registration_records.setdefault(partner.id, self.env["event.registration"].browse())
                partner_registration_records[partner.id] |= registration
            partner_points = {}
            for partner_id, registration_points in partner_registration_points.items():
                partner = partner_model.browse(partner_id)
                outstanding_points = self._get_partner_outstanding_points(event, partner, transaction_model)
                partner_points[partner_id] = outstanding_points if outstanding_points > 0 else registration_points
            for partner_id, partner_total_points in partner_points.items():
                if partner_total_points <= 0:
                    continue
                partner = partner_model.browse(partner_id)
                wallet = wallet_model.get_or_create_wallet(partner)
                wallet.add_points(partner_total_points, _("Event cancellation refund"), reference=event.name)
                refunded_partner_ids.add(partner_id)
                refunded_points += partner_total_points
                refunded_registrations |= partner_registration_records.get(partner_id, self.env["event.registration"].browse())
            if refunded_registrations:
                mark_vals = {}
                if "points_spent" in refunded_registrations._fields:
                    mark_vals["points_spent"] = 0
                if "refund_processed" in refunded_registrations._fields:
                    mark_vals["refund_processed"] = True
                if mark_vals:
                    refunded_registrations.sudo().write(mark_vals)

        if hasattr(registrations, "action_cancel"):
            registrations.action_cancel()
        else:
            registrations.sudo().write({"state": "cancel"})
        updated_registrations |= registrations
        return {
            "registration_count": len(updated_registrations),
            "refunded_people": len(refunded_partner_ids),
            "refunded_points": refunded_points,
            "unresolved_registrations": unresolved_registrations,
        }

    def action_confirm_cancel(self):
        self.ensure_one()
        event = self.event_id.sudo()
        summary = self._refund_and_cancel_registrations(event, self.refund_points)

        vals = {"stage_id": self.target_stage_id.id}
        if "website_published" in event._fields:
            vals["website_published"] = False
        if "is_published" in event._fields:
            vals["is_published"] = False
        event.write(vals)
        message = _(
            "Event cancelled. %(registrations)s registration(s) updated.",
            registrations=summary["registration_count"],
        )
        if self.refund_points:
            message += " " + _(
                "%(people)s user(s) refunded for %(points)s point(s).",
                people=summary["refunded_people"],
                points=summary["refunded_points"],
            )
            if summary["unresolved_registrations"]:
                message += " " + _(
                    "%(count)s registration(s) could not be matched to a user wallet.",
                    count=summary["unresolved_registrations"],
                )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Event Cancelled"),
                "message": message,
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.act_window_close",
                    "infos": {"stage_updated": True},
                },
            },
        }
