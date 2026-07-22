# -*- encoding: utf-8 -*-
from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    electronic_payroll_email = fields.Char(readonly=False)
    electronic_payroll_bank_code = fields.Char(readonly=False)
    electronic_payroll_bank_account_id = fields.Many2one(
        'res.partner.bank', readonly=False
    )
