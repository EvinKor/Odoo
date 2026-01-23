from odoo import models, fields

class OidcAuthCode(models.Model):
    _name = "oidc.auth.code"
    _description = "OIDC Authorization Code"
    _order = "create_date desc"

    code = fields.Char(required=True, index=True)
    user_id = fields.Many2one("res.users", required=True, index=True)
    client_id = fields.Char(required=True, index=True)
    redirect_uri = fields.Char(required=True)
    code_challenge = fields.Char(required=True)
    code_challenge_method = fields.Char(required=True, default="S256")
    nonce = fields.Char()
    state = fields.Char()
    expires_at = fields.Datetime(required=True, index=True)
    used_at = fields.Datetime(index=True)
