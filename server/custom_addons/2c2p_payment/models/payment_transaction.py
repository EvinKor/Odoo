from odoo import models

class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _handle_2c2p_notification(self, notification):
        self.ensure_one()

        resp_code = notification.get("respCode") or notification.get("responseCode")
        provider_ref = notification.get("transactionID") or notification.get("paymentID")
        if provider_ref:
            self.provider_reference = provider_ref

        if resp_code == "0000":
            self._set_done()
        elif resp_code in ("0001", "2001"):
            # pending / in progress
            self._set_pending()
        elif resp_code in ("0003",):
            self._set_canceled()
        else:
            # Anything else treat as error
            self._set_error("2C2P payment failed: %s" % resp_code)
