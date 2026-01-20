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
        'data/specialty_data.xml',
        'data/case_data.xml',
        'wizard/reject_application_wizard_views.xml',
        'views/event_application_views.xml',
        'views/event_reviews_views.xml',
        'views/event_website_templates.xml',
        'views/event_event_kanban_inherit.xml',
        'views/event_event_form_address_context.xml',
        'views/portal_templates.xml'
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
