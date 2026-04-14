{
    'name': 'Event Application',
    'version': '1.0',
    'category': 'Website',
    'summary': 'Allow users to submit event applications from the frontend',
    'description': """
        Event Application Module
        ========================
        Allows portal users to submit event applications that can be approved by administrators.
    """,
    'depends': ['base', 'website', 'portal', 'event', 'website_event', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/event_application_security.xml',
        'data/specialty_data.xml',
        'data/case_data.xml',
        'wizard/reject_application_wizard_views.xml',
        'wizard/delete_event_wizard_views.xml',
        'wizard/event_stage_reschedule_wizard_views.xml',
        'views/event_application_views.xml',
        'views/event_settings_views.xml',
        'views/event_points_views.xml',
        'views/event_reviews_views.xml',
        'views/event_event_kanban_inherit.xml',
        'views/event_event_form_address_context.xml',
        'views/event_registration_backend_views.xml',
        'views/portal_templates.xml',
        'views/event_website_templates.xml',
        'views/event_gallery_section.xml',
        'views/event_two_column_cleanup.xml',
        'views/event_filters_labels.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'event_application/static/src/js/event_kanban_stage_reschedule_patch.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
