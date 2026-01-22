from odoo import models, fields, api


class EventEvent(models.Model):
    _inherit = 'event.event'
    
    # Specialty - using tags (many2many) for flexibility
    specialty_ids = fields.Many2many(
        'event.specialty',
        string='Specialties',
        help='Dental specialties covered in this event'
    )
    
    # Cases - using tags (many2many) for flexibility
    case_ids = fields.Many2many(
        'event.case',
        string='Cases',
        help='Types of cases covered in this event'
    )

    country_id = fields.Many2one('res.country', string='Country')
    
    # Detailed venue address fields
    venue_type = fields.Selection([
        ('online', 'Online Event'),
        ('physical', 'Physical Venue')
    ], string='Venue Type', default='physical')

    # Physical venue fields
    venue_name = fields.Char(string='Venue Name', help='Name of the physical location')
    street_address = fields.Char(string='Street Address')
    city = fields.Char(string='City')
    state_id = fields.Many2one('res.country.state', string='State')
    zip_code = fields.Char(string='ZIP Code')
    venue_address = fields.Char(string='Venue Address')
    venue_city = fields.Char(string='Venue City')
    venue_zip = fields.Char(string='Venue ZIP')
    venue_state_id = fields.Many2one('res.country.state', string='Venue State')
    venue_country_id = fields.Many2one('res.country', string='Venue Country')
    card_bg_image = fields.Binary(string='Card Background')
    
    # Address input field for typing complete address
    address_input = fields.Text(string='Complete Address', 
                               help='Type the full address including house number, street, city, ZIP code, etc.',
                               placeholder='e.g., 123 Main Street, Springfield, IL 62701, USA')

    # Online venue fields
    online_platform = fields.Char(string='Online Platform', help='e.g., Zoom, Microsoft Teams, Google Meet')
    online_link = fields.Char(string='Online Link', help='Meeting link or access instructions')

    # Computed full address for physical venues
    full_address = fields.Char(string='Full Address', compute='_compute_full_address', store=True)
    venue_full_address = fields.Char(string='Venue Full Address', compute='_compute_venue_full_address', store=True)
    contact_phone = fields.Char(string='Contact Phone')
    contact_email = fields.Char(string='Contact Email')
    venue_display = fields.Text(string='Venue Details', compute='_compute_venue_display', readonly=True)

    @api.depends(
        'venue_name',
        'street_address',
        'city',
        'state_id',
        'zip_code',
        'country_id',
        'address_id',
        'address_id.contact_address',
        'address_id.name',
    )
    def _compute_full_address(self):
        for event in self:
            if event.venue_type == 'physical':
                address_parts = []
                if event.venue_name:
                    address_parts.append(event.venue_name)
                if event.street_address:
                    address_parts.append(event.street_address)
                city_state_zip = []
                if event.city:
                    city_state_zip.append(event.city)
                if event.state_id:
                    city_state_zip.append(event.state_id.name)
                if event.zip_code:
                    city_state_zip.append(event.zip_code)
                if city_state_zip:
                    address_parts.append(', '.join(city_state_zip))
                if event.country_id:
                    address_parts.append(event.country_id.name)
                if address_parts:
                    event.full_address = '\n'.join(address_parts)
                elif event.address_id:
                    event.full_address = (event.address_id.contact_address or event.address_id.name or '').strip() or False
                else:
                    event.full_address = False
            else:
                event.full_address = False

    @api.depends(
        'address_id',
        'address_id.name',
        'address_id.street',
        'address_id.street2',
        'address_id.city',
        'address_id.zip',
        'address_id.state_id',
        'address_id.country_id',
    )
    def _compute_venue_display(self):
        for event in self:
            if not event.address_id:
                event.venue_display = False
                continue
            name = event.address_id.name or ''
            address = (event.address_id._display_address(without_company=True) or '').strip()
            if name and address:
                event.venue_display = f"{name}\n{address}"
            else:
                event.venue_display = name or address or False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for event in records:
            if not event.address_input:
                event.address_input = event.full_address or event.venue_full_address or False
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'address_input' not in vals:
            for event in self:
                if not event.address_input:
                    event.address_input = event.full_address or event.venue_full_address or False
        return result

    @api.depends(
        'venue_name',
        'venue_address',
        'venue_city',
        'venue_zip',
        'venue_state_id',
        'venue_country_id',
        'street_address',
        'city',
        'zip_code',
        'state_id',
        'country_id',
    )
    def _compute_venue_full_address(self):
        for event in self:
            address = event.venue_address or event.street_address or ''
            city = event.venue_city or event.city or ''
            zip_code = event.venue_zip or event.zip_code or ''
            state = event.venue_state_id or event.state_id
            country = event.venue_country_id or event.country_id
            parts = [event.venue_name or False, address or False]
            city_state_zip = [p for p in [city, state.name if state else False, zip_code] if p]
            if city_state_zip:
                parts.append(', '.join(city_state_zip))
            if country:
                parts.append(country.name)
            event.venue_full_address = ', '.join([p for p in parts if p]) or False

