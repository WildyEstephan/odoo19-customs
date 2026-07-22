##############################################################################
# Copyright (c) 2015-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# See LICENSE file for full copyright and licensing details.
# License URL : <https://store.webkul.com/license.html/>
##############################################################################

import logging
_logger = logging.getLogger(__name__)

# 2 :  imports of odoo [Imports of odoo]

import odoo
from odoo import api, fields, models, _  # alphabetically ordered
from odoo.tools.translate import _
from odoo.exceptions import UserError, ValidationError

class BankChequeAttributeLine(models.Model):
    # Private attributes
    _name = 'bank.cheque.attribute.line'
    _description = 'Cheque Attribute Line'

    name = fields.Many2one("bank.cheque.attribute",
                           string='Nombre',
                           required=True)
    bank_cheque_id = fields.Many2one("check.report.config",
                                     string='Bank Cheque',
                                     required=True)
    company_id = fields.Many2one('res.company', related='bank_cheque_id.company_id', store=True, index=True)
    font_size = fields.Integer(string='Letras Size', default=15)
    font_family = fields.Char(string='Tipo de Letras')
    letter_spacing = fields.Float(string='Espacios Letras', default=0)
    top_displacement = fields.Float(string='Arriba', digits=(12,1))
    left_displacement = fields.Float(string='Izquierda', digits=(12,1))
    bottom_displacement = fields.Float(string='Debajo', digits=(12,1))
    right_displacement = fields.Float(string='Derecha', digits=(12,1))
    height = fields.Float(string='Altura', digits=(12,1))
    width = fields.Float(string='Ancho', digits=(12,1))

    def reset_values(self):
        for obj in self:
            obj.write({
                "top_displacement": 0,
                "left_displacement": 0,
                "bottom_displacement": 0,
                "right_displacement": 0,
                "height": 0,
                "width": 0,
            })

    @api.onchange("name")
    def onchange_name(self):
        if self.name and self.name.attribute == "amount_box" and not self.font_size:
            self.font_size = 18
                
        if self.name and self.name.attribute == "cheque_date" and not self.letter_spacing or not self.font_size:
            self.letter_spacing = 8
            self.font_size = 16
        



class BankChequeAttribute(models.Model):
    # Private attributes
    _name = 'bank.cheque.attribute'
    _description = 'Atributos de Cheques'

    name = fields.Char(string='Name', required=True)
    # MODIFICADO: Arturo Diaz Lora - 2026-03-14 10:00
    # Razón: Agregar company_id para soporte multi-company (opcional, datos de referencia)
    company_id = fields.Many2one('res.company')
    attribute = fields.Selection(
        [('cheque_date', "Fecha"),
         ('pay_line1', "Pagar a"),
         ('pay_line2', "Pagar a 2"),
         ('amount_line_1', "Monto 1 (En Palabras)"),
         ('amount_line_2', "Monto 1 (En Palabras)"),
         ('amount_box', "Monto"),
         ('account_number', "Numero de Cuenta"),
         ('ref', "Concepto"),
         ('ac_pay', "Etique de Pagado")],
        required=True)
    demo_data = fields.Char("Demo Data For Preview")
    demo_data_date = fields.Date("Demo Date For Preview",
                                 default=fields.Date.today())
    date_format = fields.Selection([("ddMMyyyy", "DD MM YYYY"),
                                    ("MMddyyyy", "MM DD YYYY"),
                                    ("MM", "MM"),
                                    ("dd", "DD"), 
                                    ("yyyy", "YY")],
                                   "Formato de Fecha",
                                   default="ddMMyyyy")