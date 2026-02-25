import base64
from datetime import datetime

from urllib.parse import quote_plus
from urllib.parse import urlencode

import pytz
import logging

from odoo import fields, http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

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
            if 'event.points.wallet' not in request.env:
                return 0
            wallet = request.env['event.points.wallet'].get_or_create_wallet(request.env.user.partner_id)
            return int(wallet.balance or 0)
        except Exception:
            return 0

    def _get_event_notification_count(self):
        return request.env['event.application.notification'].sudo().search_count([
            ('partner_id', '=', request.env.user.partner_id.id),
            ('is_read', '=', False),
        ])

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
        if 'event_point_balance' in counters:
            values['event_point_balance'] = self._get_point_balance()
        if 'event_notification_count' in counters:
            values['event_notification_count'] = self._get_event_notification_count()
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
            'event_notification_count': self._get_event_notification_count(),
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
        event = request.env['event.event'].sudo().browse(event_id)
        if not event.exists():
            return request.redirect('/my')

        is_admin = request.env.user.has_group('base.group_system')
        is_owner = event.organizer_id.id == request.env.user.partner_id.id
        if not is_admin and not is_owner:
            return request.redirect('/my')

        specialties = request.env['event.specialty'].sudo().search([])
        cases = request.env['event.case'].sudo().search([])
        countries = request.env['res.country'].sudo().search([], order='name')
        states = request.env['res.country.state'].sudo().search([], order='country_id, name')
        ticket_fields = request.env['event.event.ticket']._fields

        return request.render('event_application.portal_my_event_detail', {
            'event': event,
            'specialties': specialties,
            'cases': cases,
            'countries': countries,
            'states': states,
            'is_admin': is_admin,
            'can_edit_tickets': is_admin,
            'allow_ticket_price': 'price' in ticket_fields,
            'allow_ticket_point_cost': 'point_cost' in ticket_fields,
        })
    
    @http.route(['/my/event/<int:event_id>/update'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def my_event_update(self, event_id, **post):
        """Update event details"""
        event = request.env['event.event'].sudo().browse(event_id)

        if not event.exists():
            return request.redirect('/my')

        is_admin = request.env.user.has_group('base.group_system')
        is_owner = event.organizer_id.id == request.env.user.partner_id.id
        if not is_admin and not is_owner:
            return request.redirect('/my')

        update_vals = {}

        posted_name = (post.get('name') or '').strip()
        if posted_name:
            update_vals['name'] = posted_name

        if 'description' in post:
            update_vals['description'] = post.get('description')

        if 'location' in post:
            update_vals['location'] = post.get('location')

        if post.get('seats_max') not in (None, ''):
            update_vals['seats_max'] = int(post.get('seats_max'))

        if post.get('date_begin'):
            parsed = self._convert_datetime(post.get('date_begin'))
            if parsed:
                update_vals['date_begin'] = parsed

        if post.get('date_end'):
            parsed = self._convert_datetime(post.get('date_end'))
            if parsed:
                update_vals['date_end'] = parsed

        specialty_ids = request.httprequest.form.getlist('specialty_ids')
        if specialty_ids:
            update_vals['specialty_ids'] = [(6, 0, [int(sid) for sid in specialty_ids])]
        else:
            update_vals['specialty_ids'] = [(5, 0, 0)]

        case_ids = request.httprequest.form.getlist('case_ids')
        if case_ids:
            update_vals['case_ids'] = [(6, 0, [int(cid) for cid in case_ids])]
        else:
            update_vals['case_ids'] = [(5, 0, 0)]

        if is_admin:
            for field_name in ('contact_phone', 'contact_email', 'venue_name', 'street_address', 'city', 'zip_code', 'online_platform', 'online_link', 'address_input'):
                if field_name in post:
                    update_vals[field_name] = post.get(field_name) or False

            if 'venue_type' in post:
                update_vals['venue_type'] = post.get('venue_type') or 'physical'
            if post.get('state_id'):
                update_vals['state_id'] = int(post.get('state_id'))
            elif 'state_id' in post:
                update_vals['state_id'] = False
            if post.get('country_id'):
                update_vals['country_id'] = int(post.get('country_id'))
            elif 'country_id' in post:
                update_vals['country_id'] = False

            ticket_model = request.env['event.event.ticket'].sudo()
            ticket_fields = ticket_model._fields
            for ticket in event.event_ticket_ids:
                tvals = {}
                name_key = f'ticket_name_{ticket.id}'
                if name_key in post:
                    tvals['name'] = post.get(name_key) or ticket.name

                start_key = f'ticket_start_{ticket.id}'
                if start_key in post and 'start_sale_datetime' in ticket_fields:
                    tvals['start_sale_datetime'] = self._convert_datetime(post.get(start_key)) if post.get(start_key) else False

                end_key = f'ticket_end_{ticket.id}'
                if end_key in post and 'end_sale_datetime' in ticket_fields:
                    tvals['end_sale_datetime'] = self._convert_datetime(post.get(end_key)) if post.get(end_key) else False

                limit_key = f'ticket_limit_{ticket.id}'
                if limit_key in post and 'seats_limited' in ticket_fields:
                    tvals['seats_limited'] = str(post.get(limit_key)) == '1'

                max_key = f'ticket_max_{ticket.id}'
                if max_key in post and 'seats_max' in ticket_fields:
                    tvals['seats_max'] = int(post.get(max_key)) if post.get(max_key) else 0

                price_key = f'ticket_price_{ticket.id}'
                if price_key in post and 'price' in ticket_fields:
                    tvals['price'] = float(post.get(price_key)) if post.get(price_key) else 0.0

                points_key = f'ticket_point_cost_{ticket.id}'
                if points_key in post and 'point_cost' in ticket_fields:
                    tvals['point_cost'] = int(post.get(points_key)) if post.get(points_key) else 0

                if tvals:
                    ticket.write(tvals)

        # Update both base and current UI language values to avoid stale
        # translated titles showing the previous event name.
        if 'name' in update_vals:
            new_name = update_vals.pop('name')
            event.with_context(lang=False).write({'name': new_name})
            lang_code = request.env.context.get('lang')
            if lang_code:
                event.with_context(lang=lang_code).write({'name': new_name})

        if update_vals:
            event.write(update_vals)

        return request.redirect(f'/my/event/{event_id}?success=1')
    
    @http.route(['/my/event/applications'], type='http', auth='user', website=True)
    def my_applications(self, **kwargs):
        applications = request.env['event.application'].search([
            ('partner_id', '=', request.env.user.partner_id.id)
        ])
        return request.render('event_application.portal_my_applications', {
            'applications': applications,
            'event_notification_count': self._get_event_notification_count(),
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

    def _application_payment_session_key(self):
        return 'event_application_submit_payment'

    def _get_submission_point_cost(self):
        raw_value = request.env['ir.config_parameter'].sudo().get_param(
            'event_application.submission_point_cost',
            default='75',
        )
        try:
            return max(int(raw_value or 0), 0)
        except (TypeError, ValueError):
            return 75

    def _get_points_wallet(self):
        if 'event.points.wallet' not in request.env:
            return False
        try:
            return request.env['event.points.wallet'].get_or_create_wallet(request.env.user.partner_id)
        except Exception:
            return False

    def _build_application_payload(self, post):
        date_begin = self._convert_datetime(post.get('date_begin'))
        date_end = self._convert_datetime(post.get('date_end'))
        registration_start = self._convert_datetime(post.get('registration_start'))
        registration_end = self._convert_datetime(post.get('registration_end'))
        registration_limit = bool(post.get('registration_limit'))
        max_registrations = int(post.get('max_registrations')) if post.get('max_registrations') else 0

        if not date_begin or not date_end:
            return None, 'invalid_dates'
        if date_begin and date_end and date_begin > date_end:
            return None, 'invalid_date_range'
        if registration_start and registration_end and registration_start > registration_end:
            return None, 'invalid_registration_dates'

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
        ticket_lines = []
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
                return None, 'ticket_name_required'

            start_dt = self._convert_datetime(raw_start)
            end_dt = self._convert_datetime(raw_end)
            if raw_start and not start_dt:
                return None, 'invalid_ticket_dates'
            if raw_end and not end_dt:
                return None, 'invalid_ticket_dates'
            if start_dt and end_dt and start_dt > end_dt:
                return None, 'invalid_ticket_date_range'

            seats_limited = str(raw_limit) == '1'
            seats_max = int(raw_max) if raw_max else 0
            if seats_limited and seats_max <= 0:
                return None, 'invalid_ticket_max'

            point_cost = int(raw_points) if raw_points else 0
            if point_cost < 0:
                return None, 'invalid_ticket_points'

            ticket_lines.append({
                'name': raw_name,
                'start_sale_datetime': start_dt,
                'end_sale_datetime': end_dt,
                'seats_limited': seats_limited,
                'seats_max': seats_max if seats_limited else 0,
                'point_cost': point_cost,
                'sequence': (idx + 1) * 10,
            })

        specialty_ids = self._parse_csv_int_ids(post.get('specialty_ids', ''))
        specialty_ids.extend(self._get_or_create_names('event.specialty', post.get('specialty_other_names')))
        specialty_ids = list(dict.fromkeys(specialty_ids))

        case_ids = self._parse_csv_int_ids(post.get('case_ids', ''))
        case_ids.extend(self._get_or_create_names('event.case', post.get('case_other_names')))
        case_ids = list(dict.fromkeys(case_ids))

        badge_image = False
        badge_file = request.httprequest.files.get('badge_image')
        if badge_file and badge_file.filename:
            badge_image = base64.b64encode(badge_file.read()).decode('ascii')

        card_bg_image = False
        card_bg_file = request.httprequest.files.get('card_bg_image')
        if card_bg_file and card_bg_file.filename:
            card_bg_image = base64.b64encode(card_bg_file.read()).decode('ascii')

        payload = {
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
            'online_platform': post.get('online_platform'),
            'online_link': post.get('online_link'),
            'venue_name': post.get('venue_name'),
            'address_input': post.get('address_input'),
            'street_address': post.get('street_address'),
            'city': post.get('city'),
            'zip_code': post.get('zip_code'),
            'state_id': int(post.get('state_id')) if post.get('state_id') else False,
            'country_id': int(post.get('country_id')) if post.get('country_id') else False,
            'specialty_ids': specialty_ids,
            'case_ids': case_ids,
            'ticket_lines': ticket_lines,
            'badge_image': badge_image,
            'card_bg_image': card_bg_image,
            'submission_point_cost': self._get_submission_point_cost(),
        }
        return payload, None

    def _build_application_vals_from_payload(self, payload):
        vals = {
            'name': payload.get('name'),
            'partner_id': payload.get('partner_id'),
            'date_begin': payload.get('date_begin'),
            'date_end': payload.get('date_end'),
            'registration_start': payload.get('registration_start'),
            'registration_end': payload.get('registration_end'),
            'registration_limit': payload.get('registration_limit'),
            'max_registrations': payload.get('max_registrations') or 0,
            'contact_phone': payload.get('contact_phone'),
            'contact_email': payload.get('contact_email'),
            'description': payload.get('description'),
            'venue_type': payload.get('venue_type', 'physical'),
            'state': 'draft',
            'submission_point_cost': payload.get('submission_point_cost') or 0,
        }
        if payload.get('venue_type') == 'online':
            vals.update({
                'online_platform': payload.get('online_platform'),
                'online_link': payload.get('online_link'),
            })
        else:
            vals.update({
                'venue_name': payload.get('venue_name'),
                'address_input': payload.get('address_input'),
                'street_address': payload.get('street_address'),
                'city': payload.get('city'),
                'zip_code': payload.get('zip_code'),
                'state_id': payload.get('state_id') or False,
                'country_id': payload.get('country_id') or False,
            })

        specialty_ids = payload.get('specialty_ids') or []
        if specialty_ids:
            vals['specialty_ids'] = [(6, 0, specialty_ids)]
        case_ids = payload.get('case_ids') or []
        if case_ids:
            vals['case_ids'] = [(6, 0, case_ids)]

        ticket_lines = payload.get('ticket_lines') or []
        if ticket_lines:
            vals['ticket_line_ids'] = [(0, 0, line) for line in ticket_lines]

        if payload.get('badge_image'):
            vals['badge_image'] = payload.get('badge_image')
        if payload.get('card_bg_image'):
            vals['card_bg_image'] = payload.get('card_bg_image')
        return vals
    
    @http.route(['/event/apply/submit'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def event_application_submit(self, **post):
        payload, error_code = self._build_application_payload(post)
        if error_code:
            return request.redirect(f'/event/apply?error={error_code}')
        request.session[self._application_payment_session_key()] = payload
        return request.redirect('/event/apply/payment')

    @http.route(['/event/apply/payment'], type='http', auth='user', website=True, methods=['GET'])
    def event_application_payment(self, **kwargs):
        payload = request.session.get(self._application_payment_session_key())
        if not payload:
            return request.redirect('/event/apply')
        required_points = int(payload.get('submission_point_cost') or 0)
        wallet = self._get_points_wallet()
        available_points = int(wallet.get_current_balance()) if wallet else 0
        payment_error_code = kwargs.get('payment_error_code')
        if required_points > 0 and available_points < required_points:
            payment_error_code = payment_error_code or 'insufficient_points'
        return request.render('event_application.event_application_payment_page', {
            'application_payload': payload,
            'required_points': required_points,
            'available_points': available_points,
            'payment_error_code': payment_error_code,
            'submit_error': kwargs.get('submit_error'),
        })

    @http.route(['/event/apply/confirm-payment'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def event_application_confirm_payment(self, **post):
        try:
            payload = request.session.get(self._application_payment_session_key())
            if not payload:
                return request.redirect('/event/apply')
            required_points = int(payload.get('submission_point_cost') or 0)
            wallet = self._get_points_wallet()
            available_points = int(wallet.get_current_balance()) if wallet else 0
            if required_points > 0 and available_points < required_points:
                return request.redirect('/event/apply/payment?payment_error_code=insufficient_points')
            vals = self._build_application_vals_from_payload(payload)
            application = request.env['event.application'].create(vals)
            application.action_submit()
            request.session.pop(self._application_payment_session_key(), None)
            return request.redirect('/my/event/applications')
        except ValidationError as e:
            return request.redirect('/event/apply/payment?' + urlencode({
                'payment_error_code': 'submit_failed',
                'submit_error': str(e),
            }))
        except Exception as e:
            _logger.exception("Event application confirm-payment failed")
            return request.redirect('/event/apply/payment?' + urlencode({
                'payment_error_code': 'submit_failed',
                'submit_error': str(e),
            }))
    
    @http.route(['/my/event/application/<int:application_id>'], type='http', auth='user', website=True)
    def event_application_detail(self, application_id, **kwargs):
        application = request.env['event.application'].browse(application_id)
        if application.partner_id.id != request.env.user.partner_id.id:
            return request.redirect('/my')
        return request.render('event_application.portal_application_detail', {
            'application': application,
            'event_notification_count': self._get_event_notification_count(),
        })

    @http.route(['/my/event/notifications'], type='http', auth='user', website=True)
    def my_event_notifications(self, **kwargs):
        show_all = str(kwargs.get('show_all') or '').strip().lower() in ('1', 'true', 'yes', 'on')
        domain = [('partner_id', '=', request.env.user.partner_id.id)]
        if not show_all:
            domain.append(('is_read', '=', False))
        notifications = request.env['event.application.notification'].sudo().search(domain)
        return request.render('event_application.portal_my_event_notifications', {
            'notifications': notifications,
            'event_notification_count': self._get_event_notification_count(),
            'show_all_notifications': show_all,
        })

    @http.route(['/my/points/log'], type='http', auth='user', website=True)
    def my_points_log(self, **kwargs):
        partner = request.env.user.partner_id
        wallet_model = request.env['event.points.wallet'].sudo()
        tx_model = request.env['event.points.transaction'].sudo()

        wallet = wallet_model.search([('partner_id', '=', partner.id)], limit=1)
        balance = int(wallet.get_current_balance()) if wallet else 0
        transactions = tx_model.search([('partner_id', '=', partner.id)], order='create_date desc, id desc')

        return request.render('event_application.portal_my_points_log', {
            'wallet': wallet,
            'balance': balance,
            'transactions': transactions,
            'event_notification_count': self._get_event_notification_count(),
            'event_point_balance': balance,
        })

    @http.route(['/my/event/notification/<int:notification_id>/read'], type='http', auth='user', website=True)
    def my_event_notification_read(self, notification_id, **kwargs):
        notification = request.env['event.application.notification'].sudo().search([
            ('id', '=', notification_id),
            ('partner_id', '=', request.env.user.partner_id.id),
        ], limit=1)
        if not notification:
            return request.redirect('/my/event/notifications')
        # Force mark-as-read before any redirect to target page.
        notification.sudo().write({'is_read': True})
        if notification.action_url and str(notification.action_url).startswith('/'):
            return request.redirect(notification.action_url)
        return request.redirect('/my/event/notifications')
    
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

        # Group registrations by ticket to make attendee lists clearer.
        # Pre-create groups from the event's configured ticket types so they
        # are shown even when no attendee has registered yet.
        grouped = {}
        for ticket in event.event_ticket_ids.sorted(lambda t: (t.sequence, t.id)):
            grouped[ticket.id] = {
                'ticket': ticket,
                'ticket_name': ticket.name or 'Unnamed Ticket',
                'registrations': request.env['event.registration'].sudo().browse(),
            }

        for registration in registrations:
            ticket = registration.event_ticket_id
            ticket_id = ticket.id or 0
            if ticket_id not in grouped:
                grouped[ticket_id] = {
                    'ticket': ticket,
                    'ticket_name': ticket.name if ticket else 'General / No Ticket',
                    'registrations': request.env['event.registration'].sudo().browse(),
                }
            grouped[ticket_id]['registrations'] |= registration

        ticket_groups = sorted(
            grouped.values(),
            key=lambda g: (
                g['ticket'].sequence if g['ticket'] else 999999,
                (g['ticket_name'] or '').lower(),
            ),
        )
        for group in ticket_groups:
            group_regs = group['registrations']
            group['total_count'] = len(group_regs)
            group['attended_count'] = len(group_regs.filtered(lambda r: r.state == 'done'))
            group['not_attended_count'] = len(group_regs.filtered(lambda r: r.state in ['open', 'draft']))
        
        return request.render('event_application.portal_my_event_registrations', {
            'event': event,
            'registrations': registrations,
            'ticket_groups': ticket_groups,
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
