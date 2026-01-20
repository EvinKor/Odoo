# -*- coding: utf-8 -*-
from odoo import fields, models, api


class EventEvent(models.Model):
    _inherit = 'event.event'

    # New venue fields to replace address_id
    venue_name = fields.Char(string='Venue Name', help='Name of the venue/location')
    venue_address = fields.Char(string='Venue Address', help='Street address of the venue')
    venue_city = fields.Char(string='City')
    venue_zip = fields.Char(string='ZIP Code')
    venue_country_id = fields.Many2one('res.country', string='Country')
    venue_state_id = fields.Many2one('res.country.state', string='State', domain="[('country_id', '=', venue_country_id)]")
    venue_latitude = fields.Float(string='Latitude', digits=(10, 7))
    venue_longitude = fields.Float(string='Longitude', digits=(10, 7))

    # Computed field for backward compatibility and display
    venue_full_address = fields.Char(
        string='Full Venue Address',
        compute='_compute_venue_full_address',
        store=True
    )

    @api.depends('venue_name', 'venue_address', 'venue_city', 'venue_zip', 'venue_state_id', 'venue_country_id')
    def _compute_venue_full_address(self):
        for event in self:
            address_parts = []
            if event.venue_name:
                address_parts.append(event.venue_name)
            if event.venue_address:
                address_parts.append(event.venue_address)
            if event.venue_city:
                address_parts.append(event.venue_city)
            if event.venue_state_id:
                address_parts.append(event.venue_state_id.name)
            if event.venue_zip:
                address_parts.append(event.venue_zip)
            if event.venue_country_id:
                address_parts.append(event.venue_country_id.name)

            event.venue_full_address = ', '.join(address_parts) if address_parts else False

    @api.onchange('venue_country_id')
    def _onchange_venue_country_id(self):
        if self.venue_country_id != self.venue_state_id.country_id:
            self.venue_state_id = False

    # Override the address_id related fields for backward compatibility
    @api.model
    def _get_venue_display_address(self):
        """Get the venue address for display purposes"""
        self.ensure_one()
        return self.venue_full_address or 'Online event'