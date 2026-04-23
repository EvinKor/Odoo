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
    def _public_stage_ids(self):
        stages = request.env['event.stage'].sudo().search([])
        live_names = {'announced', 'booked'}
        past_names = {'ended'}
        live_ids = stages.filtered(lambda stage: (stage.name or '').strip().lower() in live_names).ids
        past_ids = stages.filtered(lambda stage: (stage.name or '').strip().lower() in past_names).ids
        return {
            'live': live_ids,
            'past': past_ids,
            'all': live_ids + [stage_id for stage_id in past_ids if stage_id not in live_ids],
        }

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

    def _ticket_is_bookable(self, ticket, now=None):
        now = now or fields.Datetime.now()
        start_sale = getattr(ticket, 'start_sale_datetime', False)
        end_sale = getattr(ticket, 'end_sale_datetime', False)
        seats_limited = bool(getattr(ticket, 'seats_limited', False))
        seats_available = getattr(ticket, 'seats_available', 0)
        start_ok = not start_sale or start_sale <= now
        end_ok = not end_sale or end_sale >= now
        seats_ok = not seats_limited or seats_available > 0
        return start_ok and end_ok and seats_ok

    def _event_availability_key(self, event, now=None):
        now = now or fields.Datetime.now()
        if not getattr(event, 'event_registrations_open', False):
            return 'unavailable'
        if event.event_ticket_ids and any(self._ticket_is_bookable(ticket, now=now) for ticket in event.event_ticket_ids):
            return 'booking_tickets'
        return 'open_registering'
    
    @http.route(['/event', '/event/page/<int:page>'], type='http', auth="public", website=True, sitemap=True)
    def events(self, page=1, **searches):
        """Override the website event listing with simplified custom filters."""
        
        # Ensure searches has all required keys
        if 'search' not in searches:
            searches['search'] = ''
        if 'date' not in searches:
            searches['date'] = 'upcoming'
        for deprecated_key in ('specialty', 'case', 'country'):
            searches.pop(deprecated_key, None)

        availability_options = [
            ('booking_tickets', 'Booking Tickets'),
            ('open_registering', 'Open for Registering'),
            ('unavailable', 'Unavailable'),
        ]
        availability_labels = dict(availability_options)
        current_availability = searches.get('availability')
        if current_availability not in availability_labels:
            searches.pop('availability', None)
            current_availability = False
        
        # Get models first
        Event = request.env['event.event']
        EventType = request.env['event.type']
        
        # Build domain for filtered events
        from datetime import datetime
        from odoo.fields import Datetime

        website = request.website
        now = Datetime.now()
        published_domain = ['|', ('website_published', '=', True), ('is_published', '=', True)]
        public_stage_ids = self._public_stage_ids()

        # Base domain: published events on this website
        domain_base = expression.AND([
            published_domain,
            [('active', '=', True)],
            [
            '|', ('website_id', '=', False), ('website_id', '=', website.id),
            ],
        ])

        # Build group domains (each group internally OR, groups combined as AND)
        group_domains = []

        # Date filters
        date_filter = searches.get('date', 'upcoming')
        if date_filter == 'old':
            group_domains.append([('stage_id', 'in', public_stage_ids['past'] or [0])])
        elif date_filter == 'upcoming':
            group_domains.append([('stage_id', 'in', public_stage_ids['live'] or [0])])
        else:
            group_domains.append([('stage_id', 'in', public_stage_ids['all'] or [0])])

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

        # Combine everything: AND across groups
        domain = expression.AND([domain_base] + group_domains)

        _logger.info(f"Final domain (AND logic): {domain}")

        # Run search
        events = Event.sudo().search(domain, order='date_begin asc, id asc')
        availability_counts = {key: 0 for key, _label in availability_options}
        for event in events:
            availability_counts[self._event_availability_key(event, now=now)] += 1
        if current_availability:
            events = events.filtered(
                lambda event: self._event_availability_key(event, now=now) == current_availability
            )
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
        all_count = Event.sudo().search_count(
            expression.AND([published_domain, [('active', '=', True), ('stage_id', 'in', public_stage_ids['all'] or [0])]])
        )
        
        upcoming_count = Event.sudo().search_count(
            expression.AND([published_domain, [('active', '=', True), ('stage_id', 'in', public_stage_ids['live'] or [0])]])
        )
        
        past_count = Event.sudo().search_count(
            expression.AND([published_domain, [('active', '=', True), ('stage_id', 'in', public_stage_ids['past'] or [0])]])
        )
        
        # Build dates list in the format Odoo expects: [id, name, date_begin, event_count]
        # The template expects tuples with 4 elements
        dates = [
            ('all', 'All Events', False, all_count),
            ('upcoming', 'Upcoming Events', False, upcoming_count),
            ('old', 'Past Events', False, past_count),
        ]
        
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
            'current_availability': current_availability,
            'availability_filters': [
                {
                    'key': key,
                    'label': label,
                    'event_count': availability_counts.get(key, 0),
                }
                for key, label in availability_options
            ],
            'availability_labels': availability_labels,
            'current_country': '',  # (only used by the stock topbar)
            # add these two to stay API-compatible with the base template,
            # even if your custom topbar uses different names:
            'types': event_types,             # stock expects "types"
            'event_types': event_types,
            'countries': [],                  # stock expects "countries"

            'dates': dates,
            'keep': keep,
            'tags': [],
        }
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
        lines = []
        total_points = 0
        points_by_ticket = {}
        for ticket in event_tickets:
            qty = int(registration_tickets.get(ticket.id, 0))
            unit_points = int(getattr(ticket, 'point_cost', 0) or 0)
            line_points = unit_points * qty
            total_points += line_points
            points_by_ticket[ticket.id] = unit_points
            lines.append({
                'ticket_id': ticket.id,
                'name': ticket.name,
                'qty': qty,
                'unit_points': unit_points,
                'line_points': line_points,
            })
        return {
            'lines': lines,
            'registration_tickets': registration_tickets,
            'event_tickets': event_tickets,
            'total_points': total_points,
            'points_by_ticket': points_by_ticket,
        }

    def _payment_session_key(self, event):
        return f"event_registration_payment_{event.id}"

    @http.route(['/event/<model("event.event"):event>/registration/new'], type='json', auth="public", methods=['POST'], website=True)
    def registration_new(self, event, **post):
        if request.env.user._is_public():
            return request.env['ir.ui.view']._render_template(
                'event_application.registration_login_required_modal',
                {'event': event},
            )
        return super().registration_new(event, **post)

    @http.route(['/event/<model("event.event"):event>/registration/payment'], type='http', auth="public", methods=['GET', 'POST'], website=True)
    def registration_payment(self, event, **post):
        if request.env.user._is_public():
            return request.redirect('/web/login?redirect=/event/%s/register' % event.id)
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
        existing_regs = request.env['event.registration'].sudo().with_context(active_test=False).search([
            ('x_register_batch_id', '=', payload.get('batch_id')),
        ], limit=1) if payload.get('batch_id') and 'x_register_batch_id' in request.env['event.registration']._fields else False
        if existing_regs:
            return request.redirect(
                ('/event/%s/registration/success?' % event.id) + url_encode({
                    'registration_ids': ",".join([str(rid) for rid in existing_regs.search([('x_register_batch_id', '=', payload.get('batch_id'))]).ids]),
                })
            )

        summary = self._registration_invoice_summary(payload['registration_data'])
        if any(ticket.seats_limited and ticket.seats_available < summary['registration_tickets'].get(ticket.id) for ticket in summary['event_tickets']):
            return request.redirect('/event/%s/register?registration_error_code=insufficient_seats' % event.id)

        if 'point_cost' not in request.env['event.event.ticket']._fields:
            raise UserError('Point system is not configured for event tickets.')

        total_points = summary['total_points']

        try:
            request.session.pop(key, None)
            if request.env.user._is_public():
                request.session[key] = payload
                return request.redirect('/web/login?redirect=/event/%s/registration/payment' % event.id)

            wallet = self._get_points_wallet()
            if wallet:
                if total_points > 0 and wallet.balance < total_points:
                    request.session[key] = payload
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

            if not request.env.user._is_public():
                request.env.user.partner_id.sudo().write({
                    'name': payload['buyer_name'],
                    'email': payload['buyer_email'],
                    'phone': payload['buyer_phone'],
                })

            attendees_sudo = self._create_attendees_from_registration_post(event, payload['registration_data'])
            attendee_update_vals = {}
            if not request.env.user._is_public() and 'partner_id' in attendees_sudo._fields:
                attendee_update_vals['partner_id'] = request.env.user.partner_id.id
            if 'points_spent' in attendees_sudo._fields:
                for attendee in attendees_sudo:
                    vals = dict(attendee_update_vals)
                    vals['points_spent'] = summary['points_by_ticket'].get(attendee.event_ticket_id.id, 0)
                    if vals:
                        attendee.sudo().write(vals)
            elif attendee_update_vals:
                attendees_sudo.sudo().write(attendee_update_vals)
            registration_ids_csv = ",".join([str(rid) for rid in attendees_sudo.ids])
        except Exception:
            request.session[key] = payload
            raise

        try:
            report_xmlid = "event.action_report_event_registration_full_page_ticket"
            report_id = request.env["ir.model.data"].sudo()._xmlid_to_res_id(
                report_xmlid, raise_if_not_found=False
            )
            report = request.env["ir.actions.report"].sudo().browse(report_id) if report_id else False
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
                    "res_id": request.env.user.partner_id.id if not request.env.user._is_public() else False,
                })
        except Exception:
            _logger.exception("Ticket PDF generation skipped due to access/processing error.")

        return request.redirect(('/event/%s/registration/success?' % event.id) + url_encode({'registration_ids': registration_ids_csv}))

    @http.route(['''/event/<model("event.event"):event>/registration/confirm'''], type='http', auth="public", methods=['POST'], website=True)
    def registration_confirm(self, event, **post):
        # Backward compatibility: old confirm endpoint now routes to payment review.
        return self.registration_payment(event, **post)

        
