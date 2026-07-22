import itertools
import pytz

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

from collections import defaultdict
from datetime import datetime, date, time
from dateutil.relativedelta import relativedelta


class payrolltype(models.Model):

    _name = 'hr.contract.payrolltype'
    _description = 'Payroll Type'
    _order = 'sequence, id'

    name = fields.Char(string='Payroll Type', required=True, translate=True)
    sequence = fields.Char(help="Create a New Payroll Type With '002'.", max=3)
    # MODIFICADO: Arturo Diaz Lora - 2026-03-14 10:00
    # Razón: Agregar company_id para soporte multi-company (opcional para tipos compartidos)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    _unique_payrolltype_sequence = models.Constraint(
        'UNIQUE(sequence)',
        'This Payroll Type is already registered!',
    )

    def _valid_field_parameter(self, field, name):
        return name == 'max' or super(payrolltype, self)._valid_field_parameter(field, name)


class HrVersion(models.Model):
    """This Will add some information needed on the version (employee contract) for Dominican Republic"""

    _inherit = "hr.version"

    # Campos de solo lectura - calculados desde structure_type_id
    schedule_form_pay = fields.Selection(
        string='Schedule Pay',
        related='structure_type_id.default_schedule_pay',
        required=True, readonly=True)

    # Override para hacer readonly los campos de hr_payroll
    schedule_pay = fields.Selection(readonly=True)
    wage_type = fields.Selection(readonly=True)

    # Agregar opción de importación de horas al work_entry_source
    # Default: Asistencias (attendance)
    work_entry_source = fields.Selection(
        selection_add=[('import_hours', 'Importacion Horas')],
        ondelete={'import_hours': 'set default'},
        default='attendance',
    )

    # Valores por defecto para campos del contrato
    # Default: Permanente
    contract_type_id = fields.Many2one(
        default=lambda self: self._get_default_contract_type())

    # Default: Empleado Fijo (Salario)
    structure_type_id = fields.Many2one(
        default=lambda self: self._get_default_structure_type())

    @api.model
    def _get_default_contract_type(self):
        """Retorna el tipo de contrato 'Permanent' por defecto"""
        return self.env['hr.contract.type'].search([
            ('name', 'ilike', 'Permanent')
        ], limit=1)

    @api.model
    def _get_default_structure_type(self):
        """Retorna la categoría de pago 'Empleado Fijo (Salario)' por defecto"""
        # Buscar primero por nombre exacto, luego por coincidencia parcial
        structure = self.env['hr.payroll.structure.type'].search([
            ('name', 'ilike', 'Empleado Fijo (Salario)')
        ], limit=1)
        if not structure:
            structure = self.env['hr.payroll.structure.type'].search([
                ('name', 'ilike', 'Empleado Fijo')
            ], limit=1)
        return structure

    # Campos específicos de República Dominicana
    # MODIFICADO: Arturo Diaz Lora - 2026-03-18 23:00
    # Razón: Agregar default=True a deduction_plan y default="both_month" a scheduled_retentions
    # Código original: deduction_plan sin default, scheduled_retentions sin default
    deduction_plan = fields.Boolean(string="Monthly Deduction?", default=True)
    scheduled_retentions = fields.Selection([
        ("both_month", "Distribuidas"),
        ("start_month", "A inicio de Mes"),
        ("end_month", "Al Fin de Mes")],
        string="Retenciones De Ley",
        default="both_month",
    )
    comission_rate = fields.Integer(
        string="% de comisión", help="Este porcentaje se calculará en base a todas las facturas pagadas en las que el empleado es vendedor.")
    assurance_amount = fields.Float(string="Monto seguro complementario", default=0.0)
    is_foreign = fields.Boolean(string="Es Extranjero", default=False)
    # identification_id ya existe en hr.version base, no redefinir
    allow_accumulation = fields.Boolean(
        string="Permitir Acomulacion TSS, DGII?", default=True)
    retencion_unico = fields.Boolean(string="Labora en Otra Empresa?")
    rnc_retencion_unico = fields.Many2one(
        "res.partner", string="RNC Agente De Retención Único")
    remuneracion = fields.Float(string="Remuneraciones En Otra Empresa")
    payment_day = fields.Float(string="Pagos por Dias", default=23.83, groups='hr.group_hr_user')
    hourly_payment = fields.Boolean(string='Pago por hora')
    wage_extra_hour = fields.Monetary(string="Pago horas extras", groups='hr.group_hr_user')
    dieta_amount = fields.Monetary('Dieta', digits=(16, 2), help="Dieta de Empleado.")
    wage_extra_labol = fields.Monetary('Pago Horas Operario', digits=(16, 2), groups='hr.group_hr_user')
    free_days = fields.Monetary('Pago Horas Libres', digits=(16, 2), groups='hr.group_hr_user')
    wage_holidays_hour = fields.Monetary(string="Pago horas Dias Feriados", groups='hr.group_hr_user')
    fixed_loan = fields.Monetary(string="Cuota fija quincenal de préstamo")
    amount_saved = fields.Monetary(string="Cuota de ahorro quincenal")

    income_type = fields.Selection([
        ("0001", "Normal"),
        ("0002", "Trabajador Ocasional (No Fijo)"),
        ("0003", "Asalariado Por Hora o Labora Tiempo Parcial"),
        ("0004", "No laboró Mes Completo Por Razones Varias"),
        ("0005", "Salario Prorrateado Semanal/Bisemanal"),
        ("0006", "Pensionado Antes De La Ley 87-01"),
        ("0007", "Exento por Ley de pago al SDSS"),
        ("0008", "Trabajador con salario sectorizado")],
        string='Income Type', default='0001',
        help="Defines The Income Type as TSS", required=True)

    payrolltype_id = fields.Many2one('hr.contract.payrolltype', string="Payroll Type", required=True,
                                     default=lambda self: self.env['hr.contract.payrolltype'].search([], limit=1))

    def _valid_field_parameter(self, field, name):
        return name == 'digits' or super(HrVersion, self)._valid_field_parameter(field, name)

    @api.constrains("rnc_retencion_unico", "remuneracion", "retencion_unico")
    def validate_external_partner(self):
        if self.retencion_unico:
            if self.remuneracion <= 0:
                raise ValidationError(_(
                    u"Remuneración Menor 0.00\n\n"
                    u"Favor Colocar el Monto De La Remuneracion de la "
                    u"Otra Empresa para la planilla de TSS"))

            if not self.rnc_retencion_unico.vat:
                raise ValidationError(_(
                    u"RNC Agente de Retención Único sin RNC/Céd\n\n"
                    u"*{}* no tiene RNC o Cédula y es requerido "
                    u"para la planilla de TSS")
                    .format(self.rnc_retencion_unico.name))
