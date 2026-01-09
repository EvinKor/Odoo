import requests
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[("2c2p", "2C2P")],
        ondelete={"2c2p": "cascade"},  # ✅ delete provider records created for 2C2P when uninstalling
    )

    # Config fields (you can rename to match your 2C2P account)
    _2c2p_merchant_id = fields.Char(string="2C2P Merchant ID", required_if_provider="2c2p")
    _2c2p_secret_key = fields.Char(string="2C2P Secret Key", required_if_provider="2c2p", groups="base.group_system")
    _2c2p_env = fields.Selection(
        [("sandbox", "Sandbox"), ("production", "Production")],
        string="2C2P Environment",
        default="sandbox",
        required_if_provider="2c2p",
    )

    def _2c2p_base_url(self):
        self.ensure_one()
        # Based on your screenshot endpoint style (sandbox-pgw.2c2p.com)
        if self._2c2p_env == "sandbox":
            return "https://sandbox-pgw.2c2p.com"
        return "https://pgw.2c2p.com"

    def _get_supported_currencies(self):
        """Optional: restrict currencies to those enabled in your 2C2P account."""
        res = super()._get_supported_currencies()
        if self.code != "2c2p":
            return res
        # Example: allow all already in res, or filter:
        return res

    def _get_default_payment_method_codes(self):
        """Tell Odoo which payment method(s) to display under this provider."""
        res = super()._get_default_payment_method_codes()
        if self.code != "2c2p":
            return res
        return res + ["card"]  # or your own method codes if you add them
