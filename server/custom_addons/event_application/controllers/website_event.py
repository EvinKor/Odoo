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
    def _get_points_wallet(self):
        if request.env.user._is_public():
            return False
        if 'event.points.wallet' not in request.env:
            return False
        try:
            return request.env['event.points.wallet'].get_or_create_wallet(request.env.user.partner_id)
        except Exception:
            return False

    def _get_event_notification_count(self):
        if request.env.user._is_public():
            return 0
        return request.env['event.application.notification'].sudo().search_count([
            ('partner_id', '=', request.env.user.partner_id.id),
            ('is_read', '=', False),
        ])
    
    @http.route(['/event', '/event/page/<int:page>'], type='http', auth="public", website=True, sitemap=True)
    def events(self, page=1, **searches):
        """Override to add specialty, case, and country filters"""
        
        # Ensure searches has all required keys
        if 'search' not in searches:
            searches['search'] = ''
        if 'date' not in searches:
            searches['date'] = 'upcoming'
        
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
        published_domain = ['|', ('website_published', '=', True), ('is_published', '=', True)]

        # Base domain: published events on this website
        domain_base = expression.AND([
            published_domain,
            [
            '|', ('website_id', '=', False), ('website_id', '=', website.id),
            ],
        ])

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
        date_filter = searches.get('date', 'upcoming')
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
        all_count = Event.sudo().search_count(published_domain)
        
        upcoming_count = Event.sudo().search_count(
            expression.AND([published_domain, [('date_begin', '>=', request.env.cr.now())]])
        )
        
        past_count = Event.sudo().search_count(
            expression.AND([published_domain, [('date_end', '<', request.env.cr.now())]])
        )
        
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
            count = Event.sudo().search_count(
                expression.AND([
                    published_domain,
                    [('specialty_ids', 'in', [spec.id]), ('date_begin', '>=', request.env.cr.now())],
                ])
            )
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
            count = Event.sudo().search_count(
                expression.AND([
                    published_domain,
                    [('case_ids', 'in', [case.id]), ('date_begin', '>=', request.env.cr.now())],
                ])
            )
            case_data.append({
                'id': case.id,
                'name': case.name,
                'event_count': count
            })
        
        # Fetch all countries with event count
        events_with_country = Event.sudo().search(
            expression.AND([
                published_domain,
                [
                    ('address_id', '!=', False),
                    ('address_id.country_id', '!=', False),
                    ('date_begin', '>=', request.env.cr.now()),
                ],
            ])
        )
        
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
            'current_date': searches.get('date', 'upcoming'),
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
        point_balance = 0
        wallet = self._get_points_wallet()
        if wallet:
            point_balance = int(wallet.balance or 0)
        values['point_balance'] = point_balance
        values['event_notification_count'] = self._get_event_notification_count()

        
        return request.render('website_event.index', values)

    def _parse_registration_post(self, post):
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

        return {
            'buyer_name': buyer_name,
            'buyer_email': buyer_email,
            'buyer_phone': buyer_phone,
            'batch_id': batch_id,
            'registration_data': registration_data,
        }

    def _registration_invoice_summary(self, registration_data):
        registration_tickets = Counter(
            reg.get('event_ticket_id')
            for reg in registration_data
            if reg.get('event_ticket_id')
        )
        event_tickets = request.env['event.event.ticket'].browse(list(registration_tickets.keys()))
        ticket_fields = request.env['event.event.ticket']._fields
        lines = []
        total_points = 0
        total_amount = 0.0
        points_by_ticket = {}
        for ticket in event_tickets:
            qty = int(registration_tickets.get(ticket.id, 0))
            unit_points = int(getattr(ticket, 'point_cost', 0) or 0)
            unit_amount = float(getattr(ticket, 'price', 0.0) or 0.0) if 'price' in ticket_fields else 0.0
            line_points = unit_points * qty
            line_amount = unit_amount * qty
            total_points += line_points
            total_amount += line_amount
            points_by_ticket[ticket.id] = unit_points
            lines.append({
                'ticket_id': ticket.id,
                'name': ticket.name,
                'qty': qty,
                'unit_points': unit_points,
                'line_points': line_points,
                'unit_amount': unit_amount,
                'line_amount': line_amount,
            })
        return {
            'lines': lines,
            'registration_tickets': registration_tickets,
            'event_tickets': event_tickets,
            'total_points': total_points,
            'total_amount': total_amount,
            'points_by_ticket': points_by_ticket,
        }

    def _payment_session_key(self, event):
        return f"event_registration_payment_{event.id}"

    @http.route(['/event/<model("event.event"):event>/registration/payment'], type='http', auth="public", methods=['GET', 'POST'], website=True)
    def registration_payment(self, event, **post):
        key = self._payment_session_key(event)
        if request.httprequest.method == 'POST':
            parsed = self._parse_registration_post(post)
            request.session[key] = parsed

        payload = request.session.get(key)
        if not payload:
            return request.redirect('/event/%s/register' % event.id)

        summary = self._registration_invoice_summary(payload['registration_data'])
        if any(ticket.seats_limited and ticket.seats_available < summary['registration_tickets'].get(ticket.id) for ticket in summary['event_tickets']):
            return request.redirect('/event/%s/register?registration_error_code=insufficient_seats' % event.id)

        return request.render('event_application.registration_payment_page', {
            'event': event,
            'buyer_name': payload['buyer_name'],
            'buyer_email': payload['buyer_email'],
            'buyer_phone': payload['buyer_phone'],
            'invoice_lines': summary['lines'],
            'total_points': summary['total_points'],
            'total_amount': summary['total_amount'],
            'payment_error_code': post.get('payment_error_code') or request.params.get('payment_error_code'),
            'required_points': post.get('required_points') or request.params.get('required_points'),
            'available_points': post.get('available_points') or request.params.get('available_points'),
        })

    @http.route(['/event/<model("event.event"):event>/registration/confirm-payment'], type='http', auth="public", methods=['POST'], website=True)
    def registration_confirm_payment(self, event, **post):
        key = self._payment_session_key(event)
        payload = request.session.get(key)
        if not payload:
            return request.redirect('/event/%s/register' % event.id)

        if request.env.user._is_public():
            return request.redirect('/web/login?redirect=/event/%s/registration/payment' % event.id)

        summary = self._registration_invoice_summary(payload['registration_data'])
        if any(ticket.seats_limited and ticket.seats_available < summary['registration_tickets'].get(ticket.id) for ticket in summary['event_tickets']):
            return request.redirect('/event/%s/register?registration_error_code=insufficient_seats' % event.id)

        if 'point_cost' not in request.env['event.event.ticket']._fields:
            raise UserError('Point system is not configured for event tickets.')

        total_points = summary['total_points']
        if total_points <= 0 and summary['registration_tickets']:
            raise UserError('Selected tickets do not have point cost configured.')

        wallet = self._get_points_wallet()
        if wallet:
            if total_points > 0 and wallet.balance < total_points:
                return request.redirect(
                    '/event/%s/registration/payment?%s' % (
                        event.id,
                        url_encode({
                            'payment_error_code': 'insufficient_points',
                            'required_points': total_points,
                            'available_points': wallet.balance,
                        }),
                    )
                )
            if total_points > 0:
                wallet.spend_points(total_points, 'Event registration purchase', reference=event.name)

        request.env.user.partner_id.sudo().write({
            'name': payload['buyer_name'],
            'email': payload['buyer_email'],
            'phone': payload['buyer_phone'],
        })

        attendees_sudo = self._create_attendees_from_registration_post(event, payload['registration_data'])
        if 'points_spent' in attendees_sudo._fields:
            for attendee in attendees_sudo:
                attendee.sudo().write({
                    'points_spent': summary['points_by_ticket'].get(attendee.event_ticket_id.id, 0),
                })

        try:
            report = request.env.sudo().ref(
                "event.action_report_event_registration_full_page_ticket",
                raise_if_not_found=False,
            )
            if report:
                pdf_bytes, _ = report.sudo()._render_qweb_pdf(
                    report.report_name,
                    res_ids=attendees_sudo.ids,
                )
                filename = f"tickets_{payload['batch_id']}.pdf"
                request.env["ir.attachment"].sudo().create({
                    "name": filename,
                    "type": "binary",
                    "datas": base64.b64encode(pdf_bytes),
                    "mimetype": "application/pdf",
                    "res_model": "res.partner",
                    "res_id": request.env.user.partner_id.id,
                })
        except Exception:
            _logger.exception("Ticket PDF generation skipped due to access/processing error.")

        request.session.pop(key, None)
        return request.redirect(('/event/%s/registration/success?' % event.id) + url_encode({'registration_ids': ",".join([str(rid) for rid in attendees_sudo.ids])}))

    @http.route(['''/event/<model("event.event"):event>/registration/confirm'''], type='http', auth="public", methods=['POST'], website=True)
    def registration_confirm(self, event, **post):
        # Backward compatibility: old confirm endpoint now routes to payment review.
        return self.registration_payment(event, **post)

        
