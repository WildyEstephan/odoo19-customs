
from odoo import api, fields, models


class WorkingHoursImport(models.Model):
    _name = 'working.hours.import'
    _description = 'Importacion de horas trabajadas de los emprleados'

    name = fields.Char(compute='_compute_name')
    # _sql_constraints = [('hours_check',
    #                      'CHECK((hours_amount >= 0 and extra_hours_amount > 0) or'
    #                      ' (extra_hours_amount >= 0 and hours_amount > 0))',
    #                      'El la cantidad de horas debe ser mayor a 0!')]

    employee_id = fields.Many2one('hr.employee', string="Empleado", required=True)
    # MODIFICADO: Arturo Diaz Lora - 2026-03-14 10:00
    # Razón: Agregar company_id related para soporte multi-company
    company_id = fields.Many2one('res.company', related='employee_id.company_id', store=True, index=True)
    # employee_code = fields.Char(string="Código de empleado", required=True)
    # hours_code = fields.Selection([('HE15', 'Horas Extras al 15%'),
    #                                ('HE35', 'Horas Extras al 35%'),
    #                                ('HE50', 'Horas Extras al 50%'),
    #                                ('HE100', 'Horas Extras al 100%')],
    #                                default='HE35', string="Código de horas extras", required=True)

    date_from = fields.Date(string="Fecha desde", required=True)
    date_to = fields.Date(string="Fecha hasta", required=True)
    hours_amount = fields.Float(string="Horas normales")
    extra_hours_amount_15 = fields.Float(string="Horas extras 15%")
    extra_hours_amount_35 = fields.Float(string="Horas extras 35%")
    extra_hours_amount_50 = fields.Float(string="Horas extras 50%")
    holiday_hours_amount = fields.Float(string="Horas feriadas")
    free_days = fields.Float(string="Horas Libres")

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_name(self):
        """
        Este funcion genera el nombre por defecto
        del registro de importacion de horas trabajadas.
        """
        for rec in self:
            rec.name = "Horas: {0}/{1} - {2}".format(rec.employee_id.name, rec.date_from, rec.date_to)


