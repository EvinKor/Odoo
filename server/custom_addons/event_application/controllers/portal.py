import base64
from datetime import datetime

from urllib.parse import quote_plus

import pytz

from odoo import fields, http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal

class EventApplicationPortal(CustomerPortal):
    def _registration_owner_domain(self):
        partner = request.env.user.partner_id
        user_email = (request.env.user.email or partner.email or '').strip()
        domain = [('partner_id', '=', partner.id)]
        if user_email:
            domain = ['|', ('partner_id', '=', partner.id), ('email', '=ilike', user_email)]
        return domain

    def _can_access_registration(self, registration):
        if not registration:
            return False
        partner = request.env.user.partner_id
        user_email = (request.env.user.email or partner.email or '').strip().lower()
        reg_email = (registration.email or '').strip().lower()
        return registration.partner_id.id == partner.id or (user_email and reg_email == user_email)

    def _get_event_time_status(self, event, now_dt=None):
        now_dt = now_dt or fields.Datetime.now()
        date_begin = event.date_begin
        date_end = event.date_end

        if date_end and date_end < now_dt:
            return ('past', 'Past', 'bg-danger')
        if date_begin and date_begin > now_dt:
            return ('upcoming', 'Upcoming', 'bg-success')
        return ('present', 'Present', 'bg-warning text-dark')

    def _get_point_balance(self):
        try:
            wallet = request.env['dental.points.wallet'].get_or_create_wallet(request.env.user.partner_id)
            return int(wallet.balance or 0)
        except Exception:
            return 0

    def _parse_csv_int_ids(self, csv_value):
        ids = []
        for part in (csv_value or '').split(','):
            value = (part or '').strip()
            if value.isdigit():
                ids.append(int(value))
        return ids

    def _get_or_create_names(self, model_name, names_text):
        model = request.env[model_name].sudo()
        ids = []
        raw_parts = (names_text or '').replace('\n', ',').split(',')
        for raw_name in raw_parts:
            name = (raw_name or '').strip()
            if not name:
                continue
            existing = model.search([('name', '=ilike', name)], limit=1)
            record = existing or model.create({'name': name})
            ids.append(record.id)
        return ids

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        values['event_point_balance'] = self._get_point_balance()
        if 'event_application_count' in counters:
            values['event_application_count'] = request.env['event.application'].search_count([
                ('partner_id', '=', request.env.user.partner_id.id)
            ])
        if 'my_events_count' in counters:
            values['my_events_count'] = request.env['event.event'].search_count([
                ('organizer_id', '=', request.env.user.partner_id.id)
            ])
        return values
    
    @http.route(['/my/events', '/my/events/registrations'], type='http', auth='user', website=True)
    def my_events(self, **kwargs):
        """Show user's published events"""
        partner = request.env.user.partner_id
        path = request.httprequest.path or ''
        forced_tab = 'registrations' if path.rstrip('/').endswith('/my/events/registrations') else ''
        current_tab = (forced_tab or kwargs.get('tab') or 'events').strip().lower()
        if current_tab not in ('events', 'registrations'):
            current_tab = 'events'
        events_search = (kwargs.get('events_search') or '').strip()
        events_view = (kwargs.get('events_view') or 'upcoming').strip().lower()
        if events_view not in ('upcoming', 'past'):
            events_view = 'upcoming'
        registrations_search = (kwargs.get('registrations_search') or '').strip()
        registrations_event_id = (kwargs.get('registrations_event_id') or '').strip()
        registrations_history = str(kwargs.get('registrations_history') or '').strip().lower() in ('1', 'true', 'yes', 'on')

        events_domain = [
            '|',
            ('organizer_id', '=', partner.id),
            ('application_id.partner_id', '=', partner.id),
        ]
        now_dt = fields.Datetime.now()
        if events_view == 'past':
            events_domain.append(('date_end', '<', now_dt))
        else:
            events_domain += ['|', ('date_end', '>=', now_dt), ('date_begin', '>=', now_dt)]
        if events_search:
            events_domain += ['|', '|', ('name', 'ilike', events_search), ('location', 'ilike', events_search), ('address_id.name', 'ilike', events_search)]

        events = request.env['event.event'].sudo().search(events_domain, order='date_begin desc')

        registrations_domain = list(self._registration_owner_domain())
        if not registrations_history:
            now_dt = fields.Datetime.now()
            registrations_domain += ['|', ('event_id.date_end', '>=', now_dt), ('event_id.date_begin', '>=', now_dt)]
        if registrations_event_id.isdigit():
            registrations_domain.append(('event_id', '=', int(registrations_event_id)))
        if registrations_search:
            registrations_domain += ['|', '|', ('name', 'ilike', registrations_search), ('email', 'ilike', registrations_search), ('event_id.name', 'ilike', registrations_search)]

        registrations = request.env['event.registration'].sudo().search(
            registrations_domain,
            order='create_date desc'
        )
        now_dt = fields.Datetime.now()
        registration_filter_events = registrations.mapped('event_id').sorted(lambda e: e.name or '')
        batches_map = {}
        for reg in registrations:
            batch_id = reg.x_register_batch_id or f"single-{reg.id}"
            batches_map.setdefault(batch_id, request.env['event.registration'].sudo().browse())
            batches_map[batch_id] |= reg

        registration_batches = []
        for batch_id, regs in batches_map.items():
            first = regs[0]
            status_code, status_label, status_badge = self._get_event_time_status(first.event_id, now_dt)
            download_url = (
                f"/my/event-registrations/batch/{batch_id}/ticket"
                if not batch_id.startswith("single-")
                else f"/my/event-registration/{first.id}/ticket"
            )
            registration_batches.append({
                "batch_id": batch_id,
                "event": first.event_id,
                "count": len(regs),
                "buyer_name": first.partner_id.name,
                "buyer_email": first.email,
                "buyer_phone": first.phone,
                "ticket_names": [r.name for r in regs],
                "download_url": download_url,
                "create_date": first.create_date,
                "status_code": status_code,
                "status_label": status_label,
                "status_badge": status_badge,
            })

        registration_batches.sort(key=lambda b: b.get("create_date") or "", reverse=True)
        return request.render('event_application.portal_my_events', {
            'events': events,
            'registration_batches': registration_batches,
            'current_tab': current_tab,
            'current_datetime': now_dt,
            'events_search': events_search,
            'events_view': events_view,
            'registrations_search': registrations_search,
            'registrations_event_id': registrations_event_id,
            'registrations_history': registrations_history,
            'registration_filter_events': registration_filter_events,
        })

    @http.route(['/my/event-registrations'], type='http', auth='user', website=True)
    def my_event_registrations_index(self, **kwargs):
        """List registrations for the current portal user"""
        search = (kwargs.get('search') or '').strip()
        event_id = kwargs.get('event_id') or ''

        domain = list(self._registration_owner_domain())
        if event_id and str(event_id).isdigit():
            domain.append(('event_id', '=', int(event_id)))
        if search:
            domain += ['|', '|', ('name', 'ilike', search), ('email', 'ilike', search), ('event_id.name', 'ilike', search)]

        registrations = request.env['event.registration'].sudo().search(domain, order='create_date desc')
        now_dt = fields.Datetime.now()

        # Events for filter dropdown (based on user's registrations)
        event_ids = registrations.mapped('event_id').ids
        events = request.env['event.event'].sudo().browse(event_ids).sorted(lambda e: e.name)
        batches_map = {}
        for reg in registrations:
            batch_id = reg.x_register_batch_id or f"single-{reg.id}"
            batches_map.setdefault(batch_id, request.env['event.registration'].sudo().browse())
            batches_map[batch_id] |= reg

        registration_batches = []
        for batch_id, regs in batches_map.items():
            first = regs[0]
            status_code, status_label, status_badge = self._get_event_time_status(first.event_id, now_dt)
            download_url = (
                f"/my/event-registrations/batch/{batch_id}/ticket"
                if not batch_id.startswith("single-")
                else f"/my/event-registration/{first.id}/ticket"
            )
            registration_batches.append({
                "batch_id": batch_id,
                "event": first.event_id,
                "count": len(regs),
                "buyer_name": first.partner_id.name,
                "buyer_email": first.email,
                "buyer_phone": first.phone,
                "ticket_names": [r.name for r in regs],
                "download_url": download_url,
                "create_date": first.create_date,
                "status_code": status_code,
                "status_label": status_label,
                "status_badge": status_badge,
            })

        registration_batches.sort(key=lambda b: b.get("create_date") or "", reverse=True)

        return request.render('event_application.portal_my_event_registration_index', {
            'registration_batches': registration_batches,
            'events': events,
            'search': search,
            'event_id': str(event_id) if event_id else '',
        })

    @http.route(['/my/event-registration/<int:registration_id>'], type='http', auth='user', website=True)
    def my_event_registration_detail(self, registration_id, **kwargs):
        """Show QR for a single registration"""
        registration = request.env['event.registration'].sudo().browse(registration_id)
        if not registration or not self._can_access_registration(registration):
            return request.redirect('/my/event-registrations')
        checkin_base = request.httprequest.url_root.rstrip('/')
        return request.render('event_application.portal_my_event_registration_detail', {
            'registration': registration,
            'event': registration.event_id,
            'checkin_base': checkin_base,
            'quote_plus': quote_plus,
        })
    
    @http.route(['/my/event/<int:event_id>'], type='http', auth='user', website=True)
    def my_event_detail(self, event_id, **kwargs):
        """Show event details for editing"""
        event = request.env['event.event'].browse(event_id)
        # Check if user owns this event
        if event.organizer_id.id != request.env.user.partner_id.id:
            return request.redirect('/my')
        
        # Get all available specialties and cases for selection
        specialties = request.env['event.specialty'].search([])
        cases = request.env['event.case'].search([])
        
        return request.render('event_application.portal_my_event_detail', {
            'event': event,
            'specialties': specialties,
            'cases': cases,
        })
    
    @http.route(['/my/event/<int:event_id>/update'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def my_event_update(self, event_id, **post):
        """Update event details"""
        event = request.env['event.event'].sudo().browse(event_id)
        
        # Check if user owns this event
        if event.organizer_id.id != request.env.user.partner_id.id:
            return request.redirect('/my')
        
        # Prepare update values
        update_vals = {}
        
        if post.get('name'):
            update_vals['name'] = post.get('name')
        
        if post.get('description'):
            update_vals['description'] = post.get('description')
        
        if post.get('location'):
            update_vals['location'] = post.get('location')
        
        if post.get('seats_max'):
            update_vals['seats_max'] = int(post.get('seats_max'))
        
        # Handle datetime fields
        if post.get('date_begin'):
            dt = datetime.strptime(post.get('date_begin'), '%Y-%m-%dT%H:%M')
            update_vals['date_begin'] = dt.strftime('%Y-%m-%d %H:%M:%S')
        
        if post.get('date_end'):
            dt = datetime.strptime(post.get('date_end'), '%Y-%m-%dT%H:%M')
            update_vals['date_end'] = dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Handle specialty tags (many2many)
        specialty_ids = request.httprequest.form.getlist('specialty_ids')
        if specialty_ids:
            update_vals['specialty_ids'] = [(6, 0, [int(sid) for sid in specialty_ids])]
        else:
            update_vals['specialty_ids'] = [(5, 0, 0)]  # Clear all
        
        # Handle case tags (many2many)
        case_ids = request.httprequest.form.getlist('case_ids')
        if case_ids:
            update_vals['case_ids'] = [(6, 0, [int(cid) for cid in case_ids])]
        else:
            update_vals['case_ids'] = [(5, 0, 0)]  # Clear all
        
        # Update the event
        event.write(update_vals)
        
        return request.redirect(f'/my/event/{event_id}?success=1')
    
    @http.route(['/my/event/applications'], type='http', auth='user', website=True)
    def my_applications(self, **kwargs):
        applications = request.env['event.application'].search([
            ('partner_id', '=', request.env.user.partner_id.id)
        ])
        return request.render('event_application.portal_my_applications', {
            'applications': applications,
        })
    
    @http.route(['/event/apply'], type='http', auth='user', website=True)
    def event_application_form(self, **kwargs):
        # Get all available specialties and cases for selection
        specialties = request.env['event.specialty'].search([])
        cases = request.env['event.case'].search([])
        
        # Get countries and states for address dropdowns
        countries = request.env['res.country'].search([], order='name')
        states = request.env['res.country.state'].search([], order='country_id, name')
        
        return request.render('event_application.event_application_form', {
            'specialties': specialties,
            'cases': cases,
            'countries': countries,
            'states': states,
            'form_error': kwargs.get('error'),
        })
    
    def _convert_datetime(self, date_str):
        """Convert datetime-local format to Odoo format"""
        if not date_str:
            return False
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
        except (ValueError, TypeError):
            return False
        tz_name = (
            request.env.context.get('tz')
            or request.env.user.tz
            or request.env.company.partner_id.tz
            or 'UTC'
        )
        try:
            tzinfo = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tzinfo = pytz.UTC
        dt_local = tzinfo.localize(dt, is_dst=None)
        dt_utc = dt_local.astimezone(pytz.UTC)
        return fields.Datetime.to_string(dt_utc)
    
    @http.route(['/event/apply/submit'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def event_application_submit(self, **post):
        date_begin = self._convert_datetime(post.get('date_begin'))
        date_end = self._convert_datetime(post.get('date_end'))
        registration_start = self._convert_datetime(post.get('registration_start'))
        registration_end = self._convert_datetime(post.get('registration_end'))
        registration_limit = bool(post.get('registration_limit'))
        max_registrations = int(post.get('max_registrations')) if post.get('max_registrations') else 0
        
        if not date_begin or not date_end:
            return request.redirect('/event/apply?error=invalid_dates')
        if date_begin and date_end and date_begin > date_end:
            return request.redirect('/event/apply?error=invalid_date_range')
        if registration_start and registration_end and registration_start > registration_end:
            return request.redirect('/event/apply?error=invalid_registration_dates')

        # Parse dynamic ticket rows
        form_data = request.httprequest.form
        ticket_names = form_data.getlist('ticket_name[]')
        ticket_starts = form_data.getlist('ticket_start[]')
        ticket_ends = form_data.getlist('ticket_end[]')
        ticket_limits = form_data.getlist('ticket_limit[]')
        ticket_maxes = form_data.getlist('ticket_max[]')
        ticket_points = form_data.getlist('ticket_points[]')

        row_count = max(
            len(ticket_names),
            len(ticket_starts),
            len(ticket_ends),
            len(ticket_limits),
            len(ticket_maxes),
            len(ticket_points),
        )
        ticket_line_commands = []
        for idx in range(row_count):
            raw_name = (ticket_names[idx] if idx < len(ticket_names) else '').strip()
            raw_start = ticket_starts[idx] if idx < len(ticket_starts) else ''
            raw_end = ticket_ends[idx] if idx < len(ticket_ends) else ''
            raw_limit = ticket_limits[idx] if idx < len(ticket_limits) else '0'
            raw_max = ticket_maxes[idx] if idx < len(ticket_maxes) else ''
            raw_points = (ticket_points[idx] if idx < len(ticket_points) else '').strip()

            has_points = bool(raw_points) and raw_points != '0'
            if not any([raw_name, raw_start, raw_end, raw_max, has_points]):
                continue
            if not raw_name:
                return request.redirect('/event/apply?error=ticket_name_required')

            start_dt = self._convert_datetime(raw_start)
            end_dt = self._convert_datetime(raw_end)
            if raw_start and not start_dt:
                return request.redirect('/event/apply?error=invalid_ticket_dates')
            if raw_end and not end_dt:
                return request.redirect('/event/apply?error=invalid_ticket_dates')
            if start_dt and end_dt and start_dt > end_dt:
                return request.redirect('/event/apply?error=invalid_ticket_date_range')

            seats_limited = str(raw_limit) == '1'
            seats_max = int(raw_max) if raw_max else 0
            if seats_limited and seats_max <= 0:
                return request.redirect('/event/apply?error=invalid_ticket_max')

            point_cost = int(raw_points) if raw_points else 0
            if point_cost < 0:
                return request.redirect('/event/apply?error=invalid_ticket_points')

            ticket_line_commands.append((0, 0, {
                'name': raw_name,
                'start_sale_datetime': start_dt,
                'end_sale_datetime': end_dt,
                'seats_limited': seats_limited,
                'seats_max': seats_max if seats_limited else 0,
                'point_cost': point_cost,
                'sequence': (idx + 1) * 10,
            }))
        
        # Handle specialty tags (many2many)
        specialty_ids_str = post.get('specialty_ids', '')
        specialty_ids = self._parse_csv_int_ids(specialty_ids_str)
        specialty_ids.extend(self._get_or_create_names('event.specialty', post.get('specialty_other_names')))
        specialty_ids = list(dict.fromkeys(specialty_ids))
        specialty_ids_vals = [(6, 0, specialty_ids)] if specialty_ids else False
        
        # Handle case tags (many2many)
        case_ids_str = post.get('case_ids', '')
        case_ids = self._parse_csv_int_ids(case_ids_str)
        case_ids.extend(self._get_or_create_names('event.case', post.get('case_other_names')))
        case_ids = list(dict.fromkeys(case_ids))
        case_ids_vals = [(6, 0, case_ids)] if case_ids else False
        
        # Create the application with all fields
        vals = {
            'name': post.get('event_name'),
            'partner_id': request.env.user.partner_id.id,
            'date_begin': date_begin,
            'date_end': date_end,
            'registration_start': registration_start,
            'registration_end': registration_end,
            'registration_limit': registration_limit,
            'max_registrations': max_registrations if registration_limit else 0,
            'contact_phone': post.get('contact_phone'),
            'contact_email': post.get('contact_email'),
            'description': post.get('description'),
            'venue_type': post.get('venue_type', 'physical'),
            'state': 'submitted',
        }
        
        # Add venue-specific fields based on type
        venue_type = post.get('venue_type', 'physical')
        if venue_type == 'online':
            vals.update({
                'online_platform': post.get('online_platform'),
                'online_link': post.get('online_link'),
            })
        else:  # physical
            vals.update({
                'venue_name': post.get('venue_name'),
                'address_input': post.get('address_input'),
                'street_address': post.get('street_address'),
                'city': post.get('city'),
                'zip_code': post.get('zip_code'),
                'state_id': int(post.get('state_id')) if post.get('state_id') else False,
                'country_id': int(post.get('country_id')) if post.get('country_id') else False,
            })
        
        # Add specialty and case tags if any were selected
        if specialty_ids_vals:
            vals['specialty_ids'] = specialty_ids_vals
        if case_ids_vals:
            vals['case_ids'] = case_ids_vals
        if ticket_line_commands:
            vals['ticket_line_ids'] = ticket_line_commands

        badge_file = request.httprequest.files.get('badge_image')
        if badge_file and badge_file.filename:
            vals['badge_image'] = base64.b64encode(badge_file.read())
        card_bg_file = request.httprequest.files.get('card_bg_image')
        if card_bg_file and card_bg_file.filename:
            vals['card_bg_image'] = base64.b64encode(card_bg_file.read())
        
        request.env['event.application'].create(vals)
        return request.redirect('/my/event/applications')
    
    @http.route(['/my/event/application/<int:application_id>'], type='http', auth='user', website=True)
    def event_application_detail(self, application_id, **kwargs):
        application = request.env['event.application'].browse(application_id)
        if application.partner_id.id != request.env.user.partner_id.id:
            return request.redirect('/my')
        return request.render('event_application.portal_application_detail', {
            'application': application,
        })
    
    @http.route(['/my/event/<int:event_id>/registrations'], type='http', auth='user', website=True)
    def my_event_registrations(self, event_id, **kw):
        """View registrations for an event"""
        event = request.env['event.event'].sudo().browse(event_id)
        
        # Check if user owns this event
        if event.organizer_id.id != request.env.user.partner_id.id:
            return request.redirect('/my')
        
        # Get all registrations for this event
        registrations = request.env['event.registration'].sudo().search([
            ('event_id', '=', event_id)
        ], order='create_date desc')
        
        # Calculate statistics using the 'state' field
        total_count = len(registrations)
        attended_count = len(registrations.filtered(lambda r: r.state == 'done'))
        not_attended_count = len(registrations.filtered(lambda r: r.state in ['open', 'draft']))
        attendance_rate = (attended_count / total_count * 100) if total_count else 0
        checkin_base = request.httprequest.url_root.rstrip('/')
        
        return request.render('event_application.portal_my_event_registrations', {
            'event': event,
            'registrations': registrations,
            'total_count': total_count,
            'attended_count': attended_count,
            'not_attended_count': not_attended_count,
            'attendance_rate': attendance_rate,
            'checkin_base': checkin_base,
            'quote_plus': quote_plus,
            'page_name': 'event_registrations',
        })

    @http.route(['/my/event/<int:event_id>/registration/<int:registration_id>/mark'], 
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def mark_registration_attended(self, event_id, registration_id, **post):
        """Mark a registration as attended (same as barcode scan does)"""
        event = request.env['event.event'].sudo().browse(event_id)
        
        # Check if user owns this event
        if event.organizer_id.id != request.env.user.partner_id.id:
            return request.redirect('/my')
        
        registration = request.env['event.registration'].sudo().browse(registration_id)
        if registration.event_id.id == event_id:
            registration.action_mark_attended()
        
        return request.redirect(f'/my/event/{event_id}/registrations?success=1')

    @http.route(['/my/event/<int:event_id>/registration/<int:registration_id>/unmark'], 
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def mark_registration_not_attended(self, event_id, registration_id, **post):
        """Mark a registration as not attended"""
        event = request.env['event.event'].sudo().browse(event_id)
        
        # Check if user owns this event
        if event.organizer_id.id != request.env.user.partner_id.id:
            return request.redirect('/my')
        
        registration = request.env['event.registration'].sudo().browse(registration_id)
        if registration.event_id.id == event_id:
            registration.action_mark_not_attended()
        
        return request.redirect(f'/my/event/{event_id}/registrations?success=1')

    @http.route(['/my/event-review'], type='http', auth='user', website=True)
    def event_review(self, **kwargs):
        """Backward-compatible route: redirect to unified Applications backend view"""
        action = request.env.ref('event_application.action_event_application')
        return request.redirect(f'/web#action={action.id}')
