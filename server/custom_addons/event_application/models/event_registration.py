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
            ('ended', 'Ended'),
            ('absent', 'Absent'),
            ('cancelled', 'Cancelled'),
        ],
        string="Check-in Status",
        compute='_compute_checkin_status',
        store=False,
    )

    ticket_lifecycle_status = fields.Selection(
        [
            ('active', 'Active'),
            ('ended', 'Ended'),
            ('cancelled', 'Cancelled'),
        ],
        string="Ticket Status",
        compute='_compute_ticket_lifecycle_status',
        store=False,
    )

    def _get_event_stage_name(self):
        self.ensure_one()
        return (self.event_id.stage_id.name or '').strip().lower()

    @api.depends('state', 'event_id.stage_id', 'event_id.stage_id.name', 'event_id.date_end')
    def _compute_ticket_lifecycle_status(self):
        now_dt = fields.Datetime.now()
        for registration in self:
            stage_name = registration._get_event_stage_name()
            if registration.state == 'cancel' or stage_name == 'cancelled':
                registration.ticket_lifecycle_status = 'cancelled'
            elif stage_name == 'ended' or (registration.event_id.date_end and registration.event_id.date_end < now_dt):
                registration.ticket_lifecycle_status = 'ended'
            else:
                registration.ticket_lifecycle_status = 'active'

    @api.depends('state', 'event_id.stage_id', 'event_id.stage_id.name', 'event_id.date_end')
    def _compute_checkin_status(self):
        now_dt = fields.Datetime.now()
        for registration in self:
            stage_name = registration._get_event_stage_name()
            if registration.state == 'cancel' or stage_name == 'cancelled':
                registration.checkin_status = 'cancelled'
            elif registration.state == 'done':
                registration.checkin_status = 'checked_in'
            elif stage_name == 'ended' or (registration.event_id.date_end and registration.event_id.date_end < now_dt):
                registration.checkin_status = 'ended'
            else:
                registration.checkin_status = 'not_checked_in'
