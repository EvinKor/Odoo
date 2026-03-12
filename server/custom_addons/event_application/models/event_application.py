from odoo import _, api, fields, models, Command
from odoo.exceptions import ValidationError

class EventApplication(models.Model):
    _name = 'event.application'
    _description = 'Event Application'
    _order = 'create_date desc'
    
    name = fields.Char(string='Event Name', required=True)
    current_event_name = fields.Char(
        string='Event Name',
        compute='_compute_current_event_name',
    )
    partner_id = fields.Many2one('res.partner', string='Organizer', required=True, default=lambda self: self.env.user.partner_id.id)
    date_begin = fields.Datetime(string='Start Date', required=True)
    date_end = fields.Datetime(string='End Date', required=True)
    registration_start = fields.Datetime(string='Registration Opens')
    registration_end = fields.Datetime(string='Registration Closes')
    registration_limit = fields.Boolean(string='Limit Registrations')
    max_registrations = fields.Integer(string='Maximum Registrations')
    ticket_line_ids = fields.One2many(
        'event.application.ticket',
        'application_id',
        string='Tickets'
    )
    image_ids = fields.One2many(
        'event.application.image',
        'application_id',
        string='Event Images'
    )
    thumbnail_image = fields.Image(string='Thumbnail Image')
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
    building_name = fields.Char(string='Building Name')
    street_address = fields.Char(string='Street Address')
    street_address2 = fields.Char(string='Address Line 2')
    district = fields.Char(string='District / Area')
    floor = fields.Char(string='Floor / Level')
    unit_no = fields.Char(string='Unit / Suite')
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
    specialty_other_text = fields.Text(
        string='Other Specialties (One-time)',
        help='Free-text specialties used only for this application/event.',
    )
    case_other_text = fields.Text(
        string='Other Cases (One-time)',
        help='Free-text case types used only for this application/event.',
    )
    
    rejection_reason = fields.Text(string='Rejection Reason')
    event_id = fields.Many2one('event.event', string='Published Event', readonly=True)
    submission_point_cost = fields.Integer(
        string='Submission Point Cost',
        default=lambda self: self._default_submission_point_cost(),
    )
    submission_points_deducted = fields.Boolean(string='Submission Points Deducted', default=False, readonly=True)
    submission_alert_seen = fields.Boolean(string='Submission Alert Seen', default=False)
    
    # Portal access fields
    access_url = fields.Char('Portal Access URL', compute='_compute_access_url')

    # Compatibility shim: some older loaded code paths may call message_notify
    # on this model even though it does not inherit mail.thread.
    def message_notify(self, **kwargs):
        return True

    def message_subscribe(self, partner_ids=None, subtype_ids=None):
        return True

    def message_unsubscribe(self, partner_ids=None):
        return True

    def message_post(self, **kwargs):
        return self
    
    def _compute_access_url(self):
        """Generate portal URL"""
        for application in self:
            application.access_url = f'/my/event/application/{application.id}'

    @api.depends('name', 'event_id', 'event_id.name')
    def _compute_current_event_name(self):
        for application in self:
            application.current_event_name = application.event_id.name or application.name

    def _default_submission_point_cost(self):
        raw_value = self.env['ir.config_parameter'].sudo().get_param(
            'event_application.submission_point_cost',
            default='75',
        )
        try:
            return int(raw_value or 0)
        except (TypeError, ValueError):
            return 75

    def _create_portal_notification(self, title, message, notification_type='system'):
        self.ensure_one()
        self.env['event.application.notification'].sudo().create({
            'partner_id': self.partner_id.id,
            'application_id': self.id,
            'title': title,
            'message': message,
            'notification_type': notification_type,
            'action_url': self.access_url,
        })

    def _create_admin_submission_notifications(self):
        todo_activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not todo_activity_type:
            return
        admin_users = self.env.ref('base.group_system').sudo().users.filtered(lambda u: u.active)
        if not admin_users:
            return
        model_id = self.env['ir.model']._get_id('event.application')
        Activity = self.env['mail.activity'].sudo()
        for application in self:
            for admin in admin_users:
                exists = Activity.search_count([
                    ('res_model_id', '=', model_id),
                    ('res_id', '=', application.id),
                    ('user_id', '=', admin.id),
                    ('activity_type_id', '=', todo_activity_type.id),
                    ('summary', '=', _('New Event Application Submitted')),
                ])
                if exists:
                    continue
                Activity.create({
                    'res_model_id': model_id,
                    'res_id': application.id,
                    'user_id': admin.id,
                    'activity_type_id': todo_activity_type.id,
                    'summary': _('New Event Application Submitted'),
                    'note': _("A new event application '%s' was submitted by %s.") % (
                        application.name,
                        application.partner_id.name,
                    ),
                    'date_deadline': fields.Date.context_today(self),
                })
    
    @api.depends(
        'venue_type',
        'venue_name',
        'building_name',
        'street_address',
        'street_address2',
        'district',
        'floor',
        'unit_no',
        'online_platform',
        'city',
        'state_id',
        'country_id',
    )
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
                if application.district:
                    location_parts.append(application.district)
                if application.city:
                    location_parts.append(application.city)
                if application.country_id:
                    location_parts.append(application.country_id.name)
                application.location = ', '.join(location_parts) if location_parts else 'Physical Venue'
    
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
    )
    def _compute_full_address(self):
        """Compute full address for physical venues"""
        for application in self:
            if application.venue_type == 'physical':
                address_parts = []
                if application.venue_name:
                    address_parts.append(application.venue_name)
                if application.building_name:
                    address_parts.append(application.building_name)
                if application.street_address:
                    address_parts.append(application.street_address)
                if application.street_address2:
                    address_parts.append(application.street_address2)
                detail_parts = []
                if application.district:
                    detail_parts.append(application.district)
                if application.floor:
                    detail_parts.append(f"Floor {application.floor}")
                if application.unit_no:
                    detail_parts.append(f"Unit {application.unit_no}")
                if detail_parts:
                    address_parts.append(', '.join(detail_parts))
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
        for application in self:
            values = {'state': 'submitted', 'submission_alert_seen': False}
            if (
                not application.submission_points_deducted
                and application.submission_point_cost > 0
                and 'event.points.wallet' in self.env
            ):
                wallet = self.env['event.points.wallet'].get_or_create_wallet(application.partner_id)
                wallet.spend_points(
                    application.submission_point_cost,
                    _('Event application submission'),
                    reference=application.name,
                )
                values['submission_points_deducted'] = True
            application.write(values)

    def _ensure_submission_points_deducted(self):
        for application in self:
            if application.submission_points_deducted:
                continue
            if application.submission_point_cost <= 0:
                continue
            wallet = self.env['event.points.wallet'].get_or_create_wallet(application.partner_id)
            wallet.spend_points(
                application.submission_point_cost,
                _('Event application submission'),
                reference=application.name,
            )
            application.with_context(skip_submission_point_sync=True).write({
                'submission_points_deducted': True,
            })

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        submitted_records = records.filtered(lambda r: r.state == 'submitted')
        if submitted_records:
            submitted_records._ensure_submission_points_deducted()
            submitted_records._create_admin_submission_notifications()
        return records

    def write(self, vals):
        vals = dict(vals or {})
        if (
            vals.get('state') == 'submitted'
            and 'submission_alert_seen' not in vals
            and not self.env.context.get('skip_submission_alert_reset')
        ):
            vals['submission_alert_seen'] = False
        to_notify = self.env['event.application']
        if vals.get('state') == 'submitted':
            to_notify = self.filtered(lambda r: r.state != 'submitted')
        res = super().write(vals)
        if self.env.context.get('skip_submission_point_sync'):
            return res
        if vals.get('state') == 'submitted':
            self.filtered(lambda r: not r.submission_points_deducted)._ensure_submission_points_deducted()
            to_notify._create_admin_submission_notifications()
        return res

    def read(self, fields=None, load='_classic_read'):
        result = super().read(fields=fields, load=load)
        if self.env.user.has_group('base.group_system'):
            unseen = self.filtered(lambda rec: rec.state == 'submitted' and not rec.submission_alert_seen)
            if unseen:
                unseen.with_context(skip_submission_alert_reset=True).sudo().write({'submission_alert_seen': True})
        return result
        
    def action_approve(self):
        self.state = 'approved'
        for application in self:
            application._create_portal_notification(
                _('Application Approved'),
                _("Your event '%s' has been approved.") % (application.name,),
                notification_type='approval',
            )
        
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

    def action_reject_with_reason(self, reason=False):
        refunded_map = {}
        for application in self:
            if (
                application.submission_points_deducted
                and application.submission_point_cost > 0
                and 'event.points.wallet' in self.env
            ):
                wallet = self.env['event.points.wallet'].get_or_create_wallet(application.partner_id)
                wallet.add_points(
                    application.submission_point_cost,
                    _('Event application rejected refund'),
                    reference=application.name,
                )
                refunded_map[application.id] = application.submission_point_cost
        self.write({
            'state': 'rejected',
            'rejection_reason': reason or False,
            'submission_points_deducted': False,
        })
        for application in self:
            message = _("Your event '%s' has been rejected.") % (application.name,)
            refunded_points = refunded_map.get(application.id, 0)
            if refunded_points:
                message = _("%s %s point(s) have been refunded back to you.") % (
                    message,
                    refunded_points,
                )
            if reason:
                message = _("%s Reason: %s") % (message, reason)
            application._create_portal_notification(
                _('Application Rejected'),
                message,
                notification_type='rejection',
            )
        
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
            'website_published': True,
            'user_id': self.env.user.id,
            'application_id': self.id,
            'specialty_ids': [(6, 0, self.specialty_ids.ids)],  # Transfer specialty tags
            'case_ids': [(6, 0, self.case_ids.ids)],  # Transfer case tags
            'specialty_other_text': self.specialty_other_text,
            'case_other_text': self.case_other_text,
            'contact_phone': self.contact_phone,
            'contact_email': self.contact_email,
        }

        if self.registration_limit and self.max_registrations:
            event_vals['seats_max'] = self.max_registrations

        if self.badge_image:
            event_vals['badge_image'] = self.badge_image
        # Use thumbnail as the card background; fall back to legacy card_bg_image only if no thumbnail provided.
        if self.thumbnail_image:
            if 'thumbnail_image' in self.env['event.event']._fields:
                event_vals['thumbnail_image'] = self.thumbnail_image
            event_vals['card_bg_image'] = self.thumbnail_image
        elif self.card_bg_image:
            event_vals['card_bg_image'] = self.card_bg_image

        # Drop any residual cover-image keys that the target model may not have
        event_vals.pop('image_1920', None)
        event_vals.pop('image', None)

        ticket_model_fields = self.env['event.event.ticket']._fields
        ticket_commands = []
        for line in self.ticket_line_ids.sorted(lambda l: (l.sequence, l.id)):
            if not line.name:
                continue
            ticket_vals = {'name': line.name}
            if 'start_sale_datetime' in ticket_model_fields:
                ticket_vals['start_sale_datetime'] = line.start_sale_datetime
            if 'end_sale_datetime' in ticket_model_fields:
                ticket_vals['end_sale_datetime'] = line.end_sale_datetime
            if 'seats_limited' in ticket_model_fields:
                ticket_vals['seats_limited'] = bool(line.seats_limited)
            if line.seats_limited and line.seats_max and 'seats_max' in ticket_model_fields:
                ticket_vals['seats_max'] = line.seats_max
            if line.point_cost and 'point_cost' in ticket_model_fields:
                ticket_vals['point_cost'] = line.point_cost
            ticket_commands.append(Command.create(ticket_vals))

        if ticket_commands:
            event_vals['event_ticket_ids'] = ticket_commands
        elif self.registration_start or self.registration_end or (self.registration_limit and self.max_registrations):
            ticket_vals = {'name': 'Registration'}
            if 'start_sale_datetime' in ticket_model_fields:
                ticket_vals['start_sale_datetime'] = self.registration_start
            if 'end_sale_datetime' in ticket_model_fields:
                ticket_vals['end_sale_datetime'] = self.registration_end
            if 'seats_limited' in ticket_model_fields:
                ticket_vals['seats_limited'] = bool(self.registration_limit)
            if self.registration_limit and self.max_registrations and 'seats_max' in ticket_model_fields:
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
            partner_street2_parts = [part for part in [
                self.street_address2,
                self.district,
                f"Floor {self.floor}" if self.floor else False,
                f"Unit {self.unit_no}" if self.unit_no else False,
            ] if part]
            partner_street2 = ', '.join(partner_street2_parts) if partner_street2_parts else False
            if any([
                self.venue_name,
                self.building_name,
                self.address_input,
                self.street_address,
                self.street_address2,
                self.district,
                self.floor,
                self.unit_no,
                self.city,
                self.zip_code,
                self.state_id,
                self.country_id,
            ]):
                def _norm(value):
                    return (value or '').strip().lower()

                def _partner_matches(candidate):
                    if partner_street and _norm(candidate.street) != _norm(partner_street):
                        return False
                    if partner_street2 and _norm(candidate.street2) != _norm(partner_street2):
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
                        'street2': partner_street2,
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
                    'building_name': self.building_name,
                    'venue_address': self.street_address,
                    'street_address2': self.street_address2,
                    'district': self.district,
                    'floor': self.floor,
                    'unit_no': self.unit_no,
                    'venue_city': self.city,
                    'venue_zip': self.zip_code,
                    'venue_state_id': self.state_id.id if self.state_id else False,
                    'venue_country_id': self.country_id.id if self.country_id else False,
                })
            elif all(name in event_fields for name in ('venue_name', 'street_address', 'city', 'state_id', 'zip_code', 'country_id')):
                # event_application extension fields
                event_vals.update({
                    'venue_name': self.venue_name,
                    'building_name': self.building_name,
                    'street_address': self.street_address,
                    'street_address2': self.street_address2,
                    'district': self.district,
                    'floor': self.floor,
                    'unit_no': self.unit_no,
                    'city': self.city,
                    'state_id': self.state_id.id if self.state_id else False,
                    'zip_code': self.zip_code,
                    'country_id': self.country_id.id if self.country_id else False,
                })
        # Copy gallery images to the published event (only if target field exists)
        if 'image_ids' in self.env['event.event']._fields:
            image_commands = []
            for image in self.image_ids.sorted(lambda img: (img.sequence, img.id)):
                if not image.image:
                    continue
                image_commands.append(Command.create({
                    'name': image.name or 'Event Image',
                    'sequence': image.sequence,
                    'image': image.image,
                }))
            if image_commands:
                event_vals['image_ids'] = image_commands

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
    image_ids = fields.One2many('event.image', 'event_id', string='Gallery Images')
    thumbnail_image = fields.Image(string='Thumbnail Image')
    
    
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

    def write(self, vals):
        res = super().write(vals)
        # Keep application title in sync with published event title so portal edits
        # are reflected in "All Applications" backend list.
        if 'name' in vals:
            for event in self:
                application = event.application_id.sudo()
                if not application:
                    application = self.env['event.application'].sudo().search([('event_id', '=', event.id)], limit=1)
                if application:
                    application.with_context(lang=False).write({'name': event.name})
                    lang_code = self.env.context.get('lang')
                    if lang_code:
                        application.with_context(lang=lang_code).write({'name': event.name})
        return res


class EventApplicationTicket(models.Model):
    _name = 'event.application.ticket'
    _description = 'Event Application Ticket'
    _order = 'sequence, id'

    application_id = fields.Many2one('event.application', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Ticket Name', required=True)
    start_sale_datetime = fields.Datetime(string='Sales Start')
    end_sale_datetime = fields.Datetime(string='Sales End')
    seats_limited = fields.Boolean(string='Limit Quantity')
    seats_max = fields.Integer(string='Maximum Quantity')
    point_cost = fields.Integer(string='Point Cost')

    @api.constrains('start_sale_datetime', 'end_sale_datetime')
    def _check_sale_dates(self):
        for line in self:
            if line.start_sale_datetime and line.end_sale_datetime and line.start_sale_datetime > line.end_sale_datetime:
                raise ValidationError('Ticket sales start date must be before end date.')

    @api.constrains('seats_limited', 'seats_max')
    def _check_seats_max(self):
        for line in self:
            if line.seats_limited and line.seats_max <= 0:
                raise ValidationError('Maximum quantity must be greater than 0 for limited tickets.')


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
    
