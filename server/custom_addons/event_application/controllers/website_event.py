import secrets

from odoo import http
from odoo.http import request
from odoo.osv import expression 
from odoo.addons.website_event.controllers.main import WebsiteEventController
import base64
from werkzeug.urls import url_encode
from collections import Counter
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class CustomWebsiteEventController(WebsiteEventController):
    
    @http.route(['/event', '/event/page/<int:page>'], type='http', auth="public", website=True, sitemap=True)
    def events(self, page=1, **searches):
        """Override to add specialty, case, and country filters"""
        
        # Ensure searches has all required keys
        if 'search' not in searches:
            searches['search'] = ''
        
        # Get specialty filter from URL
        specialty_id = searches.get('specialty')
        current_specialty = None
        if specialty_id and specialty_id != 'all':
            try:
                specialty_id = int(specialty_id)
                spec = request.env['event.specialty'].sudo().browse(specialty_id)
                if spec.exists():
                    current_specialty = spec.name
            except:
                specialty_id = None
        else:
            specialty_id = None
            
        # Get case filter from URL
        case_id = searches.get('case')
        current_case = None
        if case_id and case_id != 'all':
            try:
                case_id = int(case_id)
                case = request.env['event.case'].sudo().browse(case_id)
                if case.exists():
                    current_case = case.name
            except:
                case_id = None
        else:
            case_id = None
        
        # Get country filter from URL
        country_id = searches.get('country')
        current_country = None
        if country_id and country_id != 'all':
            try:
                country_id = int(country_id)
                country = request.env['res.country'].sudo().browse(country_id)
                if country.exists():
                    current_country = country.name
            except:
                country_id = None
        else:
            country_id = None
        
        # Get models first
        Event = request.env['event.event']
        EventType = request.env['event.type']
        
        # Build domain for filtered events
        from datetime import datetime
        from odoo.fields import Datetime

        website = request.website
        now = Datetime.now()

        # Base domain: published events on this website
        domain_base = [
            ('website_published', '=', True),
            '|', ('website_id', '=', False), ('website_id', '=', website.id),
        ]

        # Helper: parse comma-separated ID lists if needed
        def parse_ids(raw):
            if not raw:
                return []
            return [int(x) for x in str(raw).split(',') if x.isdigit()]

        specialty_ids = parse_ids(searches.get('specialty'))
        case_ids = parse_ids(searches.get('case'))
        country_ids = parse_ids(searches.get('country'))

        # Build group domains (each group internally OR, groups combined as AND)
        group_domains = []

        # Date filters
        date_filter = searches.get('date', 'all')
        if date_filter == 'old':
            group_domains.append([('date_end', '<', now)])
        elif date_filter == 'upcoming':
            group_domains.append([('date_begin', '>=', now)])

        # Event type filter
        if searches.get('type'):
            try:
                event_type_id = int(searches.get('type'))
                group_domains.append([('event_type_id', '=', event_type_id)])
            except Exception:
                pass

        # Search text
        if searches.get('search'):
            group_domains.append([('name', 'ilike', searches.get('search'))])

        # Custom filters
        if specialty_ids:
            group_domains.append([('specialty_ids', 'in', specialty_ids)])
        if case_ids:
            group_domains.append([('case_ids', 'in', case_ids)])
        if country_ids:
            group_domains.append([('address_id.country_id', 'in', country_ids)])

        # Combine everything: AND across groups
        domain = expression.AND([domain_base] + group_domains)

        _logger.info(f"Final domain (AND logic): {domain}")

        # Run search
        events = Event.sudo().search(domain, order='date_begin asc')
        event_count = len(events)
        _logger.info(f"Events found: {event_count}")
        
        # Combine everything: AND across groups
        domain = expression.AND([domain_base] + group_domains)
        _logger.info(f"Final domain (AND logic): {domain}")

        # Run search
        events = Event.sudo().search(domain, order='date_begin asc, id asc')
        event_count = len(events)
        _logger.info(f"Events found: {event_count}")

        # Pagination
        step = 12
        pager = request.website.pager(
            url='/event',
            total=event_count,
            page=page,
            step=step,
            scope=5,
            url_args=searches
        )
        
        events_paginated = events[(page - 1) * step:page * step]
        
        # Get event types for filter
        event_types = EventType.sudo().search([])
        
        # Calculate event counts for all, upcoming and past events
        all_count = Event.sudo().search_count([
            ('website_published', '=', True)
        ])
        
        upcoming_count = Event.sudo().search_count([
            ('website_published', '=', True),
            ('date_begin', '>=', request.env.cr.now())
        ])
        
        past_count = Event.sudo().search_count([
            ('website_published', '=', True),
            ('date_end', '<', request.env.cr.now())
        ])
        
        # Build dates list in the format Odoo expects: [id, name, date_begin, event_count]
        # The template expects tuples with 4 elements
        dates = [
            ('all', 'All Events', False, all_count),
            ('upcoming', 'Upcoming Events', False, upcoming_count),
            ('old', 'Past Events', False, past_count),
        ]
        
        # Fetch all specialties with event count
        Specialty = request.env['event.specialty']
        specialties = Specialty.sudo().search([])
        specialty_data = []
        for spec in specialties:
            count = Event.sudo().search_count([
                ('specialty_ids', 'in', [spec.id]),
                ('website_published', '=', True),
                ('date_begin', '>=', request.env.cr.now())
            ])
            specialty_data.append({
                'id': spec.id,
                'name': spec.name,
                'event_count': count
            })
        
        # Fetch all cases with event count
        Case = request.env['event.case']
        cases = Case.sudo().search([])
        case_data = []
        for case in cases:
            count = Event.sudo().search_count([
                ('case_ids', 'in', [case.id]),
                ('website_published', '=', True),
                ('date_begin', '>=', request.env.cr.now())
            ])
            case_data.append({
                'id': case.id,
                'name': case.name,
                'event_count': count
            })
        
        # Fetch all countries with event count
        events_with_country = Event.sudo().search([
            ('website_published', '=', True),
            ('address_id', '!=', False),
            ('address_id.country_id', '!=', False),
            ('date_begin', '>=', request.env.cr.now())
        ])
        
        countries_dict = {}
        for event in events_with_country:
            if event.address_id and event.address_id.country_id:
                country = event.address_id.country_id
                if country.id not in countries_dict:
                    countries_dict[country.id] = {
                        'id': country.id,
                        'name': country.name,
                        'event_count': 0
                    }
                countries_dict[country.id]['event_count'] += 1
        
        country_data = sorted(countries_dict.values(), key=lambda x: x['name'])
        
        # Helper function for keeping URL parameters
        def keep(url, **kwargs):
            """Keep current search parameters and update with new ones"""
            params = dict(searches)
            params.update(kwargs)
            # Remove None values
            params = {k: v for k, v in params.items() if v is not None}
            if params:
                return f"{url}?{url_encode(params)}"
            return url
        
        # Ensure searches has all required keys for the template
        if 'tags' not in searches:
            searches['tags'] = ''
        
        # Build response values with all required template variables
        values = {
            # used by the core template
            'event_ids': events_paginated,

            # your convenience alias (optional)
            'events': events_paginated,

            'event_count': event_count,
            'pager': pager,
            'searches': searches,
            'search': searches.get('search', ''),
            'original_search': searches.get('search', ''),
            'search_tags': False,
            'current_date': searches.get('date', 'all'),
            'current_type': searches.get('type'),
            'current_country': '',  # (only used by the stock topbar)
            # add these two to stay API-compatible with the base template,
            # even if your custom topbar uses different names:
            'types': event_types,             # stock expects "types"
            'countries': [],                  # stock expects "countries"

            'dates': dates,
            'keep': keep,
            'tags': [],

            # your custom data (used by your replaced topbar)
            'specialties': specialty_data,
            'cases': case_data,
            'custom_countries': country_data,
            'current_specialty': current_specialty,
            'current_case': current_case,
            'current_country_custom': current_country,
            'specialty': specialty_id,
            'case': case_id,
            'country': country_id,
        }

        
        return request.render('website_event.index', values)

    @http.route(['''/event/<model("event.event"):event>/registration/confirm'''], type='http', auth="public", methods=['POST'], website=True)
    def registration_confirm(self, event, **post):
        if not request.env['ir.http']._verify_request_recaptcha_token('website_event_registration'):
            raise UserError('Suspicious activity detected by Google reCaptcha.')

        buyer_name = (post.get('buyer_name') or '').strip()
        buyer_email = (post.get('buyer_email') or '').strip()
        buyer_phone = (post.get('buyer_phone') or '').strip()
        if not buyer_name or not buyer_email:
            raise UserError('Buyer name and email are required.')

        ticket_names = {}
        ticket_ids = {}
        for key, value in post.items():
            if key.startswith('ticket_name-'):
                idx = key.split('ticket_name-')[1]
                ticket_names[idx] = (value or '').strip()
            elif key.endswith('-event_ticket_id'):
                parts = key.split('-')
                if len(parts) == 2 and parts[0].isdigit():
                    ticket_ids[parts[0]] = int(value) if value else 0

        if not ticket_names:
            raise UserError('At least one ticket name is required.')

        batch_id = secrets.token_urlsafe(12)
        registration_data = []
        for idx, name in ticket_names.items():
            if not name:
                raise UserError('Each ticket requires a name.')
            vals = {
                'name': name,
                'email': buyer_email,
                'phone': buyer_phone,
                'x_register_batch_id': batch_id,
            }
            if idx in ticket_ids:
                vals['event_ticket_id'] = ticket_ids[idx]
            registration_data.append(vals)

        registration_tickets = Counter(registration.get('event_ticket_id') for registration in registration_data if registration.get('event_ticket_id'))
        event_tickets = request.env['event.event.ticket'].browse(list(registration_tickets.keys()))
        if any(event_ticket.seats_limited and event_ticket.seats_available < registration_tickets.get(event_ticket.id) for event_ticket in event_tickets):
            return request.redirect('/event/%s/register?registration_error_code=insufficient_seats' % event.id)

        if not request.env.user._is_public():
            request.env.user.partner_id.sudo().write({
                'name': buyer_name,
                'email': buyer_email,
                'phone': buyer_phone,
            })

        attendees_sudo = self._create_attendees_from_registration_post(event, registration_data)
        if not request.env.user._is_public():
            report = request.env.ref(
                "event.action_report_event_registration_full_page_ticket",
                raise_if_not_found=False,
            )
            if report:
                pdf_bytes, _ = report.sudo()._render_qweb_pdf(
                    report.report_name,
                    res_ids=attendees_sudo.ids,
                )
                filename = f"tickets_{batch_id}.pdf"
                request.env["ir.attachment"].sudo().create({
                    "name": filename,
                    "type": "binary",
                    "datas": base64.b64encode(pdf_bytes),
                    "mimetype": "application/pdf",
                    "res_model": "res.partner",
                    "res_id": request.env.user.partner_id.id,
                })
        return request.redirect(('/event/%s/registration/success?' % event.id) + url_encode({'registration_ids': ",".join([str(rid) for rid in attendees_sudo.ids])}))

        
