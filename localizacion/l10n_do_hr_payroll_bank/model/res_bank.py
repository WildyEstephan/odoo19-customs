# -*- encoding: utf-8 -*-
from odoo import models, fields, api


class ResBank(models.Model):
    _inherit = 'res.bank'

    bank_code = fields.Char()
    bank_digi = fields.Char()
