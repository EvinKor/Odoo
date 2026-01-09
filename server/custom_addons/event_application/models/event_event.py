from odoo import models, fields, api

class EventApplication(models.Model):
    _inherit = 'event.application'
    
    # Add specialty and case tags to applications
    specialty_ids = fields.Many2many(
        'event.specialty',
        string='Specialties',
        help='Dental specialties covered in this event'
    )
    
    case_ids = fields.Many2many(
        'event.case',
        string='Cases',
        help='Types of cases covered in this event'
    )


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
    
    # Address input field for typing complete address
    address_input = fields.Text(string='Complete Address', 
                               help='Type the full address including house number, street, city, ZIP code, etc.',
                               placeholder='e.g., 123 Main Street, Springfield, IL 62701, USA')

    # Online venue fields
    online_platform = fields.Char(string='Online Platform', help='e.g., Zoom, Microsoft Teams, Google Meet')
    online_link = fields.Char(string='Online Link', help='Meeting link or access instructions')

    # Computed full address for physical venues
    full_address = fields.Char(string='Full Address', compute='_compute_full_address', store=True)
    contact_phone = fields.Char(string='Contact Phone')
    contact_email = fields.Char(string='Contact Email')

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


class EventSpecialty(models.Model):
    _name = 'event.specialty'
    _description = 'Event Specialty'
    _order = 'name'
    
    name = fields.Char(string='Specialty Name', required=True, translate=True)
    color = fields.Integer(string='Color Index')
    active = fields.Boolean(default=True)
    
    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'Specialty name must be unique!')
    ]


class EventCase(models.Model):
    _name = 'event.case'
    _description = 'Event Case Type'
    _order = 'name'
    
    name = fields.Char(string='Case Type', required=True, translate=True)
    color = fields.Integer(string='Color Index')
    active = fields.Boolean(default=True)
    
    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'Case type must be unique!')
    ]
