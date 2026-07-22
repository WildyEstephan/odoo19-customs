from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError
import re
import base64
import time
import logging

_logger = logging.getLogger(__name__)


class _NullInput(int):
    """
    2026-03-18 — Arturo Diaz Lora — Objeto dummy para inputs inexistentes
    Hereda de int(0) para soportar toda aritmetica (+, -, *, /, negacion).
    Cuando una regla hace: x = inputs.get('X') and inputs.get('X').amount
    y 'X' no existe, x = _NullInput (falsy, == 0, tiene .amount=0).
    Asi: _NullInput + _NullInput = 0, -_NullInput = 0, bool(_NullInput) = False.
    """
    def __new__(cls):
        return super().__new__(cls, 0)

    amount = 0
    quantity = 0

_NULL_INPUT = _NullInput()


class SafeInputsDict(dict):
    """
    2026-03-18 — Arturo Diaz Lora — Dict wrapper para inputs de nomina
    Retorna _NULL_INPUT (amount=0, bool=False) en vez de None para claves inexistentes.
    """
    def get(self, key, default=None):
        return super().get(key, default if default is not None else _NULL_INPUT)


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'
    _description = 'To get values from methon'

    def _get_localdict(self):
        """
        2026-03-18 — Arturo Diaz Lora — Compatibilidad con reglas salariales dominicanas
        - Alias 'contract' para 'version' (Odoo 19 renombró contract → version)
        - SafeInputsDict para evitar TypeError en inputs.get('X').amount cuando X no existe
        """
        localdict = super()._get_localdict()
        localdict['contract'] = localdict.get('version', self.version_id)
        localdict['inputs'] = SafeInputsDict(localdict.get('inputs', {}))
        return localdict

    def _get_safe_context(self):
        """Obtener contexto seguro sin idiomas inválidos"""
        context = dict(self.env.context)
        # Remover cualquier referencia a idiomas problemáticos
        if 'lang' in context and context['lang'] == 'es_ES':
            context['lang'] = 'en_US'
        # También limpiar otros posibles contextos problemáticos
        context.pop('tz', None)  # Zona horaria
        return context

    total_to_pay = fields.Float(store=True)
    real_worked_hours = fields.Float()
    wage_type = fields.Selection(related='version_id.wage_type')

    # Arturo Diaz Lora - 2025-12-22: Campo para mostrar solo líneas visibles en la UI
    # Filtra las líneas que tienen appears_on_payslip=True
    visible_line_ids = fields.One2many(
        'hr.payslip.line',
        'slip_id',
        string='Lineas Visibles',
        compute='_compute_visible_line_ids',
    )

    @api.depends('line_ids', 'line_ids.appears_on_payslip')
    def _compute_visible_line_ids(self):
        """
        Arturo Diaz Lora - 2025-12-22: Filtra las líneas del payslip
        para mostrar solo las que tienen appears_on_payslip=True
        """
        for slip in self:
            slip.visible_line_ids = slip.line_ids.filtered(lambda l: l.appears_on_payslip)

    def get_quotation_calculation(self, code):
        return self.env['hr.quotation.calculation'].search([('code', '=', code)])

    def _get_analytic_account(self):
        """
        Obtiene la cuenta analítica a usar para esta nómina.
        Prioridad:
        1. Si el lote tiene use_batch_analytic activo -> cuenta del lote
        2. Si no -> cuenta del empleado
        3. Si no -> None (usará la del contrato o regla salarial)
        """
        self.ensure_one()
        # Verificar si el lote tiene cuenta analítica configurada
        if self.payslip_run_id and self.payslip_run_id.use_batch_analytic:
            return self.payslip_run_id.analytic_account_id
        # Si no, verificar cuenta del empleado
        if self.employee_id.analytic_account_id:
            return self.employee_id.analytic_account_id
        return None

    def _prepare_line_values(self, line, account, date, debit, credit):
        """
        2026-03-18 — Arturo Diaz Lora — Sobrescribe para incluir cuenta analitica del lote/empleado.
        Fix: firma igual al enterprise (account es record, retorna lista de dicts).
        Fix: usar analytic_distribution (JSON) en vez de analytic_account_id (no existe en Odoo 19).
        """
        # Obtener cuenta analítica personalizada (lote o empleado)
        custom_analytic = self._get_analytic_account()
        if custom_analytic:
            analytic_override = {str(custom_analytic.id): 100}
        else:
            analytic_override = None

        # Llamar al método original del enterprise
        result = super()._prepare_line_values(line, account, date, debit, credit)

        # Si hay cuenta analítica custom, aplicarla a todas las líneas generadas
        if analytic_override:
            for line_vals in result:
                line_vals['analytic_distribution'] = analytic_override

        return result

    def get_quotation_isr(self, code):
        return self.env['hr.retention.scale'].search([('code', '=', code)])

    def action_payslip_done(self):
        res = super(HrPayslip, self).action_payslip_done()

        for slip in self:
            # Modification --> Bellow for is the connection with the employee loan to assign some values
            payslip_day = slip.date_to.day
            for loan in slip.employee_id.loan_ids.filtered(lambda loan: loan.state == 'approved'):
                if slip.pay_vacation and slip.vacation_type == 'enjoyed' and 13 <= payslip_day <= 16:
                    loan_lines = loan.loan_line_ids.filtered(
                        lambda loan_line: loan_line.number == loan.next_fee or loan_line.number == loan.next_fee + 1)
                    for l in loan_lines:
                        l.payslip_id = slip.id
                    loan.next_fee += 2 if loan.next_fee < loan.fee_count - 1 else 1
                else:
                    loan_line = loan.loan_line_ids.filtered(
                        lambda loan_line: loan_line.number == loan.next_fee)
                    loan_line.payslip_id = slip.id
                    loan.next_fee += 1 if loan.next_fee < loan.fee_count else 0
                if loan.next_fee == loan.fee_count and loan.loan_line_ids.filtered(lambda l: l.number == loan.next_fee).paid:
                    loan.write({'state': 'paid'})
        return res

    @api.depends('line_ids')
    def _compute_worked_hours(self):
        for register in self.filtered('line_ids'):
            total_amount = register.line_ids.filtered(
                lambda line: line.code == 'NET').total or 0.0
            register.total_to_pay = total_amount

    # Modificado: 2026-03-18 — Arturo Diaz Lora — Override _compute_input_line_ids para generar
    # todas las entradas salariales DO basadas en input_line_type_ids de la estructura,
    # no solo salary attachments como hace el core de v19
    @api.depends('employee_id', 'version_id', 'struct_id', 'date_from', 'date_to')
    def _compute_input_line_ids(self):
        from odoo.fields import Command
        attachment_type_ids = self.env['hr.payslip.input.type'].search(
            [('available_in_attachments', '=', True)]).ids
        for slip in self:
            if not slip.struct_id:
                continue

            # Obtener IDs de input types que ya existen en las líneas actuales
            existing_type_ids = set(slip.input_line_ids.mapped('input_type_id').ids)
            # Input types permitidos por la estructura
            allowed_type_ids = set(slip.struct_id.input_line_type_ids.ids)

            input_line_vals = []

            # 1. Eliminar líneas de tipos que ya no están permitidos (excepto las manuales)
            for line in slip.input_line_ids:
                if line.input_type_id.id in attachment_type_ids:
                    # Las líneas de attachment se manejan aparte
                    input_line_vals.append(Command.unlink(line.id))
                elif line.input_type_id.id not in allowed_type_ids:
                    input_line_vals.append(Command.unlink(line.id))

            # 2. Crear líneas para tipos permitidos que no existen aún
            for input_type in slip.struct_id.input_line_type_ids:
                if input_type.id not in existing_type_ids and input_type.id not in attachment_type_ids:
                    input_line_vals.append(Command.create({
                        'input_type_id': input_type.id,
                        'name': input_type.name,
                    }))

            # 3. Manejar salary attachments (lógica del core)
            if slip.employee_id and slip.employee_id.salary_attachment_ids and slip.date_to:
                valid_attachments = slip.employee_id.salary_attachment_ids.filtered(
                    lambda a: a.state == 'open'
                        and a.date_start <= slip.date_to
                        and (not a.date_end or a.date_end >= slip.date_from)
                        and (not a.other_input_type_id.struct_ids or slip.struct_id in a.other_input_type_id.struct_ids)
                )
                for input_type_id, attachments in valid_attachments.grouped("other_input_type_id").items():
                    amount = attachments._get_active_amount()
                    name = ', '.join(desc for desc in attachments.mapped('description') if desc)
                    input_line_vals.append(Command.create({
                        'name': name,
                        'amount': amount if not slip.credit_note else -amount,
                        'input_type_id': input_type_id.id,
                    }))

            if input_line_vals:
                slip.update({'input_line_ids': input_line_vals})

    @api.onchange('employee_id', 'struct_id', 'version_id', 'date_from', 'date_to')
    def _onchange_employee(self):
        for slip in self:
            # Verificar si hay cambios significativos
            if hasattr(slip, '_origin') and slip._origin and slip._origin.id:
                origin = slip._origin
                same_emp = slip.employee_id == origin.employee_id
                same_struct = slip.struct_id == origin.struct_id
                same_contract = slip.version_id == origin.version_id
                same_dates = slip.date_from == origin.date_from and slip.date_to == origin.date_to
                if same_emp and same_struct and same_contract and same_dates:
                    continue

            # Verificar que tenemos datos mínimos necesarios
            if not slip.struct_id:
                continue

            # Construir lista de comandos para input_line_ids
            commands = []
            
            # Comando para limpiar todas las líneas existentes
            commands.append((5, 0, 0))
            
            # Crear nuevas líneas basadas en la estructura
            if slip.struct_id.input_line_type_ids:
                for input_type in slip.struct_id.input_line_type_ids:
                    commands.append((0, 0, {'input_type_id': input_type.id}))
            
            # Asignar los comandos al campo
            slip.input_line_ids = commands

            # Solo procesar descuentos si tenemos empleado
            if slip.employee_id and slip.date_from and slip.date_to:
                try:
                    discounts = self.env['payroll.discount.import'].search([
                        ('employee_id', '=', slip.employee_id.id),
                        ('date_from', '>=', slip.date_from),
                        ('date_to', '<=', slip.date_to),
                    ])
                    if discounts:
                        discount_codes = set(discounts.mapped('discount_code'))
                        for code in discount_codes:
                            amount = sum(discounts.filtered(lambda d: d.discount_code == code).mapped('amount'))
                            matching_lines = slip.input_line_ids.filtered(lambda l: l.code == code)
                            for line in matching_lines:
                                line.amount = amount
                except Exception:
                    pass  # Continuar si hay error en descuentos

            # Solo procesar horas trabajadas si tenemos empleado
            if slip.employee_id and slip.date_from and slip.date_to:
                try:
                    working_hours = self.env['working.hours.import'].search([
                        ('employee_id', '=', slip.employee_id.id),
                        ('date_from', '>=', slip.date_from),
                        ('date_to', '<=', slip.date_to),
                    ])
                    if working_hours:
                        hour_mapping = {
                            'HEL': 'extra_hours_amount_35',
                            'HEN': 'extra_hours_amount_50',
                            'HNI': 'extra_hours_amount_15',
                            'HEF': 'holiday_hours_amount',
                            'HLT': 'free_days',
                        }
                        for line in slip.input_line_ids:
                            if line.code in hour_mapping:
                                field_name = hour_mapping[line.code]
                                if hasattr(working_hours, field_name):
                                    total = sum(working_hours.mapped(field_name))
                                    line.amount = total
                except Exception:
                    pass  # Continuar si hay error en horas

            # Solo procesar préstamos si tenemos empleado y contrato
            if slip.employee_id and slip.version_id:
                try:
                    pre_lines = slip.input_line_ids.filtered(lambda l: l.code == 'PRE')
                    for line in pre_lines:
                        if hasattr(slip.employee_id, 'get_approved_loans'):
                            loans = slip.employee_id.get_approved_loans() or []
                            total_fees = 0
                            for loan in loans:
                                if hasattr(loan, 'get_next_fee'):
                                    next_fee = loan.get_next_fee()
                                    if next_fee and hasattr(next_fee, 'dues'):
                                        total_fees += next_fee.dues
                            base = total_fees + (slip.version_id.fixed_loan or 0.0)
                            multiplier = 2 if (slip.pay_vacation and slip.vacation_type == 'enjoyed') else 1
                            line.amount = base * multiplier

                    cooa_lines = slip.input_line_ids.filtered(lambda l: l.code == 'COOA')
                    for line in cooa_lines:
                        saved = slip.version_id.amount_saved or 0.0
                        multiplier = 2 if (slip.pay_vacation and slip.vacation_type == 'enjoyed') else 1
                        line.amount = saved * multiplier
                except Exception:
                    pass  # Continuar si hay error en préstamos


    def _get_last_payslip_vacation(self):
        payslip_day = self.date_to.day
        payslips = self.employee_id.slip_ids.sorted('id')
        payslips_ids = [p.id for p in payslips]

        if len(payslips_ids) > 1:
            last_slip = self.env['hr.payslip'].browse(
                [payslips_ids[payslips_ids.index(self.id) - 1]])
            if payslip_day >= 25 and payslip_day <= 31:
                if last_slip.pay_vacation and last_slip.vacation_type in ['enjoyed', 'worked', 'unpayed']:
                    self.last_payslip_vacation = True
                else:
                    self.last_payslip_vacation = False
            else:
                self.last_payslip_vacation = False
        else:
            self.last_payslip_vacation = False

    pay_vacation = fields.Boolean(string="Vacaciones",
                                  help="Seleccione si el empleado va a cobrar vacaciones")
    vacation_type = fields.Selection([
        ('enjoyed', 'Vacaciones disfrutadas'),
        ('worked', 'Vacaciones trabajadas'),
        ('unpayed', 'Vacaciones disfrutadas sin adelanto')],
        string="Tipo de vacaciones")
    last_payslip_vacation = fields.Boolean(
        compute='_get_last_payslip_vacation', store=False)

    partial_worked_days = fields.Boolean(string=u"Días trabajados parciales",
                                         help='Usar por ejemplo si un empleado entró a mitad de quincena (No usar si el empleado cobra por hora)')

    def compute_commission_amount(self, payslip):
        # --- Obtengo todos los pagos vinculados al empleado hasta la fecha del payslip
        payment_domain = [
            ('payment_date', '<=', payslip.date_to),
            ('state', 'in', ['posted', 'sent', 'reconciled']),
            ('commissioned', '=', False),
            ('user_id', '=', payslip.employee_id.user_id.id)
        ]
        payment_fields = ['amount', 'amount_tax', 'payment_type']
        payments = payslip.env['account.payment'].search_read(payment_domain, payment_fields)
        
        # --- Aquí deberías distinguir ventas de cobranzas; yo asumo que lo marcas en payment_type:
        sales_amount     = sum(p['amount'] - p['amount_tax']
                               for p in payments if p['payment_type'] == 'inbound')
        collection_amount = sum(p['amount'] - p['amount_tax']
                               for p in payments if p['payment_type'] == 'outbound')
        
        # --- Tasa de comisión sobre cada tipo
        rate = payslip.version_id.comission_rate / 100.0
        sales_commission     = sales_amount * rate
        collection_commission = collection_amount * rate

        # --- Asigno a cada input line
        for line in payslip.input_line_ids:
            if line.code == 'COMV':
                line.amount = sales_commission
            elif line.code == 'COMC':
                line.amount = collection_commission


    def compute_sheet(self):
        # Computar segunda quincena con validaciones por vacaciones y contratos
        contract_wages = {}

        for rec in self:
            rec._onchange_employee()

            # Salario base según el tipo de contrato
            real_wage = rec.version_id.hourly_wage if rec.version_id.structure_type_id.wage_type == 'hourly' else rec.version_id.wage

            # Obtener el valor de días promedio del contrato (por defecto 23.83)
            payment_days = rec.version_id.payment_day or 23.83

            # Ajuste visual de las horas trabajadas
            for wdl in rec.worked_days_line_ids:
                wdl.number_of_hours = rec.real_worked_hours if rec.version_id.structure_type_id.wage_type == 'hourly' else wdl.number_of_days

            # Cálculo de salario proporcional
            if rec.version_id.structure_type_id.wage_type == 'hourly':
                wage_amount = real_wage * sum([line.number_of_days for line in rec.worked_days_line_ids])
            else:
                wage_amount = (real_wage / payment_days) * sum([line.number_of_days for line in rec.worked_days_line_ids])

            # Registrar salario para uso posterior (vacaciones, etc.)
            contract_wages.update({rec.version_id.id: wage_amount})

            # Validación de entrada de vacaciones y asignación de seguro
            for line in rec.input_line_ids:
                if rec.pay_vacation and line.code == 'VAC' and line.amount <= 0:
                    raise ValidationError(u"Establezca primero la cantidad de días de vacaciones")
                if rec.version_id.assurance_amount > 0.0 and line.code == 'SEGMED':
                    line.amount = rec.version_id.assurance_amount / 2

            # Calcular comisión si el contrato lo requiere
            if rec.version_id.comission_rate > 0:
                self.compute_commission_amount(rec)


        super(HrPayslip, self).compute_sheet()

        ##############################################################
        # duplicate company contributions if vacation type is enjoyed
        for rec in self:
            if rec.pay_vacation and rec.vacation_type == 'enjoyed':
                for line in rec.line_ids:
                    if line.category_id.code in ['COMP']:
                        line.amount = line.amount * 2

            elif rec.pay_vacation and rec.vacation_type == 'worked':
                pass

            elif rec.pay_vacation and rec.vacation_type == 'unpayed':
                vacation_days = 0
                for line in rec.input_line_ids:
                    if line.code == 'VAC':
                        vacation_days = line.amount
                        break

                for line in rec.line_ids:
                    if line.code == 'VAC':
                        line.amount = (
                            ((wage_amount / 23.83) * vacation_days) - (wage_amount / 2))
                    if line.code == 'NET':
                        line.amount = line.total + \
                            (((wage_amount / 23.83) * vacation_days) - (wage_amount / 2))

        for record in self:

            payslip_day = record.date_to.day
            payslips = record.employee_id.slip_ids.sorted('id')
            payslips_ids = [p.id for p in payslips]
            extra_hours = sum(pl.total for pl in record.line_ids if pl.code in [
                              'HEL', 'HEF', 'HEN', 'HNI', 'HLT'])
            commissions = record.line_ids.filtered(lambda pl: pl.code == 'COM').total
            incentives  = record.line_ids.filtered(lambda pl: pl.code == 'INC').total
            retenciones = sum(l.total for l in record.line_ids.filtered(
                lambda pl: pl.code in ['SFSE', 'SVDSE']))
            if len(payslips_ids) > 1:
                last_slip = record.env['hr.payslip'].browse(
                    [payslips_ids[payslips_ids.index(record.id) - 1]])
                if payslip_day >= 25 and payslip_day <= 31:
                    if last_slip.pay_vacation and last_slip.vacation_type == 'enjoyed':
                        for line in record.line_ids:
                            if line.category_id.code not in ['HE', 'INCE', 'COM', 'NET', 'COMP', 'DED', 'GROSS'] or line.code == 'ISR':
                                line.amount = 0.0
                                line.total = 0.0
                        #         pass
                        for line in record.line_ids:
                            if line.code == 'NET':
                                line.total = extra_hours + commissions + incentives + retenciones
                                line.amount = extra_hours + commissions + incentives + retenciones
                            if line.code == 'COMM':
                                line.total = commissions
                                line.amount = commissions
                            if line.code == 'INCENT':
                                line.total = incentives
                                line.amount = incentives

                    elif last_slip.pay_vacation and last_slip.vacation_type == 'unpayed':
                        pass

                elif payslip_day >= 12 and payslip_day <= 15 and last_slip.pay_vacation and last_slip.vacation_type in ['enjoyed']:
                    for line in record.line_ids:
                        if line.category_id.code not in ['HE']:
                            line.amount = 0.0

                    for line in record.line_ids:
                        if line.code == 'NET':
                            line.total = extra_hours + commissions + incentives + retenciones
                            line.amount = extra_hours + commissions + incentives + retenciones
                        if line.code == 'COMM':
                            line.total = commissions
                            line.amount = commissions
                        if line.code == 'INCENT':
                            line.total = incentives
                            line.amount = incentives

        return True
    
    def _generate_basic_payslip_html(self):
        """Generar HTML básico de nómina como respaldo"""
        # Preparar datos seguros
        employee_name = self.employee_id.name or "N/A"
        payslip_name = self.name or "N/A"
        company_name = self.company_id.name or "Empresa"
        currency_symbol = self.company_id.currency_id.symbol or "$"
        
        # Formatear fechas
        try:
            date_from_str = self.date_from.strftime('%d/%m/%Y') if self.date_from else "N/A"
            date_to_str = self.date_to.strftime('%d/%m/%Y') if self.date_to else "N/A"
        except:
            date_from_str = str(self.date_from) if self.date_from else "N/A"
            date_to_str = str(self.date_to) if self.date_to else "N/A"
        
        # Obtener líneas de nómina
        payslip_lines = self.line_ids.filtered(lambda line: line.appears_on_payslip)
        
        # Preparar valores seguros
        contract_wage = self.version_id.wage if self.version_id else 0.0
        net_wage = self.net_wage or 0.0
        compute_date_str = self.compute_date.strftime('%d/%m/%Y') if self.compute_date else 'N/A'
        compute_datetime_str = self.compute_date.strftime('%d/%m/%Y %H:%M') if self.compute_date else ''
        
        # Generar tabla de líneas
        lines_html = ""
        for line in payslip_lines:
            lines_html += f"""
                <tr>
                    <td>{line.name}</td>
                    <td style="text-align: right;">{currency_symbol} {line.total:,.2f}</td>
                </tr>
            """
        
        html = f'''
        <html>
        <head>
            <meta charset="utf-8"/>
            <title>Nómina - {payslip_name}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .info-table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
                .info-table th, .info-table td {{ 
                    border: 1px solid #ddd; 
                    padding: 8px; 
                    text-align: left; 
                }}
                .info-table th {{ background-color: #f2f2f2; }}
                .lines-table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                .lines-table th, .lines-table td {{ 
                    border: 1px solid #ddd; 
                    padding: 8px; 
                }}
                .lines-table th {{ background-color: #f2f2f2; text-align: center; }}
                .total-row {{ font-weight: bold; background-color: #e8f4f8; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>{company_name}</h2>
                <h3>Recibo de Nómina</h3>
                <h4>{payslip_name}</h4>
            </div>
            
            <table class="info-table">
                <tr>
                    <th>Información del Empleado</th>
                    <th>Información del Período</th>
                </tr>
                <tr>
                    <td>
                        <strong>Nombre:</strong> {employee_name}<br/>
                        <strong>ID:</strong> {self.employee_id.identification_id or 'N/A'}<br/>
                        <strong>Departamento:</strong> {self.employee_id.department_id.name if self.employee_id.department_id else 'N/A'}<br/>
                        <strong>Puesto:</strong> {self.employee_id.job_title or 'N/A'}
                    </td>
                    <td>
                        <strong>Período:</strong> {date_from_str} - {date_to_str}<br/>
                        <strong>Fecha de cálculo:</strong> {compute_date_str}<br/>
                        <strong>Salario base:</strong> {currency_symbol} {contract_wage:,.2f}<br/>
                        <strong>Neto a pagar:</strong> {currency_symbol} {net_wage:,.2f}
                    </td>
                </tr>
            </table>
            
            <table class="lines-table">
                <thead>
                    <tr>
                        <th>Concepto</th>
                        <th>Monto</th>
                    </tr>
                </thead>
                <tbody>
                    {lines_html}
                    <tr class="total-row">
                        <td><strong>NETO A PAGAR</strong></td>
                        <td style="text-align: right;"><strong>{currency_symbol} {net_wage:,.2f}</strong></td>
                    </tr>
                </tbody>
            </table>
            
            <div style="margin-top: 30px; font-size: 12px; color: #666;">
                <p><strong>Nota:</strong> Este documento es generado automáticamente por el sistema de nómina.</p>
                <p>Fecha de emisión: {compute_datetime_str}</p>
            </div>
        </body>
        </html>
        '''
        return html

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if 'journal_id' in fields and not res.get('journal_id'):
            journal = self.env['account.journal'].search([('name', '=', 'Salarios')], limit=1)
            if journal:
                res['journal_id'] = journal.id
        return res





    def get_payroll_total(self):
        """Calcula los totales de percepciones, deducciones y total neto para el reporte"""
        self.ensure_one()
        
        perceptions = 0.0
        deductions = 0.0
        
        for line in self.line_ids.filtered(lambda l: l.appears_on_payslip):
            if line.total > 0:
                perceptions += line.total
            else:
                deductions += abs(line.total)
        
        totals = perceptions - deductions
        
        return {
            'perceptions': perceptions,
            'deductions': deductions,
            'totals': totals
        }

    def payslip_send_mail(self):
        self.ensure_one()
        # Usar una implementación completamente personalizada para evitar cualquier problema de idioma
        return self._send_payslip_email_safe()
    
    def _send_payslip_email_safe(self):
        """Método seguro para enviar correos sin problemas de idioma"""
        # Obtener template de correo
        try:
            template_id = int(
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("l10n_do_hr_payroll.choose_mail_template")
            )
        except ValueError:
            template_id = False
        if not template_id:
            raise UserError("Email Template must be selected in settings.")
        
        # Obtener el template con contexto completamente limpio
        template = self.env["mail.template"].sudo().browse(template_id)
        
        # Generar PDF usando el reporte oficial de nómina
        try:
            # Usar el reporte oficial de hr_payroll
            report = self.env.ref('hr_payroll.action_report_payslip')
            pdf_bin, _ = report._render_qweb_pdf(self.ids)
        except Exception as e:
            # Si falla, intentar con el reporte ligero
            try:
                report = self.env.ref('hr_payroll.action_report_light_payslip')
                pdf_bin, _ = report._render_qweb_pdf(self.ids)
            except Exception as e2:
                # Como último recurso, usar un HTML básico pero mejorado
                _logger.warning(f"Failed to generate official payslip report: {e}, {e2}")
                payslip_html = self._generate_basic_payslip_html()
                pdf_bin = self.env['ir.actions.report']._run_wkhtmltopdf([payslip_html])
        pdf_name = re.sub(r"\W+", "", self.employee_id.name) + "_Payslip.pdf"
        
        # Crear attachment
        attach = self.env["ir.attachment"].sudo().create({
            "name": pdf_name,
            "datas": base64.b64encode(pdf_bin),
            "res_id": self.id,
            "res_model": "hr.payslip",
            "type": "binary",
        })
        
        # Validar que el empleado tenga email
        if not self.employee_id.work_email:
            raise UserError("El empleado %s no tiene configurado un email de trabajo." % self.employee_id.name)
        
        # Preparar datos seguros para evitar errores
        employee_name = self.employee_id.name or "N/A"
        payslip_name = self.name or "N/A"
        company_name = self.company_id.name or "Empresa"
        currency_symbol = self.company_id.currency_id.symbol or "$"
        total_pay = self.total_to_pay or 0.0
        
        # Formatear fechas de manera segura
        try:
            date_from_str = self.date_from.strftime('%d/%m/%Y') if self.date_from else "N/A"
            date_to_str = self.date_to.strftime('%d/%m/%Y') if self.date_to else "N/A"
        except:
            date_from_str = str(self.date_from) if self.date_from else "N/A"
            date_to_str = str(self.date_to) if self.date_to else "N/A"
        
        # Crear el HTML del correo de manera más segura
        body_html = f'''
<html>
<body style="font-family: Arial, sans-serif; margin: 20px;">
    <h3>Nómina - {employee_name}</h3>
    
    <p>Estimado/a {employee_name},</p>
    
    <p>Adjunto encontrará su nómina correspondiente al período <strong>{payslip_name}</strong>.</p>
    
    <p><strong>Detalles:</strong></p>
    <ul>
        <li><strong>Empleado:</strong> {employee_name}</li>
        <li><strong>Período:</strong> {date_from_str} - {date_to_str}</li>
        <li><strong>Nómina:</strong> {payslip_name}</li>
        <li><strong>Total a recibir:</strong> {currency_symbol} {total_pay:,.2f}</li>
    </ul>
    
    <p>Si tiene alguna pregunta sobre su nómina, no dude en contactarnos.</p>
    
    <p>Saludos cordiales,<br/>
    <strong>Departamento de Recursos Humanos</strong><br/>
    {company_name}</p>
</body>
</html>
        '''
        
        # Enviar correo usando método directo sin contextos problemáticos
        mail_values = {
            'subject': f"Nómina - {employee_name} - {payslip_name}",
            'email_from': self.company_id.email or self.env.user.email,
            'email_to': self.employee_id.work_email,
            'body_html': body_html,
            'attachment_ids': [(4, attach.id)],
        }

        # MODIFICADO: Arturo Diaz Lora - 2026-03-27 18:50
        # Razón: Usar servidor de correo específico para HR/Nómina si está configurado
        try:
            hr_mail_server_id = int(
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("l10n_do_hr_payroll.mail_server_id", default=0)
            )
        except (ValueError, TypeError):
            hr_mail_server_id = 0

        if hr_mail_server_id:
            # Verificar que el servidor existe y está activo
            mail_server = self.env['ir.mail_server'].sudo().browse(hr_mail_server_id)
            if mail_server.exists() and mail_server.active:
                mail_values['mail_server_id'] = hr_mail_server_id
                _logger.info(f"Using HR mail server: {mail_server.name} (id={hr_mail_server_id})")

        # Crear y enviar el correo directamente
        try:
            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()
            
            # Log de éxito
            _logger.info(f"Email sent successfully to {self.employee_id.work_email} for payslip {self.name}")
            
        except Exception as e:
            # Log del error
            _logger.error(f"Error sending email for payslip {self.name}: {str(e)}")
            raise UserError("Error enviando correo: %s" % str(e))
        
        # Mostrar notificación
        message = "Mail sent"
        self.env["bus.bus"]._sendone(
            self.env.user.partner_id,
            "simple_notification",
            {"title": "Notification", "message": message, "sticky": False},
        )

    def send_payslip_by_email_action(self):
        for rec in self:
            rec._send_payslip_email_safe()

    # MODIFICADO: Arturo Diaz Lora - 2026-04-04
    # Razón: Agregar método puente para llamar action_payment_report del lote desde la nómina
    def action_run_payment_report(self):
        """
        Llama al método action_payment_report del lote de nómina asociado.
        Permite generar el reporte de pago desde la vista del recibo individual.
        """
        self.ensure_one()
        if not self.payslip_run_id:
            from odoo.exceptions import UserError
            raise UserError("Esta nómina no está asociada a ningún lote.")
        return self.payslip_run_id.action_payment_report()


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    choose_mail_template = fields.Many2one(
        "mail.template",
        string="Mail Template For Payroll",
        config_parameter="l10n_do_hr_payroll.choose_mail_template",
        default=lambda self: self.env.ref('l10n_do_hr_payroll.mail_template_payslip', raise_if_not_found=False),
        domain="[('model_id.model','=', 'hr.payslip')]",
    )
    # MODIFICADO: Arturo Diaz Lora - 2026-03-27 18:50
    # Razón: Agregar campo para seleccionar servidor de correo específico para HR/Nómina
    hr_payroll_mail_server_id = fields.Many2one(
        "ir.mail_server",
        string="Servidor de Correo para Nómina",
        config_parameter="l10n_do_hr_payroll.mail_server_id",
        help="Servidor de correo saliente específico para envío de nóminas. "
             "Si no se selecciona, se usará el servidor con mayor prioridad.",
    )







