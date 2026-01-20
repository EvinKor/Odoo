from odoo import models, fields

class ResUsers(models.Model):
    _inherit = "res.users"

    supabase_uid = fields.Char(
        string="Supabase User ID",
        index=True,
        copy=False
    )

