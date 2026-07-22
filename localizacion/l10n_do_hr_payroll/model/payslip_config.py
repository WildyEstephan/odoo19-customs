
from odoo import models, fields, api, _
from odoo.exceptions import UserError

SELECT = [
    ("IN", "Ingreso"),
    ("SA", "Salida"),
    ("VC", "Vacaciones"),
    ("LM", "Licencia Por Maternidad"),
    ("LV", "Licencia Voluntaria"),
    ("LD", "Licencia Discapacidad"),
    ("AD", "Actualizacion de datos del trabajador"),
    ]


class HRPayslipLine(models.Model):
    """docstring for HRSalaryRule"""

    _inherit = "hr.payslip.line"

    is_news = fields.Boolean(string="Novedad")
    type_news = fields.Selection(selection=SELECT, string="Tipo De Novedad")


class HRPayslipConfig(models.Model):
    _name = "hr.payslip.config"
    _description = "HR Payslip Configuration"

    # MODIFICADO: Arturo Diaz Lora - 2026-03-14 10:00
    # Razón: Agregar company_id para soporte multi-company
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    last_payroll_day = fields.Integer(
        string="Last payroll day",
        help="Coloque aquí el día del mes en que se realiza el último pago de nómina",
    )
    quotation_calculation_ids = fields.One2many(
        comodel_name="hr.quotation.calculation",
        inverse_name="payslip_config_id",
        string="Quotation Calculation",
    )
    retention_scale_ids = fields.One2many(
        comodel_name="hr.retention.scale",
        inverse_name="payslip_config_id",
        string="Retention Scale",
    )

    # @api.model
    # def create(self, values):
    #     config = self.env.ref('l10n_do_salary_rule.hr_payslip_config_1')
    #     return config

    @api.constrains("last_payroll_day")
    def _check_last_payroll_day(self):
        for payslip_config in self:
            lpday = payslip_config.last_payroll_day
            if lpday < 10 or lpday > 27:
                raise UserError(_("Debe colocar una fecha válida, entre 10 y 30."))


class HRQuotationCalculation(models.Model):
    """docstring for HRQuotationCalculation"""

    _name = "hr.quotation.calculation"
    _description = "HR Quotation Calculation"

    name = fields.Char(string="Concept")
    value = fields.Float(string="Value")
    retention = fields.Float(string="Retention")
    code = fields.Char(string="Code", required=True)
    contrib = fields.Float(string="Contrib", required=True)
    payslip_config_id = fields.Many2one(
        comodel_name="hr.payslip.config", string="Payslip Config"
    )
    # MODIFICADO: Arturo Diaz Lora - 2026-03-14 10:00
    # Razón: Agregar company_id related para soporte multi-company
    company_id = fields.Many2one('res.company', related='payslip_config_id.company_id', store=True, index=True)


class HRRetentionScale(models.Model):
    """docstring for HRRetentionScale"""

    _name = "hr.retention.scale"
    _description = "HR Retention Scale"

    code = fields.Char(string="Code", required=True)
    exempt = fields.Boolean(string="Exempt")
    name = fields.Char(string="Annual Scale")
    percent = fields.Integer(string="Percent")
    sequence = fields.Integer(string="Sequence")
    top_amount = fields.Float(string="Top Amount")
    base_amount = fields.Float(string="Base Amount")
    extra_amount = fields.Float(string="Extra Amount")
    payslip_config_id = fields.Many2one(
        comodel_name="hr.payslip.config", string="Payslip Config"
    )
    # MODIFICADO: Arturo Diaz Lora - 2026-03-14 10:00
    # Razón: Agregar company_id related para soporte multi-company
    company_id = fields.Many2one('res.company', related='payslip_config_id.company_id', store=True, index=True)