from odoo import http
from odoo.http import request

class TwoC2PController(http.Controller):

    @http.route("/payment/2c2p/return", type="http", auth="public", methods=["GET", "POST"], csrf=False, save_session=False)
    def two_c2p_return(self, **kwargs):
        """Customer browser returns here after payment."""
        # Usually: show “processing” then rely on webhook, or also process return payload.
        # Best practice: treat return as UX, webhook as source of truth.
        return request.redirect("/payment/status")

    @http.route("/payment/2c2p/webhook", type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def two_c2p_webhook(self, **kwargs):
        """2C2P server-to-server notification."""
        # Depending on 2C2P, data may come as JSON body or form params.
        notification = request.httprequest.get_json(silent=True) or kwargs

        # Find the transaction. Use reference you sent (invoiceNo / merchant ref).
        reference = (
            notification.get("invoiceNo")
            or notification.get("merchantTransactionID")
            or notification.get("orderNo")
        )

        tx = request.env["payment.transaction"].sudo().search([("reference", "=", reference)], limit=1)
        if not tx:
            return "NOT FOUND"

        # Let Odoo’s payment.transaction handle mapping/validation via a dedicated method
        tx._handle_2c2p_notification(notification)

        return "OK"
