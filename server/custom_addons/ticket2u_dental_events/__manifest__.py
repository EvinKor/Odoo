{
    "name": "Ticket2U Dental Events",
    "version": "1.0.0",
    "summary": "Dental event submission, approvals, points, and notifications",
    "category": "Website",
    "depends": ["base", "mail", "portal", "website", "event", "website_event"],
    "data": [
        "security/ir.model.access.csv",
        "security/dental_security.xml",
        "data/dental_config_data.xml",
        "views/dental_event_submission_views.xml",
        "views/dental_points_views.xml",
        "views/dental_notification_views.xml",
        "views/dental_portal_templates.xml",
        "views/dental_website_templates.xml"
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3"
}
