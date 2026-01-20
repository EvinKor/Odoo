{
    "name": "Odoo JWT Auth",
    "version": "1.0",
    "summary": "JWT authentication API",
    "category": "Tools",
    "depends": ["base"],
    "data": [
        "views/res_users_view.xml",  # <-- add this line
    ],
    "installable": True,
    "application": False,
}

