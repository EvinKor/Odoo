from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class DentalPointsWallet(models.Model):
    _name = "dental.points.wallet"
    _description = "Dental Points Wallet"

    partner_id = fields.Many2one("res.partner", required=True, ondelete="cascade", index=True)
    transaction_ids = fields.One2many("dental.points.transaction", "wallet_id")
    balance = fields.Integer(compute="_compute_balance", store=True)

    _sql_constraints = [
        ("wallet_partner_unique", "unique(partner_id)", "A wallet already exists for this partner."),
    ]

    @api.depends("transaction_ids.amount")
    def _compute_balance(self):
        for wallet in self:
            wallet.balance = sum(wallet.transaction_ids.mapped("amount"))

    @api.model
    def get_or_create_wallet(self, partner):
        # Portal/internal users can only bootstrap their own wallet.
        if not self.env.user.has_group("base.group_system") and partner.id != self.env.user.partner_id.id:
            raise AccessError(_("You can only access your own wallet."))
        wallet = self.sudo().search([("partner_id", "=", partner.id)], limit=1)
        if not wallet:
            wallet = self.sudo().create({"partner_id": partner.id})
        return wallet

    def add_points(self, amount, reason, reference=None):
        self.ensure_one()
        if not self.env.user.has_group("base.group_system") and self.partner_id.id != self.env.user.partner_id.id:
            raise AccessError(_("You can only modify your own wallet."))
        if amount <= 0:
            raise ValidationError(_("Add points amount must be positive."))
        return self.env["dental.points.transaction"].sudo().create({
            "wallet_id": self.id,
            "partner_id": self.partner_id.id,
            "amount": amount,
            "reason": reason,
            "reference": reference,
            "transaction_type": "credit",
        })

    def spend_points(self, amount, reason, reference=None):
        self.ensure_one()
        if not self.env.user.has_group("base.group_system") and self.partner_id.id != self.env.user.partner_id.id:
            raise AccessError(_("You can only modify your own wallet."))
        if amount <= 0:
            raise ValidationError(_("Spend points amount must be positive."))
        if self.balance < amount:
            raise ValidationError(_("Insufficient points. Required: %s, Available: %s") % (amount, self.balance))
        return self.env["dental.points.transaction"].sudo().create({
            "wallet_id": self.id,
            "partner_id": self.partner_id.id,
            "amount": -amount,
            "reason": reason,
            "reference": reference,
            "transaction_type": "debit",
        })


class DentalPointsTransaction(models.Model):
    _name = "dental.points.transaction"
    _description = "Dental Points Transaction"
    _order = "create_date desc, id desc"

    wallet_id = fields.Many2one("dental.points.wallet", required=True, ondelete="cascade")
    partner_id = fields.Many2one("res.partner", required=True, index=True)
    amount = fields.Integer(required=True)
    transaction_type = fields.Selection([
        ("credit", "Credit"),
        ("debit", "Debit"),
    ], required=True)
    reason = fields.Char(required=True)
    reference = fields.Char()

    @api.onchange("wallet_id")
    def _onchange_wallet_id(self):
        for rec in self:
            if rec.wallet_id:
                rec.partner_id = rec.wallet_id.partner_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            wallet_id = vals.get("wallet_id")
            if wallet_id:
                wallet = self.env["dental.points.wallet"].browse(wallet_id)
                if wallet.exists():
                    vals["partner_id"] = wallet.partner_id.id
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("wallet_id"):
            wallet = self.env["dental.points.wallet"].browse(vals["wallet_id"])
            if wallet.exists():
                vals["partner_id"] = wallet.partner_id.id
        return super().write(vals)
