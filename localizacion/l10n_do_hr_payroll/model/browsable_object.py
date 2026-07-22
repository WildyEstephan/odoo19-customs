
from odoo import fields, models, api

class BrowsableObject(object):
    def __init__(self, employee_id, dict, env):
        self.employee_id = employee_id
        self.dict = dict
        self.env = env
        # Customization to allow changing the behavior of the discrete browsable objects.
        # you can think of this as 'compiling' the query based on the configuration.
        #sum_field = env['ir.config_parameter'].sudo().get_param('hr_payroll.payslip.sum_behavior', 'date_from')
        #if sum_field == 'date' and 'date' not in env['hr.payslip']:
            # missing attribute, closest by definition
        #    sum_field = 'date_to'
        #if not sum_field:
        sum_field = 'date_from'
        self._compile_browsable_query(sum_field)

    def __getattr__(self, attr):
        return attr in self.dict and self.dict.__getitem__(attr) or 0.0

    def _compile_browsable_query(self, sum_field):
        pass


class InputLine(BrowsableObject):
    """a class that will be used into the python code, mainly for usability purposes"""
    def _compile_browsable_query(self, sum_field):
        self.__browsable_query = """
            SELECT sum(amount) as sum
            FROM hr_payslip as hp, hr_payslip_input as pi
            WHERE hp.employee_id = %s AND hp.state in ('validated', 'paid')
            AND hp.{sum_field} >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s""".format(sum_field=sum_field)

    def sum(self, code, from_date, to_date=None):
        if to_date is None:
            to_date = fields.Date.today()
        self.env.cr.execute(self.__browsable_query, (self.employee_id, from_date, to_date, code))
        return self.env.cr.fetchone()[0] or 0.0


class WorkedDays(BrowsableObject):
    """a class that will be used into the python code, mainly for usability purposes"""
    def _compile_browsable_query(self, sum_field):
        self.__browsable_query = """
            SELECT sum(number_of_days) as number_of_days, sum(number_of_hours) as number_of_hours
            FROM hr_payslip as hp, hr_payslip_worked_days as pi
            WHERE hp.employee_id = %s AND hp.state in ('validated', 'paid')
            AND hp.{sum_field} >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s""".format(sum_field=sum_field)

    def _sum(self, code, from_date, to_date=None):
        if to_date is None:
            to_date = fields.Date.today()
        self.env.cr.execute(self.__browsable_query, (self.employee_id, from_date, to_date, code))
        return self.env.cr.fetchone()

    def sum(self, code, from_date, to_date=None):
        res = self._sum(code, from_date, to_date)
        return res and res[0] or 0.0

    def sum_hours(self, code, from_date, to_date=None):
        res = self._sum(code, from_date, to_date)
        return res and res[1] or 0.0


class Payslips(BrowsableObject):
    """a class that will be used into the python code, mainly for usability purposes"""
    def _compile_browsable_query(self, sum_field):
        # Note that the core odoo has this as `hp.credit_note = False` but what if it is NULL?
        # reverse of the desired behavior.
        self.__browsable_query_rule = """
            SELECT sum(case when hp.credit_note is not True then (pl.total) else (-pl.total) end)
            FROM hr_payslip as hp, hr_payslip_line as pl
            WHERE hp.employee_id = %s AND hp.state in ('validated', 'paid')
            AND hp.{sum_field} >= %s AND hp.date_to <= %s AND hp.id = pl.slip_id AND pl.code = %s""".format(sum_field=sum_field)

        # MODIFICADO: Arturo Diaz Lora - 2026-03-30 15:45
        # Razón: Odoo 19 hr_payslip_line no tiene category_id, se accede vía salary_rule_id
        self.__browsable_query_category = """
            WITH RECURSIVE
            category_by_code as (
                SELECT id
                FROM hr_salary_rule_category
                WHERE code = %s
                ),
            category_ids as (
                SELECT COALESCE((SELECT id FROM category_by_code), -1) AS id
                UNION ALL
                SELECT rc.id
                FROM hr_salary_rule_category AS rc
                JOIN category_ids AS rcs ON rcs.id = rc.parent_id
            )

            SELECT sum(case when hp.credit_note is not True then (pl.total) else (-pl.total) end)
            FROM hr_payslip as hp
            JOIN hr_payslip_line as pl ON hp.id = pl.slip_id
            JOIN hr_salary_rule as sr ON pl.salary_rule_id = sr.id
            WHERE hp.employee_id = %s AND hp.state in ('validated', 'paid')
            AND hp.{sum_field} >= %s AND hp.date_to <= %s
            AND sr.category_id in (SELECT id from category_ids)""".format(sum_field=sum_field)

    def sum(self, code, from_date, to_date=None):
        if to_date is None:
            to_date = fields.Date.today()
        self.env.cr.execute(self.__browsable_query_rule, (self.employee_id, from_date, to_date, code))
        res = self.env.cr.fetchone()
        return res and res[0] or 0.0

    def rule_parameter(self, code):
        return self.env['hr.rule.parameter']._get_parameter_from_code(code, self.dict.date_to)

    def sum_category(self, code, from_date, to_date=None):
        if to_date is None:
            to_date = fields.Date.today()

        self.env['hr.payslip'].flush_model(['employee_id', 'state', 'date_from', 'date_to'])
        self.env['hr.payslip.line'].flush_model(['total', 'slip_id', 'salary_rule_id'])
        self.env['hr.salary.rule'].flush_model(['category_id'])
        self.env['hr.salary.rule.category'].flush_model(['code'])
        self.env.cr.execute(self.__browsable_query_category, (code, self.employee_id, from_date, to_date))
        res = self.env.cr.fetchone()
        return res and res[0] or 0.0

    @property
    def paid_amount(self):
        return self.dict._get_paid_amount()

class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    @api.model
    def sum_payslips(self, employee_id):
        payslips = self.search([('employee_id', '=', employee_id)])
        return sum(payslips.mapped('amount_total'))

class HrWorkedDays(models.Model):
    _inherit = 'hr.payslip.worked_days'

    @api.model
    def sum_worked_days(self, employee_id):
        worked_days = self.search([('payslip_id.employee_id', '=', employee_id)])
        return sum(worked_days.mapped('number_of_days'))
    
class HrPayslipSumCategory(models.Model):
    _inherit = 'hr.payslip'

    # MODIFICADO: Arturo Diaz Lora - 2026-03-30 15:30
    # Razón: Corregir firma de sum_category para compatibilidad con Odoo 19 enterprise
    # En Odoo 19, payslip en localdict = self (hr.payslip record), no BrowsableObject
    # Las reglas salariales lo llaman como: payslip.sum_category('ISR', start_date)
    # Código original: @api.model sum_category(self, employee_id, category_code) — firma incorrecta
    def sum_category(self, code, from_date, to_date=None):
        """Suma totales de categoría desde nóminas validadas/pagadas del mismo empleado."""
        self.ensure_one()
        if to_date is None:
            to_date = fields.Date.today()
        self.env['hr.payslip'].flush_model(['employee_id', 'state', 'date_from', 'date_to'])
        self.env['hr.payslip.line'].flush_model(['total', 'slip_id', 'salary_rule_id'])
        self.env['hr.salary.rule'].flush_model(['category_id'])
        self.env['hr.salary.rule.category'].flush_model(['code'])
        # Odoo 19: hr_payslip_line no tiene category_id directo, se accede vía salary_rule_id
        query = """
            WITH RECURSIVE
            category_by_code as (
                SELECT id FROM hr_salary_rule_category WHERE code = %s
            ),
            category_ids as (
                SELECT COALESCE((SELECT id FROM category_by_code), -1) AS id
                UNION ALL
                SELECT rc.id FROM hr_salary_rule_category AS rc
                JOIN category_ids AS rcs ON rcs.id = rc.parent_id
            )
            SELECT sum(case when hp.credit_note is not True then (pl.total) else (-pl.total) end)
            FROM hr_payslip as hp
            JOIN hr_payslip_line as pl ON hp.id = pl.slip_id
            JOIN hr_salary_rule as sr ON pl.salary_rule_id = sr.id
            WHERE hp.employee_id = %s AND hp.state in ('validated', 'paid')
            AND hp.date_from >= %s AND hp.date_to <= %s
            AND sr.category_id in (SELECT id from category_ids)
        """
        self.env.cr.execute(query, (code, self.employee_id.id, from_date, to_date))
        res = self.env.cr.fetchone()
        return res and res[0] or 0.0

    # MODIFICADO: Arturo Diaz Lora - 2026-04-04 04:15
    # Razón: Agregar método sum para sumar por código de REGLA (no categoría)
    # Similar al método sum del Payslips BrowsableObject pero para hr.payslip record
    def sum(self, code, from_date, to_date=None):
        """Suma totales de una regla específica desde nóminas validadas/pagadas del mismo empleado."""
        self.ensure_one()
        if to_date is None:
            to_date = fields.Date.today()
        self.env['hr.payslip'].flush_model(['employee_id', 'state', 'date_from', 'date_to', 'credit_note'])
        self.env['hr.payslip.line'].flush_model(['total', 'slip_id', 'code'])
        query = """
            SELECT sum(case when hp.credit_note is not True then (pl.total) else (-pl.total) end)
            FROM hr_payslip as hp
            JOIN hr_payslip_line as pl ON hp.id = pl.slip_id
            WHERE hp.employee_id = %s AND hp.state in ('validated', 'paid')
            AND hp.date_from >= %s AND hp.date_to <= %s
            AND pl.code = %s
        """
        self.env.cr.execute(query, (self.employee_id.id, from_date, to_date, code))
        res = self.env.cr.fetchone()
        return res and res[0] or 0.0
