from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import xlsxwriter
import string
import base64
from odoo.tools.misc import format_date
from dateutil.relativedelta import relativedelta
from datetime import date, datetime, timedelta
import calendar
import re


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    payroll_xlsx_file_name = fields.Char()
    payroll_xlsx_binary = fields.Binary(string="Archivo TXT")

    is_christmas_salary = fields.Boolean(string='Nómina de doble sueldo / regalía')

    # Cuenta analítica a nivel de lote (opcional)
    use_batch_analytic = fields.Boolean(
        string='Usar cuenta analítica por lote',
        help='Si está activo, la cuenta analítica se configura a nivel de lote y no a nivel de empleado.'
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Cuenta Analítica',
        help='Cuenta analítica para asignar a todas las nóminas de este lote. '
             'Si está configurada, se ignorará la cuenta analítica del empleado.'
    )

    # Campo para seleccionar manualmente el tipo de estructura salarial
    # Modificado: 2026-03-18 — Arturo Diaz Lora — Agregar default Empleado Fijo (Salario)
    payroll_structure_type_id = fields.Many2one(
        'hr.payroll.structure.type',
        string='Tipo de Estructura Salarial',
        required=True,
        default=lambda self: self.env['hr.payroll.structure.type'].search(
            [('name', 'ilike', 'Empleado Fijo (Salario)')], limit=1
        ),
        help='Seleccionar el tipo de estructura salarial para generar el nombre del lote dinámicamente'
    )

    # Override estructura salarial con default Nómina de Empleados Internos
    # Modificado: 2026-03-18 — Arturo Diaz Lora — Agregar default Nómina de Empleados Internos
    structure_id = fields.Many2one(
        'hr.payroll.structure',
        string='Salary Structure',
        readonly=False,
        default=lambda self: self.env['hr.payroll.structure'].search(
            [('name', 'ilike', 'Nómina de Empleados Internos')], limit=1
        ),
    )

    # Override calendario de pago con default bi-weekly (2 weeks)
    # Modificado: 2026-03-18 — Arturo Diaz Lora — Default calendario de pago = 2 weeks (bi-weekly)
    schedule_pay = fields.Selection(
        selection=lambda self: self.env['hr.payroll.structure.type']._get_selection_schedule_pay(),
        compute='_compute_schedule_pay', default="bi-weekly", readonly=False, store=True, precompute=True, string='Pay Schedule')

    # Override campos de fecha con lógica automática basada en modo de pago
    date_start = fields.Date(string='Date From', required=True, readonly=False)
    date_end = fields.Date(string='Date To', required=True, readonly=False)
    
    # Campo para la referencia del contrato
    contract_reference = fields.Char(string='Referencia de contrato', readonly=True, compute='_compute_contract_reference')
    
    # Override del campo name para que se calcule automáticamente y sea readonly
    name = fields.Char(string='Nombre', required=True, readonly=True, compute='_compute_name', store=True, default='Nuevo Lote de Nómina')

    def generate_payslips(self, version_ids=None, employee_ids=None):
        """
        Override para manejar estructura de regalía pascual en República Dominicana.
        Si is_christmas_salary está activo, usa la estructura de regalía pascual.
        """
        # Si es nómina de regalía, cambiar estructura
        if self.is_christmas_salary:
            christmas_struct = self.env.ref(
                'l10n_do_hr_payroll.christmas_salary_structure', raise_if_not_found=False)
            if christmas_struct:
                self.structure_id = christmas_struct

        # Llamar al método original
        return super().generate_payslips(version_ids=version_ids, employee_ids=employee_ids)

    @api.constrains('payroll_structure_type_id')
    def _check_payroll_structure_type_id(self):
        """Validar que el campo Tipo de Estructura Salarial sea obligatorio"""
        for record in self:
            if not record.payroll_structure_type_id:
                raise ValidationError(_('El campo "Tipo de Estructura Salarial" es obligatorio. Por favor seleccione un tipo de estructura salarial.'))

    def _get_default_date_start(self):
        """Calcula la fecha de inicio basada en el modo de pago del contrato"""
        today = date.today()
        return self._calculate_period_dates(today)[0]

    def _get_default_date_end(self):
        """Calcula la fecha de fin basada en el modo de pago del contrato"""
        today = date.today()
        return self._calculate_period_dates(today)[1]

    def _calculate_period_from_schedule(self, current_date, schedule_pay):
        """
        Calcula las fechas de inicio y fin del período basado en el modo de pago específico
        Ejemplo: Si estamos el 08/09/2025 y es quincenal -> 01/09/2025 a 15/09/2025
        """
        if not schedule_pay:
            schedule_pay = 'monthly'
            
        if schedule_pay == 'daily':
            return current_date, current_date
            
        elif schedule_pay == 'weekly':
            # Semana del lunes al viernes (5 días laborales)
            # Si hoy es 08/09/2025 (domingo), usar esa semana: 08/09 al 12/09
            days_since_monday = current_date.weekday()  # 0=Lunes, 6=Domingo
            
            if days_since_monday == 6:  # Si es domingo, usar esa semana empezando desde el domingo
                start_date = current_date  # Domingo actual
                end_date = current_date + timedelta(days=4)  # Jueves (5 días desde domingo)
            else:
                # Para otros días, usar la semana normal lunes-viernes
                start_date = current_date - timedelta(days=days_since_monday)  # Lunes de esta semana
                end_date = start_date + timedelta(days=4)  # Viernes
            return start_date, end_date
            
        elif schedule_pay == 'bi-weekly':
            # Quincenal: del 1-15 o 16-final del mes
            # Si estamos el 08/09/2025 -> primera quincena (01/09 a 15/09)
            if current_date.day <= 15:
                start_date = current_date.replace(day=1)
                end_date = current_date.replace(day=15)
            else:
                start_date = current_date.replace(day=16)
                last_day = calendar.monthrange(current_date.year, current_date.month)[1]
                end_date = current_date.replace(day=last_day)
            return start_date, end_date
            
        elif schedule_pay == 'semi-monthly':
            # Igual que bi-weekly (quincenal)
            if current_date.day <= 15:
                start_date = current_date.replace(day=1)
                end_date = current_date.replace(day=15)
            else:
                start_date = current_date.replace(day=16)
                last_day = calendar.monthrange(current_date.year, current_date.month)[1]
                end_date = current_date.replace(day=last_day)
            return start_date, end_date
            
        elif schedule_pay == 'monthly':
            # Mensual: del 1 al último día del mes
            start_date = current_date.replace(day=1)
            last_day = calendar.monthrange(current_date.year, current_date.month)[1]
            end_date = current_date.replace(day=last_day)
            return start_date, end_date
            
        elif schedule_pay == 'bi-monthly':
            # Bimestral: cada 2 meses
            if current_date.month % 2 == 1:  # Mes impar
                start_date = current_date.replace(day=1)
                end_date = (current_date + relativedelta(months=1)).replace(day=1) - timedelta(days=1)
            else:  # Mes par
                start_date = (current_date - relativedelta(months=1)).replace(day=1)
                end_date = current_date.replace(day=1) - timedelta(days=1)
            return start_date, end_date
            
        elif schedule_pay == 'quarterly':
            # Trimestral: cada 3 meses
            quarter_start_month = ((current_date.month - 1) // 3) * 3 + 1
            start_date = current_date.replace(month=quarter_start_month, day=1)
            end_date = (start_date + relativedelta(months=3)) - timedelta(days=1)
            return start_date, end_date
            
        elif schedule_pay == 'semi-annually':
            # Semestral: cada 6 meses
            if current_date.month <= 6:
                start_date = current_date.replace(month=1, day=1)
                end_date = current_date.replace(month=6, day=30)
            else:
                start_date = current_date.replace(month=7, day=1)
                end_date = current_date.replace(month=12, day=31)
            return start_date, end_date
            
        elif schedule_pay == 'annually':
            # Anual: todo el año
            start_date = current_date.replace(month=1, day=1)
            end_date = current_date.replace(month=12, day=31)
            return start_date, end_date
            
        else:
            # Por defecto mensual
            start_date = current_date.replace(day=1)
            last_day = calendar.monthrange(current_date.year, current_date.month)[1]
            end_date = current_date.replace(day=last_day)
            return start_date, end_date

    def _calculate_period_dates(self, current_date):
        """
        Calcula las fechas de inicio y fin del período basado en el modo de pago del contrato
        (Función legacy para compatibilidad)
        """
        # Obtener el modo de pago del contrato activo (usar el primero disponible)
        # En Odoo 19, hr.version.is_current es campo computado sin store, usar campos almacenados
        today = fields.Date.today()
        version = self.env['hr.version'].search([
            ('active', '=', True),
            ('company_id', '=', self.env.company.id),
            ('contract_date_start', '<=', today),
            '|',
                ('contract_date_end', '=', False),
                ('contract_date_end', '>=', today),
        ], limit=1)
        
        schedule_pay = version.schedule_form_pay if version else 'monthly'
        return self._calculate_period_from_schedule(current_date, schedule_pay)

    def _get_main_contract(self):
        """
        Obtiene la versión principal para calcular el período
        Si hay nóminas en este período, usa la versión de la primera nómina
        Si no, usa la primera versión activa de la empresa
        """
        if self.slip_ids:
            # Si hay nóminas, usar la versión de la primera nómina
            return self.slip_ids[0].version_id
        else:
            # Si no hay nóminas, usar la primera versión actual
            # is_current es campo computado sin store, usar campos almacenados
            today = fields.Date.today()
            return self.env['hr.version'].search([
                ('active', '=', True),
                ('company_id', '=', self.env.company.id),
                ('contract_date_start', '<=', today),
                '|',
                    ('contract_date_end', '=', False),
                    ('contract_date_end', '>=', today),
            ], limit=1)

    @api.depends('date_start', 'date_end', 'slip_ids')
    def _compute_contract_reference(self):
        """Calcula la referencia del contrato basada en el tipo de nómina, modo de pago y período"""
        for record in self:
            # Obtener el contrato principal
            contract = record._get_main_contract()
            
            if contract and record.date_start and record.date_end:
                # Obtener el tipo de nómina
                payroll_type = contract.payrolltype_id.name if contract.payrolltype_id else 'N/A'
                
                # Obtener el modo de pago
                schedule_pay = contract.schedule_form_pay if contract.schedule_form_pay else 'N/A'
                schedule_display = self._get_schedule_pay_display_name(schedule_pay)
                
                # Formatear el período
                period = f"{record.date_start.strftime('%d/%m/%Y')} - {record.date_end.strftime('%d/%m/%Y')}"
                
                # Construir la referencia
                record.contract_reference = f"{payroll_type} - {schedule_display} - {period}"
            else:
                record.contract_reference = "N/A"

    @api.depends('date_start', 'date_end', 'slip_ids', 'payroll_structure_type_id')
    def _compute_name(self):
        """Calcula el nombre automáticamente basado en el tipo de estructura seleccionado y período"""
        for record in self:
            try:
                if record.date_start and record.date_end:
                    # Usar el tipo de estructura salarial seleccionado manualmente
                    if record.payroll_structure_type_id:
                        payroll_type = record.payroll_structure_type_id.name or 'Nómina'
                        schedule_display = record._get_schedule_display_from_structure_type(record.payroll_structure_type_id)
                    else:
                        # Fallback al método anterior si no se selecciona manualmente
                        contract = record._get_main_contract()
                        if contract:
                            payroll_type = contract.payrolltype_id.name if contract.payrolltype_id else 'Nómina'
                            schedule_pay = contract.schedule_form_pay if contract.schedule_form_pay else 'monthly'
                            schedule_display = record._get_schedule_pay_display_name(schedule_pay)
                        else:
                            payroll_type = 'Nómina'
                            schedule_display = 'Mensual'
                    
                    # Formatear el período usando las fechas seleccionadas
                    period = f"{record.date_start.strftime('%d/%m/%Y')} - {record.date_end.strftime('%d/%m/%Y')}"
                    
                    # Construir el nombre
                    record.name = f"{payroll_type} - {schedule_display} - {period}"
                else:
                    # Si no hay fechas, usar nombre por defecto
                    record.name = record.name or "Nuevo Lote de Nómina"
            except Exception:
                # En caso de error, mantener el nombre actual o usar uno por defecto
                record.name = record.name or "Nuevo Lote de Nómina"

    def _get_schedule_pay_display_name(self, schedule_pay):
        """Obtiene el nombre de visualización del modo de pago"""
        schedule_names = {
            'daily': 'Diario',
            'weekly': 'Semanal',
            'bi-weekly': 'Quincenal',
            'semi-monthly': 'Semanal',
            'monthly': 'Mensual',
            'bi-monthly': 'Bimestral',
            'quarterly': 'Trimestral',
            'semi-annually': 'Semestral',
            'annually': 'Anual'
        }
        return schedule_names.get(schedule_pay, schedule_pay)

    def _get_schedule_display_from_structure_type(self, structure_type):
        """Obtiene el nombre de visualización del período basado en el tipo de estructura salarial"""
        if not structure_type or not structure_type.default_schedule_pay:
            return 'Mensual'  # Valor por defecto
        
        # Usar la función existente para obtener el nombre de visualización
        return self._get_schedule_pay_display_name(structure_type.default_schedule_pay)

    @api.onchange('payroll_structure_type_id')
    def _onchange_payroll_structure_type(self):
        """Recalcula el período y nombre cuando cambia el tipo de estructura salarial"""
        if self.payroll_structure_type_id:
            # Calcular período basado en el default_schedule_pay del tipo de estructura
            today = date.today()  # En producción será 08/09/2025
            schedule_pay = self.payroll_structure_type_id.default_schedule_pay
            start_date, end_date = self._calculate_period_from_schedule(today, schedule_pay)
            
            # Actualizar las fechas
            self.date_start = start_date
            self.date_end = end_date
            
            # Recalcular el nombre
            self._compute_name()

    @api.onchange('date_start', 'date_end')
    def _onchange_dates(self):
        """Recalcula el nombre cuando cambian las fechas del período"""
        if self.date_start and self.date_end:
            self._compute_name()

    @api.model_create_multi
    def create(self, vals_list):
        """Override create para aplicar lógica automática basada en modo de pago si es necesario
        Odoo 19: usa vals_list (lista de dicts) en lugar de vals (dict único).
        Modificado: 2026-03-17 — Arturo Diaz Lora — Fix TypeError: list indices must be integers or slices, not str
        """
        for vals in vals_list:
            # Normalizar Many2one que llegan como dict del cliente web (Odoo 19)
            for key in list(vals.keys()):
                if isinstance(vals[key], dict):
                    vals[key] = vals[key].get('id', False)

            if 'date_start' not in vals and 'date_end' not in vals:
                # Solo aplicar lógica automática si no se especifican fechas
                today = date.today()
                start_date, end_date = self._calculate_period_dates(today)
                vals['date_start'] = start_date
                vals['date_end'] = end_date

            # Asegurar que siempre haya un nombre básico si no se especifica
            if 'name' not in vals:
                vals['name'] = 'Nuevo Lote de Nómina'

        # Crear los registros
        records = super().create(vals_list)

        # Forzar el cálculo del nombre después de crear
        for record in records:
            record._compute_name()

        return records

    @api.onchange('slip_ids')
    def _onchange_slips_recalculate_period(self):
        """Recalcula el período cuando cambian las nóminas"""
        if self.slip_ids and not self.date_start and not self.date_end:
            # Solo recalcular si no hay fechas establecidas
            contract = self._get_main_contract()
            if contract:
                today = date.today()
                start_date, end_date = self._calculate_period_dates(today)
                self.date_start = start_date
                self.date_end = end_date
                
                # Recalcular también el nombre
                self._compute_name()

    def process_report_data(self, values):
        CUENTA = str(values['numero_cuenta'] if values['numero_cuenta'] else "")
        NOMBRE = str(values['nombre_empleado'] if values['nombre_empleado'] else "")
        DOCUMENTO = str(values['documento'] if values['documento'] else "")
        MONTO_APAGAR = str('{:.2f}'.format(
            abs(values['monto_apagar'])) if values['monto_apagar'] else "")
        COMENTARIO = str(values['comentario'] if values['comentario'] else "")

        return ";".join([
            CUENTA, NOMBRE, DOCUMENTO, MONTO_APAGAR, COMENTARIO
        ])

    def action_payslip_report(self):
        if len(self.slip_ids) > 0:
            records = []
            for rec in self.slip_ids:
                records.append([rec.employee_id.bank_account_id.acc_number or '',
                                rec.employee_id.name,
                                rec.line_ids.filtered(
                                    lambda line_ids: line_ids.code == 'NET').total or '',
                                rec.employee_id.work_email or '',
                                self.name or ''])

            raise Warning(records)

    # MODIFICADO: Arturo Diaz Lora - 2026-04-03
    # Razón: Aceptar export_format para compatibilidad con firma base Odoo 19
    def action_payment_report(self, export_format='xlsx'):
        """
        Genera un reporte de pago en formato Excel con el formato estándar de nómina
        """
        if not self.slip_ids:
            raise ValidationError(_("Debe generar la nómina primero."))

        # Validar que las nóminas estén calculadas
        uncalculated_slips = self.slip_ids.filtered(lambda s: s.state == 'draft')
        if uncalculated_slips:
            raise ValidationError(_(
                "Debe calcular todas las nóminas primero. "
                "Hay %s nóminas sin calcular.") % len(uncalculated_slips))

        # Verificar campos faltantes en empleados
        missing_fields_warnings = []
        for slip in self.slip_ids:
            emp = slip.employee_id
            warnings = []

            if not emp.department_id:
                warnings.append("Departamento")
            if not emp.identification_id:
                warnings.append("Identificación")

            if warnings:
                missing_fields_warnings.append(
                    f"• {emp.name}: Falta {', '.join(warnings)}"
                )

        # Mostrar advertencia si hay campos faltantes
        if missing_fields_warnings:
            warning_msg = _(
                "ADVERTENCIA: Algunos empleados tienen campos vacíos que afectarán el reporte:\n\n"
                "%s\n\n"
                "Configure estos campos en: Empleados > Empleado > "
                "Pestaña 'Información Laboral' (Departamento) y 'Información Personal' (Identificación)\n\n"
                "¿Desea continuar generando el reporte de todos modos?"
            ) % '\n'.join(missing_fields_warnings[:10])  # Mostrar máximo 10

            # En lugar de bloquear, registrar warning en log
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning("Generando reporte con campos faltantes:\n%s", '\n'.join(missing_fields_warnings))

        # Crear archivo Excel en memoria
        import io
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Nómina')

        # Definir formatos
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'align': 'left',
            'valign': 'vcenter'
        })

        period_format = workbook.add_format({
            'font_size': 11,
            'align': 'left',
            'valign': 'vcenter'
        })

        section_header_format = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#D9D9D9',
            'border': 1
        })

        column_header_format = workbook.add_format({
            'bold': True,
            'font_size': 9,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#F2F2F2',
            'border': 1,
            'text_wrap': True
        })

        data_format = workbook.add_format({
            'font_size': 9,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1
        })

        number_format = workbook.add_format({
            'font_size': 9,
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '#,##0.00'
        })

        subtotal_format = workbook.add_format({
            'bold': True,
            'font_size': 9,
            'align': 'right',
            'valign': 'vcenter',
            'bg_color': '#E7E6E6',
            'border': 1,
            'num_format': '#,##0.00'
        })

        # Ajustar anchos de columnas
        worksheet.set_column('A:A', 15)  # Gerencia
        worksheet.set_column('B:B', 15)  # Departamento
        worksheet.set_column('C:C', 15)  # Oficina
        worksheet.set_column('D:D', 10)  # ID
        worksheet.set_column('E:F', 25)  # EMPLEADO (merged)
        worksheet.set_column('G:AC', 12)  # Resto de columnas

        # FILA 2: Título
        worksheet.write('A2', 'Nomina Mensual', title_format)

        # FILA 4: Información de período
        structure_name = self.payroll_structure_type_id.name if self.payroll_structure_type_id else 'REGULAR'
        date_from_str = self.date_start.strftime('%d/%m/%Y') if self.date_start else ''
        date_to_str = self.date_end.strftime('%d/%m/%Y') if self.date_end else ''
        period_text = f"Usuario  ({structure_name}        -{date_from_str} - {date_to_str})"
        worksheet.write('A4', period_text, period_format)

        # FILA 7: Encabezados de secciones (merged cells)
        worksheet.merge_range('D7:F7', 'INFORMACION', section_header_format)
        worksheet.merge_range('G7:M7', 'INGRESOS', section_header_format)
        worksheet.merge_range('N7:S7', 'DEDUCCIONES', section_header_format)
        worksheet.merge_range('T7:W7', 'BENEFICIOS', section_header_format)
        worksheet.merge_range('X7:Y7', 'ISR', section_header_format)
        worksheet.write('Z7', 'SUELDO', section_header_format)

        # FILA 9: Encabezados de columnas
        headers = [
            ('A9', 'Gerencia'),
            ('B9', 'Departamento'),
            ('C9', 'Oficina'),
            ('D9', 'ID'),
            ('G9', 'SALARIO MENSUAL'),
            ('H9', 'HORAS EXTRAS'),
            ('I9', 'COMBUSTIBLE'),
            ('J9', 'COMISIONES'),
            ('K9', 'RETROACTIVO'),
            ('L9', 'VACACIONES'),
            ('M9', 'TOTAL PAGOS'),
            ('N9', 'AFP'),
            ('O9', 'CXC EMPLEADO'),
            ('P9', 'SEGURO COMPLEMENTARIO'),
            ('Q9', 'SFS'),
            ('R9', 'SFS DEPENDIENTE ADICIONAL'),
            ('S9', 'TOTAL DEDUCCIONES'),
            ('T9', 'APORTE FONDO DE PENSIONES'),
            ('U9', 'SEGURO RIESGOS LABORALES'),
            ('V9', 'APORTE SEGURO FAMIL. DE SALUD'),
            ('W9', 'TOTAL BENEFICIOS'),
            ('X9', 'IMPUESTO SOBRE LA RENTA'),
            ('Y9', 'TOTAL ISR'),
            ('Z9', 'NETO')
        ]

        for cell, header in headers:
            worksheet.write(cell, header, column_header_format)

        # Merge de EMPLEADO en E9:F9
        worksheet.merge_range('E9:F9', 'EMPLEADO', column_header_format)

        # FILA 10+: Datos de empleados
        row = 10  # Empezar en fila 10 (índice 9 en xlsxwriter)

        # Totales para subtotales
        totals = {
            'salario': 0, 'horas_extras': 0, 'combustible': 0, 'comisiones': 0, 'retroactivo': 0,
            'vacaciones': 0, 'total_pagos': 0, 'afp': 0, 'cxc': 0, 'seguro_comp': 0,
            'sfs': 0, 'sfs_dep': 0, 'total_ded': 0, 'aporte_afp': 0, 'srl': 0,
            'aporte_sfs': 0, 'total_ben': 0, 'isr': 0, 'total_isr': 0, 'neto': 0
        }

        for slip in self.slip_ids:
            emp = slip.employee_id

            # Helper function to get line amount
            def get_line_amount(code):
                line = slip.line_ids.filtered(lambda l: l.code == code)
                return line.total if line else 0.0

            # INFORMACION
            gerencia = emp.department_id.parent_id.name if emp.department_id and emp.department_id.parent_id else (emp.department_id.name if emp.department_id else '')
            departamento = emp.department_id.name if emp.department_id else ''
            oficina = emp.department_id.name if emp.department_id else ''
            emp_id = emp.identification_id or str(emp.id)
            empleado = emp.name or ''

            # INGRESOS
            salario = get_line_amount('BASIC')
            # Horas Extras: HEL (Laboral), HEF (Feriado), HEN (Nocturna), HNI (Nocturna Inicio), HLT (Libre Trabajado)
            horas_extras = (get_line_amount('HEL') + get_line_amount('HEF') +
                          get_line_amount('HEN') + get_line_amount('HNI') + get_line_amount('HLT'))
            combustible = get_line_amount('COMB')
            comisiones = get_line_amount('COM')
            retroactivo = 0.0  # No hay código específico
            vacaciones = get_line_amount('VAC') + get_line_amount('PVAC')
            total_pagos = salario + horas_extras + combustible + comisiones + retroactivo + vacaciones

            # DEDUCCIONES
            afp = get_line_amount('SVDSE')
            cxc = get_line_amount('PRE') + get_line_amount('DDSL')
            seguro_comp = get_line_amount('SEC')
            sfs = get_line_amount('SFSE')
            sfs_dep = get_line_amount('DEPA')
            total_ded = afp + cxc + seguro_comp + sfs + sfs_dep

            # BENEFICIOS (Contribuciones del empleador)
            aporte_afp = get_line_amount('SVDSC')
            srl = get_line_amount('SRLC')
            aporte_sfs = get_line_amount('SFSC')
            total_ben = aporte_afp + srl + aporte_sfs

            # ISR
            isr = get_line_amount('ISR')
            total_isr = isr

            # NETO
            neto = get_line_amount('NET')

            # Escribir datos
            worksheet.write(f'A{row}', gerencia, data_format)
            worksheet.write(f'B{row}', departamento, data_format)
            worksheet.write(f'C{row}', oficina, data_format)
            worksheet.write(f'D{row}', emp_id, data_format)
            # Merge de EMPLEADO en E-F
            worksheet.merge_range(f'E{row}:F{row}', empleado, data_format)

            worksheet.write(f'G{row}', salario, number_format)
            worksheet.write(f'H{row}', horas_extras, number_format)
            worksheet.write(f'I{row}', combustible, number_format)
            worksheet.write(f'J{row}', comisiones, number_format)
            worksheet.write(f'K{row}', retroactivo, number_format)
            worksheet.write(f'L{row}', vacaciones, number_format)
            worksheet.write(f'M{row}', total_pagos, number_format)

            worksheet.write(f'N{row}', afp, number_format)
            worksheet.write(f'O{row}', cxc, number_format)
            worksheet.write(f'P{row}', seguro_comp, number_format)
            worksheet.write(f'Q{row}', sfs, number_format)
            worksheet.write(f'R{row}', sfs_dep, number_format)
            worksheet.write(f'S{row}', total_ded, number_format)

            worksheet.write(f'T{row}', aporte_afp, number_format)
            worksheet.write(f'U{row}', srl, number_format)
            worksheet.write(f'V{row}', aporte_sfs, number_format)
            worksheet.write(f'W{row}', total_ben, number_format)

            worksheet.write(f'X{row}', isr, number_format)
            worksheet.write(f'Y{row}', total_isr, number_format)
            worksheet.write(f'Z{row}', neto, number_format)

            # Acumular totales
            totals['salario'] += salario
            totals['horas_extras'] += horas_extras
            totals['combustible'] += combustible
            totals['comisiones'] += comisiones
            totals['retroactivo'] += retroactivo
            totals['vacaciones'] += vacaciones
            totals['total_pagos'] += total_pagos
            totals['afp'] += afp
            totals['cxc'] += cxc
            totals['seguro_comp'] += seguro_comp
            totals['sfs'] += sfs
            totals['sfs_dep'] += sfs_dep
            totals['total_ded'] += total_ded
            totals['aporte_afp'] += aporte_afp
            totals['srl'] += srl
            totals['aporte_sfs'] += aporte_sfs
            totals['total_ben'] += total_ben
            totals['isr'] += isr
            totals['total_isr'] += total_isr
            totals['neto'] += neto

            row += 1

        # Fila de subtotales
        worksheet.merge_range(f'D{row}:F{row}', 'Sub Total', section_header_format)
        worksheet.write(f'G{row}', totals['salario'], subtotal_format)
        worksheet.write(f'H{row}', totals['horas_extras'], subtotal_format)
        worksheet.write(f'I{row}', totals['combustible'], subtotal_format)
        worksheet.write(f'J{row}', totals['comisiones'], subtotal_format)
        worksheet.write(f'K{row}', totals['retroactivo'], subtotal_format)
        worksheet.write(f'L{row}', totals['vacaciones'], subtotal_format)
        worksheet.write(f'M{row}', totals['total_pagos'], subtotal_format)
        worksheet.write(f'N{row}', totals['afp'], subtotal_format)
        worksheet.write(f'O{row}', totals['cxc'], subtotal_format)
        worksheet.write(f'P{row}', totals['seguro_comp'], subtotal_format)
        worksheet.write(f'Q{row}', totals['sfs'], subtotal_format)
        worksheet.write(f'R{row}', totals['sfs_dep'], subtotal_format)
        worksheet.write(f'S{row}', totals['total_ded'], subtotal_format)
        worksheet.write(f'T{row}', totals['aporte_afp'], subtotal_format)
        worksheet.write(f'U{row}', totals['srl'], subtotal_format)
        worksheet.write(f'V{row}', totals['aporte_sfs'], subtotal_format)
        worksheet.write(f'W{row}', totals['total_ben'], subtotal_format)
        worksheet.write(f'X{row}', totals['isr'], subtotal_format)
        worksheet.write(f'Y{row}', totals['total_isr'], subtotal_format)
        worksheet.write(f'Z{row}', totals['neto'], subtotal_format)

        # Cerrar workbook
        workbook.close()

        # Preparar archivo para descarga
        output.seek(0)
        xlsx_data = output.read()
        output.close()

        # Generar nombre de archivo
        date_str = self.date_end.strftime('%Y%m%d') if self.date_end else datetime.now().strftime('%Y%m%d')
        filename = f'Reporte_Nomina_{self.name.replace("/", "-")}_{date_str}.xlsx'

        # MODIFICADO: Arturo Diaz Lora - 2026-04-03
        # Razón: Escribir en payment_report (campo base v19) para que el botón kanban de descarga funcione
        xlsx_b64 = base64.b64encode(xlsx_data)
        self.write({
            'payroll_xlsx_file_name': filename,
            'payroll_xlsx_binary': xlsx_b64,
            'payment_report': xlsx_b64,
            'payment_report_filename': filename,
            'payment_report_format': 'xlsx',
            'payment_report_date': fields.Date.today(),
        })

        # Retornar acción para descargar
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content?model=hr.payslip.run&id={self.id}&field=payment_report&filename_field=payment_report_filename&download=true',
            'target': 'self',
        }

    # MÉTODO COMENTADO: Ahora se debe generar el archivo desde el módulo de Nómina Electrónica (electronic.payroll)
    # Este método generaba un formato específico de BHD que no cumple con el estándar de Pagos Electrónicos 2023
    # Se debe usar el módulo l10n_do_hr_payroll_bank para generar archivos según especificación bancaria
    #
    # def generate_payroll_xlsx(self):
    #     if len(self.slip_ids) > 0:
    #         records = ''
    #         empleados = ''
    #
    #         for rec in self.slip_ids:
    #             if rec.employee_id.bank_account_id.acc_number:
    #                 values = {
    #                     'numero_cuenta': rec.employee_id.bank_account_id.acc_number or '',
    #                     'nombre_empleado': rec.employee_id.name or '',
    #                     'documento': rec.employee_id.identification_id.strip().replace('-', '') or '',
    #                     'monto_apagar': rec.line_ids.filtered(lambda line_ids: line_ids.code == 'NET').total or '',
    #                     'comentario': self.name or ''
    #                 }
    #                 records += self.process_report_data(values) + '\n'
    #             else:
    #                 monto = str('{:,.2f}'.format(abs(rec.line_ids.filtered(
    #                     lambda line_ids: line_ids.code == 'NET').total)))
    #                 empleados += str(rec.employee_id.name) + "| Monto Pagar: " + monto + '\n'
    #
    #         payroll_date = self.date_end
    #         data = records
    #         file_path = '/tmp/BHD_NOMINA_{}.txt'.format(payroll_date)
    #         with open(file_path, 'w', encoding="utf-8", newline='\r\n') as txt:
    #             txt.write(str(data))
    #
    #         self.write({
    #             'payroll_xlsx_file_name': file_path.replace('/tmp/', ''),
    #             'payroll_xlsx_binary': base64.b64encode(open(file_path, 'rb').read())
    #         })
    #
    #         if empleados:
    #             view = self.env.ref('sh_message.sh_message_wizard')
    #             view_id = view and view.id or False
    #             context = dict(self.env.context or {})
    #             context['message'] = str(
    #                 _('Acontinuacion Empleado(s) SIN CUENTA DE BANCO VER: \n \n{}').format(empleados))
    #             return {
    #                 'name': 'Verificar',
    #                 'type': 'ir.actions.act_window',
    #                 'view_type': 'form',
    #                 'view_mode': 'form',
    #                 'res_model': 'sh.message.wizard',
    #                 'views': [(view.id, 'form')],
    #                 'view_id': view.id,
    #                 'target': 'new',
    #                 'context': context
    #             }
    #     else:
    #         raise ValidationError(u"Debe generar la nómina primero.")

    def assign_worked_hours(self):
        for payslip in self.slip_ids:
            for wdl in payslip.worked_days_line_ids:
                wdl.number_of_hours = payslip.real_worked_hours

    def compute_all_payslips(self):
        if len(self.slip_ids) < 1:
            raise ValidationError(u"Debe generar alguna nómina primero.")
        self.assign_worked_hours()
        for payslip in self.slip_ids.filtered(lambda slip: slip.state != 'validated'):
            payslip.compute_sheet()

    def confirm_all_payslips(self):
        for payslip in self.slip_ids.filtered(lambda slip: slip.state != 'validated'):
            payslip.action_payslip_done()

    # Los campos date_start y date_end son de solo lectura, no se permiten cambios
    # @api.onchange('date_start')
    # def onchange_date_start(self):
    #     if not self.date_start:
    #         return
    #     for payslip in self.slip_ids:
    #         payslip.date_from = self.date_start

    # @api.onchange('date_end')
    # def onchange_date_end(self):
    #     if not self.date_end:
    #         return
    #     for payslip in self.slip_ids:
    #         payslip.date_to = self.date_end

    # def action_mail_send(self):
    #     for slip in self.slip_ids.filtered(lambda s: s.state == 'validated'):
    #         slip.action_mail_send()

    def action_payslip_batch_send(self):
        """Enviar nóminas en lote usando implementación segura"""
        for payslip in self.slip_ids:
            payslip._send_payslip_email_safe()

        message = "All payslips sent successfully"
        self.env["bus.bus"]._sendone(
            self.env.user.partner_id,
            "simple_notification",
            {"title": _("Notification"), "message": message, "sticky": False},
        )

    def action_generate_check_payments(self):
        """
        Genera pagos por lote de cheques para todos los empleados que tienen forma de pago 'Cheque'
        El nombre del lote será igual al nombre del hr.payslip.run
        """
        self.ensure_one()

        # Validar que la nómina esté en estado 'close' (Listo)
        if self.state != '02_close':
            raise UserError(_('Solo se pueden generar cheques cuando la nómina está en estado "Listo".'))

        # Validar que existan nóminas confirmadas
        if not self.slip_ids:
            raise UserError(_('No hay nóminas generadas en este lote.'))

        # Filtrar empleados con forma de pago 'Cheque' y que tengan nóminas confirmadas
        check_slips = self.slip_ids.filtered(
            lambda s: s.state == 'validated' and s.employee_id.pay_form == 'cheque'
        )

        if not check_slips:
            raise UserError(_(
                'No se encontraron empleados con forma de pago "Cheque" en este lote.\n\n'
                'Asegúrese de que:\n'
                '1. Las nóminas estén confirmadas (estado "Hecho")\n'
                '2. Los empleados tengan configurado "Forma de Pago" = "Cheque" en su ficha'
            ))

        # Crear los pagos de cheques
        created_payments = self.env['account.payment']
        errors = []

        for slip in check_slips:
            employee = slip.employee_id

            # Validar que el empleado tenga diario de pago configurado
            if not employee.payment_journal_id:
                errors.append(f"• {employee.name}: No tiene configurado un Diario de Pago")
                continue

            journal = employee.payment_journal_id

            # Validar que el diario tenga el método de pago 'check_printing' habilitado
            payment_method_line = journal.outbound_payment_method_line_ids.filtered(
                lambda l: l.code == 'check_printing'
            )

            if not payment_method_line:
                errors.append(
                    f"• {employee.name}: El diario '{journal.name}' no tiene habilitado el método de pago 'Checks'.\n"
                    f"  Por favor, habilite el método 'Checks' en: Contabilidad > Configuración > Diarios > {journal.name} > Pestaña 'Pagos Salientes'"
                )
                continue

            partner = employee.work_contact_id or employee.user_id.partner_id

            if not partner:
                errors.append(f"• {employee.name}: No tiene contacto de trabajo ni usuario asociado")
                continue

            # Obtener el monto neto de la nómina
            net_amount = slip.line_ids.filtered(lambda l: l.code == 'NET').total or 0.0

            if net_amount <= 0:
                errors.append(f"• {employee.name}: Monto neto es cero o negativo ({net_amount})")
                continue

            try:
                # Crear el pago usando el método de pago 'check_printing' del diario del empleado
                payment_vals = {
                    'payment_type': 'outbound',
                    'partner_type': 'supplier',
                    'partner_id': partner.id,
                    'amount': net_amount,
                    'journal_id': journal.id,
                    'payment_method_line_id': payment_method_line.id,
                    'date': self.date_end or fields.Date.today(),
                    'payment_reference': self.name,  # Usar el nombre del lote como referencia
                    'memo': f'Nómina: {self.name} - {employee.name}',
                }

                payment = self.env['account.payment'].create(payment_vals)
                created_payments |= payment

            except Exception as e:
                errors.append(f"• {employee.name}: Error al crear pago - {str(e)}")

        # Mostrar resultado
        if errors:
            error_msg = _('Advertencias al generar cheques:\n\n') + '\n'.join(errors)
            if created_payments:
                error_msg += _('\n\nSe generaron %d cheques exitosamente.') % len(created_payments)
                # Mostrar notificación de advertencia
                self.env["bus.bus"]._sendone(
                    self.env.user.partner_id,
                    "simple_notification",
                    {"title": _("Generación Parcial"), "message": error_msg, "type": "warning", "sticky": True},
                )
            else:
                raise UserError(error_msg)

        # Mostrar notificación de éxito
        if created_payments and not errors:
            success_msg = _('Se generaron %d cheques exitosamente para el lote: %s') % (len(created_payments), self.name)
            self.env["bus.bus"]._sendone(
                self.env.user.partner_id,
                "simple_notification",
                {"title": _("Cheques Generados"), "message": success_msg, "type": "success", "sticky": False},
            )

        # Abrir vista de pagos generados
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pagos de Cheques - %s') % self.name,
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created_payments.ids)],
            'context': {
                'create': False,
                'default_payment_type': 'outbound',
                'default_partner_type': 'supplier',
            },
            'target': 'current',
        }


# NOTA: En Odoo 19, hr.payslip.employees wizard fue eliminado.
# La generación de nóminas se hace a través de hr.payslip.run.generate_payslips()
# La lógica de regalía pascual está implementada en el override de generate_payslips arriba.

