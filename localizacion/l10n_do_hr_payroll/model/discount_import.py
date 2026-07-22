
from odoo import fields, models


class PayrollDiscountConfig(models.Model):
    _name = 'payroll.discount.config'
    _description = "Modelo para configurar los codigos de los descuentos en la nomina de empleados"
    _rec_name = 'name'

    _unique_input_rel = models.Constraint(
        'UNIQUE(code_rel)',
        'Solo puede tener una configuración por descuento!',
    )

    name = fields.Char(string="Nombre", required=True)
    code_rel = fields.Many2one('hr.payslip.input.type', required=True)
    code = fields.Char(related='code_rel.code', string="Discount Code", store=True)
    active = fields.Boolean(default=True, string="Active")
    # MODIFICADO: Arturo Diaz Lora - 2026-03-14 10:00
    # Razón: Agregar company_id para soporte multi-company
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)


class PayrollDiscountImport(models.Model):
    _name = 'payroll.discount.import'
    _description = "Modelo para cargar los descuentos de nomina a los empleados"

    _amount_check = models.Constraint(
        'CHECK(amount > 0)',
        'El monto debe ser mayor a 0!',
    )

    employee_id = fields.Many2one('hr.employee', string="Empleado", required=True)
    # MODIFICADO: Arturo Diaz Lora - 2026-03-14 10:00
    # Razón: Agregar company_id related para soporte multi-company
    company_id = fields.Many2one('res.company', related='employee_id.company_id', store=True, index=True)
    date_from = fields.Date(string="Fecha desde", required=True)
    date_to = fields.Date(string="Fecha hasta", required=True)
    discount_code = fields.Char(string="Código de descuento", required=True)
    amount = fields.Float(string="Monto", required=True)
