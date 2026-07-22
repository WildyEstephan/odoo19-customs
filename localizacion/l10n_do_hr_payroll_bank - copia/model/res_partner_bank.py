# -*- encoding: utf-8 -*-
from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = 'res.partner.bank'

    account_type = fields.Selection([
        ('CC', 'Cuenta Corriente'),
        ('CA', 'Cuenta de Ahorro'),
    ], string='Account Type', default='CA')

    electronic_payroll_type = fields.Selection([
        ('BHD', 'Banco BHD'),
        ('BPD', 'Banco Popular'),
        ('BHL', 'Banco Lopez de Haro'),
        ('BDR', 'Banco Reservas'),
        ('BC', 'Banco Caribe'),
    ], string='Electroni Payroll'
    )
    electronic_payroll_email = fields.Char(string='Email Payroll')
    electronic_payroll_bank_code = fields.Char(string='Bank Code')
    electronic_payroll_bank_account_id = fields.Many2one('res.partner.bank', string='Bank Account')
    
    # Override del campo allow_out_payment para que sea True por defecto
    allow_out_payment = fields.Boolean('Enviar Dinero', help='Esta cuenta puede ser utilizada para pagos salientes', default=True, copy=False, readonly=False)
