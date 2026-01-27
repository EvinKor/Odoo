# -*- coding: utf-8 -*-
from odoo import fields, models
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
