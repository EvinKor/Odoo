from odoo import models, fields

class OidcAccessToken(models.Model):
    _name = "oidc.access.token"
    _description = "OIDC Access Token"
    _order = "create_date desc"

    token = fields.Char(required=True, index=True)
    user_id = fields.Many2one("res.users", required=True, index=True)
    client_id = fields.Char(required=True, index=True)
    scope = fields.Char(default="openid email profile")
    expires_at = fields.Datetime(required=True, index=True)
