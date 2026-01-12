from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def name_get(self):
        if self.env.context.get("show_address_only"):
            result = []
            for partner in self:
                name = partner.name or ""
                address = (partner._display_address(without_company=True) or "").strip()
                if name and address:
                    display = f"{name}\n{address}"
                else:
                    display = name or address
                result.append((partner.id, display))
            return result
        return super().name_get()
