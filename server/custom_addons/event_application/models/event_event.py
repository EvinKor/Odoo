from odoo import _, api, fields, models
from odoo.exceptions import UserError


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
    specialty_other_text = fields.Text(
        string='Other Specialties',
        help='One-time specialty labels for this event only.',
    )
    case_other_text = fields.Text(
        string='Other Cases',
        help='One-time case labels for this event only.',
    )

    country_id = fields.Many2one('res.country', string='Country')
    
    # Detailed venue address fields
    venue_type = fields.Selection([
        ('online', 'Online Event'),
        ('physical', 'Physical Venue')
    ], string='Venue Type', default='physical')

    # Physical venue fields
    venue_name = fields.Char(string='Venue Name', help='Name of the physical location')
    building_name = fields.Char(string='Building Name')
    street_address = fields.Char(string='Street Address')
    street_address2 = fields.Char(string='Address Line 2')
    district = fields.Char(string='District / Area')
    floor = fields.Char(string='Floor / Level')
    unit_no = fields.Char(string='Unit / Suite')
    city = fields.Char(string='City')
    state_id = fields.Many2one('res.country.state', string='State')
    zip_code = fields.Char(string='ZIP Code')
    venue_address = fields.Char(string='Venue Address')
    venue_city = fields.Char(string='Venue City')
    venue_zip = fields.Char(string='Venue ZIP')
    venue_state_id = fields.Many2one('res.country.state', string='Venue State')
    venue_country_id = fields.Many2one('res.country', string='Venue Country')
    card_bg_image = fields.Binary(string='Card Background')
    registration_total_count = fields.Integer(
        string='All Registrations',
        compute='_compute_registration_counts',
    )
    registration_archived_count = fields.Integer(
        string='Archived Registrations',
        compute='_compute_registration_counts',
    )
    
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

    @api.depends('registration_ids', 'registration_ids.active')
    def _compute_registration_counts(self):
        registration_model = self.env['event.registration'].with_context(active_test=False)
        grouped = registration_model.read_group(
            [('event_id', 'in', self.ids)],
            ['event_id', 'active'],
            ['event_id', 'active'],
            lazy=False,
        )
        totals = {event_id: 0 for event_id in self.ids}
        archived = {event_id: 0 for event_id in self.ids}
        for row in grouped:
            event_id = row.get('event_id') and row['event_id'][0]
            count = row.get('__count', 0)
            if not event_id:
                continue
            totals[event_id] = totals.get(event_id, 0) + count
            if row.get('active') is False:
                archived[event_id] = archived.get(event_id, 0) + count
        for event in self:
            event.registration_total_count = totals.get(event.id, 0)
            event.registration_archived_count = archived.get(event.id, 0)

    def action_view_registrations_portal(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("event.act_event_registration_from_event")
        action.update({
            'domain': [('event_id', '=', self.id)],
            'context': {
                'default_event_id': self.id,
                'active_test': False,
                'search_default_taken': 0,
                'search_default_filter_inactive': 0,
                'name_with_seats_availability': True,
            },
        })
        return action

    def action_hide_from_users(self):
        vals = {}
        if 'website_published' in self._fields:
            vals['website_published'] = False
        if 'is_published' in self._fields:
            vals['is_published'] = False
        if vals:
            self.write(vals)
        return True

    def action_show_to_users(self):
        vals = {}
        if 'website_published' in self._fields:
            vals['website_published'] = True
        if 'is_published' in self._fields:
            vals['is_published'] = True
        if vals:
            self.write(vals)
        return True

    def action_delete_all_registrations(self):
        registration_model = self.env['event.registration'].with_context(active_test=False)
        for event in self:
            registrations = registration_model.search([('event_id', '=', event.id)])
            if registrations:
                registrations.unlink()
        return True

    def action_open_delete_event_wizard(self):
        self.ensure_one()
        return {
            'name': _('Delete Event'),
            'type': 'ir.actions.act_window',
            'res_model': 'delete.event.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_event_id': self.id},
        }

    def action_delete_event_with_refund_option(self, refund_points=False):
        registration_model = self.env['event.registration'].with_context(active_test=False)
        wallet_model = self.env['event.points.wallet'].sudo() if 'event.points.wallet' in self.env else False
        for event in self:
            registrations = registration_model.search([('event_id', '=', event.id)])
            for registration in registrations:
                if refund_points and wallet_model and registration.partner_id:
                    points = 0
                    if 'points_spent' in registration._fields:
                        points = int(registration.points_spent or 0)
                    elif registration.event_ticket_id and 'point_cost' in registration.event_ticket_id._fields:
                        points = int(registration.event_ticket_id.point_cost or 0)
                    if points > 0:
                        wallet = wallet_model.get_or_create_wallet(registration.partner_id)
                        wallet.add_points(points, _('Event registration refund'), reference=event.name)
                        if 'points_spent' in registration._fields:
                            registration.write({'points_spent': 0})
            registrations.unlink()
            super(EventEvent, event.with_context(force_event_hard_delete=True)).unlink()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_archive(self):
        res = super().action_archive()
        vals = {}
        if 'website_published' in self._fields:
            vals['website_published'] = False
        if 'is_published' in self._fields:
            vals['is_published'] = False
        if vals:
            self.write(vals)
        return res

    def action_unarchive(self):
        return super().action_unarchive()

    def unlink(self):
        if self.env.context.get('force_event_hard_delete'):
            return super().unlink()
        # Soft delete for events: archive and unpublish instead of removing rows.
        self.action_archive()
        return True

    @api.depends(
        'venue_name',
        'building_name',
        'street_address',
        'street_address2',
        'district',
        'floor',
        'unit_no',
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
                if event.building_name:
                    address_parts.append(event.building_name)
                if event.street_address:
                    address_parts.append(event.street_address)
                if event.street_address2:
                    address_parts.append(event.street_address2)
                detail_parts = []
                if event.district:
                    detail_parts.append(event.district)
                if event.floor:
                    detail_parts.append(f"Floor {event.floor}")
                if event.unit_no:
                    detail_parts.append(f"Unit {event.unit_no}")
                if detail_parts:
                    address_parts.append(', '.join(detail_parts))
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
        # Remove image fields that may not exist in this deployment to avoid invalid field errors.
        for vals in vals_list:
            if 'image_1920' in vals and 'image_1920' not in self._fields:
                vals.pop('image_1920', None)
            if 'image' in vals and 'image' not in self._fields:
                vals.pop('image', None)
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
        'building_name',
        'venue_address',
        'venue_city',
        'venue_zip',
        'venue_state_id',
        'venue_country_id',
        'street_address',
        'street_address2',
        'district',
        'floor',
        'unit_no',
        'city',
        'zip_code',
        'state_id',
        'country_id',
    )
    def _compute_venue_full_address(self):
        for event in self:
            address = event.venue_address or event.street_address or ''
            address2 = event.street_address2 or ''
            detail_parts = []
            if event.district:
                detail_parts.append(event.district)
            if event.floor:
                detail_parts.append(f"Floor {event.floor}")
            if event.unit_no:
                detail_parts.append(f"Unit {event.unit_no}")
            city = event.venue_city or event.city or ''
            zip_code = event.venue_zip or event.zip_code or ''
            state = event.venue_state_id or event.state_id
            country = event.venue_country_id or event.country_id
            parts = [
                event.venue_name or False,
                event.building_name or False,
                address or False,
                address2 or False,
                ', '.join(detail_parts) if detail_parts else False,
            ]
            city_state_zip = [p for p in [city, state.name if state else False, zip_code] if p]
            if city_state_zip:
                parts.append(', '.join(city_state_zip))
            if country:
                parts.append(country.name)
            event.venue_full_address = ', '.join([p for p in parts if p]) or False


class EventEventTicket(models.Model):
    _inherit = 'event.event.ticket'
    _order = 'is_pinned desc, sequence, id'

    point_cost = fields.Integer(
        string='Point Cost',
        default=0,
        help='Points required for this ticket.',
    )
    is_pinned = fields.Boolean(
        string='Pin Ticket',
        default=False,
        help='Pinned tickets are shown first.',
    )

