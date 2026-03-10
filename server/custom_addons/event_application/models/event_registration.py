# -*- coding: utf-8 -*-
from odoo import api, fields, models
import secrets

class EventRegistration(models.Model):
    _inherit = "event.registration"

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
        ],
        string="Check-in Status",
        compute='_compute_checkin_status',
        store=False,
    )

    @api.depends('state')
    def _compute_checkin_status(self):
        for registration in self:
            if registration.state == 'done':
                registration.checkin_status = 'checked_in'
            elif registration.state == 'cancel':
                registration.checkin_status = 'absent'
            else:
                registration.checkin_status = 'not_checked_in'
