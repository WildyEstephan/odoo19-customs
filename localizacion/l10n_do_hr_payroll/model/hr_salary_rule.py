
from odoo import models, fields


SELECT = [
    ("IN", "Ingreso"),
    ("SA", "Salida"),
    ("VC", "Vacaciones"),
    ("LM", "Licencia Por Maternidad"),
    ("LV", "Licencia Voluntaria"),
    ("LD", "Licencia Discapacidad"),
    ("AD", "Actualizacion de datos del trabajador"),
    ]


class HRSalaryRule(models.Model):
    """docstring for HRSalaryRule"""

    _inherit = "hr.salary.rule"

    is_news = fields.Boolean(string="Is News")
    type_news = fields.Selection(selection=SELECT, string="Tipo de novedad")
    
    account_debit = fields.Many2one('account.account', 'Cuenta Deudora',
                                    domain=[('deprecated', '=', False)], company_dependent=True )
    account_credit = fields.Many2one('account.account', 'Cuenta Acreedora',
                                     domain=[('deprecated', '=', False)], company_dependent=True)