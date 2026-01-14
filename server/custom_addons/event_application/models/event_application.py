from odoo import api, fields, models, Command

class EventApplication(models.Model):
    _name = 'event.application'
    _description = 'Event Application'
    _order = 'create_date desc'
    
    name = fields.Char(string='Event Name', required=True)
    partner_id = fields.Many2one('res.partner', string='Organizer', required=True, default=lambda self: self.env.user.partner_id.id)
    date_begin = fields.Datetime(string='Start Date', required=True)
    date_end = fields.Datetime(string='End Date', required=True)
    registration_start = fields.Datetime(string='Registration Opens')
    registration_end = fields.Datetime(string='Registration Closes')
    registration_limit = fields.Boolean(string='Limit Registrations')
    max_registrations = fields.Integer(string='Maximum Registrations')
    badge_image = fields.Binary(string='Badge Background')
    card_bg_image = fields.Binary(string='Card Background')
    contact_phone = fields.Char(string='Contact Phone')
    contact_email = fields.Char(string='Contact Email')
    description = fields.Html(string='Description')
    
    # Venue type and location fields
    venue_type = fields.Selection([
        ('online', 'Online Event'),
        ('physical', 'Physical Venue')
    ], string='Venue Type', default='physical', required=True)
    
    # Online venue fields
    online_platform = fields.Char(string='Online Platform', help='e.g., Zoom, Microsoft Teams, Google Meet')
    online_link = fields.Char(string='Online Link', help='Meeting link or access instructions')
    
    # Physical venue fields
    venue_name = fields.Char(string='Venue Name', help='Name of the physical location')
    street_address = fields.Char(string='Street Address')
    city = fields.Char(string='City')
    state_id = fields.Many2one('res.country.state', string='State')
    zip_code = fields.Char(string='ZIP Code')
    country_id = fields.Many2one('res.country', string='Country', default=lambda self: self.env.company.country_id)
    
    # Address input field for typing complete address
    address_input = fields.Text(string='Complete Address', 
                               help='Type the full address including house number, street, city, ZIP code, etc.',
                               placeholder='e.g., 123 Main Street, Springfield, IL 62701, USA')
    
    # Legacy location field (keep for backward compatibility)
    location = fields.Char(string='Location', compute='_compute_location', store=True)
    
    # Computed full address for physical venues
    full_address = fields.Char(string='Full Address', compute='_compute_full_address', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('published', 'Published')
    ], default='draft', string='Status', required=True)
    
    # Add specialty and case tags
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
    
    rejection_reason = fields.Text(string='Rejection Reason')
    event_id = fields.Many2one('event.event', string='Published Event', readonly=True)
    
    # Portal access fields
    access_url = fields.Char('Portal Access URL', compute='_compute_access_url')
    
    def _compute_access_url(self):
        """Generate portal URL"""
        for application in self:
            application.access_url = f'/my/event/application/{application.id}'
    
    @api.depends('venue_type', 'venue_name', 'online_platform', 'street_address', 'city', 'state_id', 'country_id')
    def _compute_location(self):
        """Compute legacy location field for backward compatibility"""
        for application in self:
            if application.venue_type == 'online':
                location_parts = []
                if application.online_platform:
                    location_parts.append(application.online_platform)
                if application.venue_name:
                    location_parts.append(application.venue_name)
                application.location = ' - '.join(location_parts) if location_parts else 'Online Event'
            else:  # physical
                location_parts = []
                if application.venue_name:
                    location_parts.append(application.venue_name)
                if application.city:
                    location_parts.append(application.city)
                if application.country_id:
                    location_parts.append(application.country_id.name)
                application.location = ', '.join(location_parts) if location_parts else 'Physical Venue'
    
    @api.depends('venue_name', 'street_address', 'city', 'state_id', 'zip_code', 'country_id')
    def _compute_full_address(self):
        """Compute full address for physical venues"""
        for application in self:
            if application.venue_type == 'physical':
                address_parts = []
                if application.venue_name:
                    address_parts.append(application.venue_name)
                if application.street_address:
                    address_parts.append(application.street_address)
                if application.city:
                    address_parts.append(application.city)
                if application.state_id:
                    address_parts.append(application.state_id.name)
                if application.zip_code:
                    address_parts.append(application.zip_code)
                if application.country_id:
                    address_parts.append(application.country_id.name)
                application.full_address = ', '.join(address_parts)
            else:
                application.full_address = False
    
    @api.constrains('zip_code', 'state_id', 'country_id')
    def _check_zip_code(self):
        """Validate ZIP code based on country and state"""
        for application in self:
            if application.venue_type == 'physical' and application.zip_code and application.country_id:
                country_code = application.country_id.code
                
                if country_code == 'US':
                    # US ZIP code validation (5 digits or 5+4 format)
                    import re
                    if not re.match(r'^\d{5}(-\d{4})?$', application.zip_code):
                        raise ValidationError("US ZIP codes must be in format 12345 or 12345-6789")
                        
                elif country_code == 'CA':
                    # Canadian postal code validation
                    import re
                    if not re.match(r'^[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d$', application.zip_code):
                        raise ValidationError("Canadian postal codes must be in format A1A 1A1 or A1A1A1")
    
    def action_submit(self):
        self.state = 'submitted'
        
    def action_approve(self):
        self.state = 'approved'
        
    def action_reject(self):
        """Open wizard for rejection reason"""
        return {
            'name': 'Reject Application',
            'type': 'ir.actions.act_window',
            'res_model': 'reject.application.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_application_id': self.id}
        }
    
    def action_reset_to_draft(self):
        """Reset to draft"""
        self.write({
            'state': 'draft',
            'rejection_reason': False
        })
        
    def action_publish(self):
        """Create the actual event record on the website"""
        self.ensure_one()
        
        # Prepare event creation values
        event_vals = {
            'name': self.name,
            'date_begin': self.date_begin,
            'date_end': self.date_end,
            'description': self.description,
            'organizer_id': self.partner_id.id,
            'is_published': True,
            'user_id': self.env.user.id,
            'application_id': self.id,
            'specialty_ids': [(6, 0, self.specialty_ids.ids)],  # Transfer specialty tags
            'case_ids': [(6, 0, self.case_ids.ids)],  # Transfer case tags
            'contact_phone': self.contact_phone,
            'contact_email': self.contact_email,
        }

        if self.registration_limit and self.max_registdirations:
            event_vals['seats_max'] = self.max_registrations

        if self.badge_image:
            event_vals['badge_image'] = self.badge_image
        if self.card_bg_image:
            event_vals['card_bg_image'] = self.card_bg_image

        if self.registration_start or self.registration_end or (self.registration_limit and self.max_registrations):
            ticket_vals = {
                'name': 'Registration',
                'start_sale_datetime': self.registration_start,
                'end_sale_datetime': self.registration_end,
            }
            if self.registration_limit and self.max_registrations:
                ticket_vals['seats_max'] = self.max_registrations
            event_vals['event_ticket_ids'] = [Command.create(ticket_vals)]
        
        # Handle venue information based on type
        if self.venue_type == 'online':
            # For online events, store platform and link in description or custom fields
            online_info = []
            if self.online_platform:
                online_info.append(f"Platform: {self.online_platform}")
            if self.online_link:
                online_info.append(f"Link: {self.online_link}")
            if online_info:
                event_vals['description'] = (self.description or '') + '\n\n' + '\n'.join(online_info)
            # Use a default online venue partner for consistency
            online_partner = self.env['res.partner'].search([('name', '=', 'Online Event')], limit=1)
            if not online_partner:
                online_partner = self.env['res.partner'].create({
                    'name': 'Online Event',
                    'website': self.online_link or False,
                    'type': 'contact',
                })
            else:
                if self.online_link:
                    online_partner.write({'website': self.online_link})
            event_vals['address_id'] = online_partner.id
        else:
            # Always create/reuse a venue partner for physical venues and set address_id
            venue_partner = False
            venue_name_value = self.venue_name or self.full_address or self.address_input or self.location or 'Venue'
            partner_street = self.street_address or self.address_input or False
            if any([self.venue_name, self.address_input, self.street_address, self.city, self.zip_code, self.state_id, self.country_id]):
                def _norm(value):
                    return (value or '').strip().lower()

                def _partner_matches(candidate):
                    if partner_street and _norm(candidate.street) != _norm(partner_street):
                        return False
                    if self.city and _norm(candidate.city) != _norm(self.city):
                        return False
                    if self.zip_code and _norm(candidate.zip) != _norm(self.zip_code):
                        return False
                    if self.state_id and candidate.state_id != self.state_id:
                        return False
                    if self.country_id and candidate.country_id != self.country_id:
                        return False
                    return True

                venue_candidates = self.env['res.partner'].search([('name', '=', venue_name_value)])
                for candidate in venue_candidates:
                    if _partner_matches(candidate):
                        venue_partner = candidate
                        break

                if not venue_partner:
                    venue_partner = self.env['res.partner'].create({
                        'name': venue_name_value,
                        'street': partner_street,
                        'city': self.city or False,
                        'zip': self.zip_code or False,
                        'state_id': self.state_id.id if self.state_id else False,
                        'country_id': self.country_id.id if self.country_id else False,
                        'phone': self.contact_phone or False,
                        'email': self.contact_email or False,
                        'type': 'contact',
                    })
                else:
                    updates = {}
                    if self.contact_phone and not venue_partner.phone:
                        updates['phone'] = self.contact_phone
                    if self.contact_email and not venue_partner.email:
                        updates['email'] = self.contact_email
                    if updates:
                        venue_partner.write(updates)

            event_vals['address_id'] = (venue_partner or self.partner_id).id
            event_vals['location'] = self.full_address or self.location
            event_vals['address_input'] = self.address_input

            # For physical venues, use matching event.event fields when available
            event_fields = self.env['event.event']._fields
            if all(name in event_fields for name in ('venue_name', 'venue_address', 'venue_city')):
                # event_venue_map module is installed
                event_vals.update({
                    'venue_name': self.venue_name,
                    'venue_address': self.street_address,
                    'venue_city': self.city,
                    'venue_zip': self.zip_code,
                    'venue_state_id': self.state_id.id if self.state_id else False,
                    'venue_country_id': self.country_id.id if self.country_id else False,
                })
            elif all(name in event_fields for name in ('venue_name', 'street_address', 'city', 'state_id', 'zip_code', 'country_id')):
                # event_application extension fields
                event_vals.update({
                    'venue_name': self.venue_name,
                    'street_address': self.street_address,
                    'city': self.city,
                    'state_id': self.state_id.id if self.state_id else False,
                    'zip_code': self.zip_code,
                    'country_id': self.country_id.id if self.country_id else False,
                })
        
        event = self.env['event.event'].create(event_vals)
        self.write({
            'state': 'published',
            'event_id': event.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'event.event',
            'res_id': event.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_open_event(self):
        """Open the published event"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'event.event',
            'res_id': self.event_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


class EventEvent(models.Model):
    _inherit = 'event.event'
    
    application_id = fields.Many2one('event.application', string='Original Application', readonly=True)
    location = fields.Char(string='Location')
    badge_image = fields.Binary(string='Badge Background')
    
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
    
    def action_view_registrations_portal(self):
        """Allow organizers to view registrations"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Event Registrations',
            'res_model': 'event.registration',
            'view_mode': 'list,form',
            'domain': [('event_id', '=', self.id)],
            'context': {'default_event_id': self.id}
        }


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
    

class EventRegistration(models.Model):
    _inherit = 'event.registration'

    def action_mark_attended(self):
        """Mark attendee as attended (same as barcode scan)"""
        self.write({'state': 'done'})
    
    def action_mark_not_attended(self):
        """Mark attendee as not attended"""
        self.write({'state': 'open'})
    
    def is_attended(self):
        """Check if registration is marked as attended"""
        return self.state == 'done'
