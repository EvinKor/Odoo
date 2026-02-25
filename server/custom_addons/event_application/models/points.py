from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class EventPointsWallet(models.Model):
    _name = "event.points.wallet"
    _description = "Event Points Wallet"

    partner_id = fields.Many2one("res.partner", required=True, ondelete="cascade", index=True)
    transaction_ids = fields.One2many("event.points.transaction", "wallet_id")
    balance = fields.Integer(compute="_compute_balance", store=True)

    _sql_constraints = [
        ("wallet_partner_unique", "unique(partner_id)", "A points wallet already exists for this partner."),
    ]

    @api.depends("transaction_ids.amount")
    def _compute_balance(self):
        for wallet in self:
            wallet.balance = sum(wallet.transaction_ids.mapped("amount"))

    @api.model
    def get_or_create_wallet(self, partner):
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
        return self.env["event.points.transaction"].sudo().create({
            "wallet_id": self.id,
            "partner_id": self.partner_id.id,
            "amount": amount,
            "reason": reason,
            "reference": reference,
            "transaction_type": "credit",
        })

    def get_current_balance(self):
        self.ensure_one()
        return int(sum(self.sudo().transaction_ids.mapped("amount")))

    def spend_points(self, amount, reason, reference=None):
        self.ensure_one()
        if not self.env.user.has_group("base.group_system") and self.partner_id.id != self.env.user.partner_id.id:
            raise AccessError(_("You can only modify your own wallet."))
        if amount <= 0:
            raise ValidationError(_("Spend points amount must be positive."))
        current_balance = self.get_current_balance()
        if current_balance < amount:
            raise ValidationError(_("Insufficient points. Required: %s, Available: %s") % (amount, current_balance))
        return self.env["event.points.transaction"].sudo().create({
            "wallet_id": self.id,
            "partner_id": self.partner_id.id,
            "amount": -amount,
            "reason": reason,
            "reference": reference,
            "transaction_type": "debit",
        })


class EventPointsTransaction(models.Model):
    _name = "event.points.transaction"
    _description = "Event Points Transaction"
    _order = "create_date desc, id desc"

    wallet_id = fields.Many2one("event.points.wallet", required=True, ondelete="cascade")
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
                wallet = self.env["event.points.wallet"].browse(wallet_id)
                if wallet.exists():
                    vals["partner_id"] = wallet.partner_id.id
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("wallet_id"):
            wallet = self.env["event.points.wallet"].browse(vals["wallet_id"])
            if wallet.exists():
                vals["partner_id"] = wallet.partner_id.id
        return super().write(vals)
