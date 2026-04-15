# -*- coding: utf-8 -*-
from odoo import api, fields, models
import secrets

class EventRegistration(models.Model):
    _inherit = "event.registration"

    points_spent = fields.Integer(
        string="Points Spent",
        default=0,
        copy=False,
        readonly=True,
    )

    refund_processed = fields.Boolean(
        string="Refund Processed",
        default=False,
        copy=False,
        readonly=True,
    )

    x_register_batch_id = fields.Char(
        string="Registration Batch ID",
        index=True,
        copy=False,
        readonly=True,
    )

    x_ticket_token = fields.Char(
        string="External Ticket Token",
        index=True,
        copy=False,
        readonly=True,
        default=lambda self: secrets.token_urlsafe(24),
    )

    checkin_status = fields.Selection(
        [
            ('not_checked_in', 'Not yet check-in'),
            ('checked_in', 'Checked-in'),
            ('absent', 'Absent'),
            ('cancelled', 'Cancelled'),
        ],
        string="Check-in Status",
        compute='_compute_checkin_status',
        store=False,
    )

    @api.depends('state', 'event_id.stage_id', 'event_id.stage_id.name')
    def _compute_checkin_status(self):
        for registration in self:
            stage_name = (registration.event_id.stage_id.name or '').strip().lower()
            if registration.state == 'cancel' or stage_name == 'cancelled':
                registration.checkin_status = 'cancelled'
            elif registration.state == 'done':
                registration.checkin_status = 'checked_in'
            else:
                registration.checkin_status = 'not_checked_in'
