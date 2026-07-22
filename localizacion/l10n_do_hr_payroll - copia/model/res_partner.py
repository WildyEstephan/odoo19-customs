
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ResBank(models.Model):
    _inherit = 'res.bank'

    bank_code = fields.Char()
    bank_digi = fields.Char()


class ResCompany(models.Model):
    _inherit = 'res.partner.bank'

    account_type = fields.Selection([
        ('CC', 'Cuenta Corriente'),
        ('CA', 'Cuenta de Ahorro'),
    ], string='Account Type', default='CA')

    electronic_payroll_type = fields.Selection([
        ('BHD', 'Banco BHD'),
        ('BPD', 'Banco Popular'),
        ('BDR', 'Banco Reservas'),
        ('SCB', 'ScotianBank'),
        ('BC', 'Banco Caribe'),
    ], string='Electroni Payroll'
    )
    electronic_payroll_email = fields.Char(string='Email Payroll')
    electronic_payroll_bank_code = fields.Char(string='Bank Code')
    electronic_payroll_bank_account_id = fields.Many2one('res.partner.bank', string='Bank Account')