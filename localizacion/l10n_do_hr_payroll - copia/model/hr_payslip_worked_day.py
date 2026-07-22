from odoo import api, fields, models


class HrPayslipWorkedDays(models.Model):
    _inherit = 'hr.payslip.worked_days'

    amount = fields.Float(string="Importe calculado", compute="_compute_amount", store=True)

    @api.depends('is_paid', 'code', 'payslip_id.version_id.wage', 'payslip_id.version_id.schedule_pay')
    def _compute_amount(self):
        for worked_day in self:
            contract = worked_day.payslip_id.version_id

            if not worked_day.is_paid or not contract or worked_day.code != 'WORK100':
                worked_day.amount = 0.0
                worked_day.number_of_hours = worked_day.number_of_days * 8
                continue

            wage = contract.wage or 0.0
            schedule = contract.schedule_pay or 'mensual'

            if schedule in ['quincenal', 'bi-weekly']:
                worked_day.amount = wage / 2
            elif schedule in ['semanal', 'weekly']:
                worked_day.amount = wage / 4
            else:  # mensual u otro
                worked_day.amount = wage

            # Mostrar horas para fines visuales
            worked_day.number_of_hours = worked_day.number_of_days * 8
