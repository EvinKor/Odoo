# -*- coding: utf-8 -*-
from odoo import models, fields
import secrets

class EventRegistration(models.Model):
    _inherit = "event.registration"

    x_ticket_token = fields.Char(
        string="External Ticket Token",
        index=True,
        copy=False,
        readonly=True,
        default=lambda self: secrets.token_urlsafe(24),
    )
