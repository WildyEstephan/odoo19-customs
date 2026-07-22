
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class Partner(models.Model):
    _inherit = "res.partner"

    res_municipality_id = fields.Many2one('res.municipality', 'Municipality', domain="[('state_id', '=', state_id)]")

    @api.onchange("res_municipality_id")
    def onchange_municipality(self):
        self.city = self.res_municipality_id.name
