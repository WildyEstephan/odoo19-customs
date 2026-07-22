# -*- encoding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.addons.l10n_do_hr_payroll_bank.bank_generator import generate_data_for_bank

_logger = logging.getLogger(__name__)


class ElectronicPayroll(models.Model):
    _name = 'electronic.payroll'
    _description = 'Electronic Payroll'

    @api.depends('line_ids.amount')
    def _compute_get_total(self):
        for rec in self:
            rec.total = sum([i.amount for i in rec.line_ids])
            rec.total_valid = sum([i.amount for i in rec.line_ids if not i.no_file])
            rec.total_cash = sum([i.amount for i in rec.line_ids if i.pay_form == 'cash'])
            rec.total_cheque = sum([i.amount for i in rec.line_ids if i.pay_form == 'cheque'])
            rec.total_trans = sum([i.amount for i in rec.line_ids if i.pay_form == 'trans'])

    name = fields.Char(readonly=True)
    description = fields.Char(string="Description")
    effective_date = fields.Date(string='Efective Date', required=True)
    payslip_run_id = fields.Many2one('hr.payslip.run', string='Payslip Run', required=True)
    journal_id = fields.Many2one(
        'account.journal',
        string='Medio de Pago',
        domain=[('type', 'in', ['bank', 'cash'])])
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda x: x.env.company
    )
    binary = fields.Binary(readonly=True)
    binary_name = fields.Char(readonly=True)
    binary_ext = fields.Selection(
        [('txt', 'TXT'), ('csv', 'CSV')], string='Extension', default='txt', required=True
    )
    total = fields.Float(compute='_compute_get_total', string='Total')
    total_valid = fields.Float(compute='_compute_get_total', string='Transferencia Valida')
    total_cheque = fields.Float(compute='_compute_get_total', string='Cheque a Pagar')
    total_cash = fields.Float(compute='_compute_get_total', string='Efectivo a Pagar')
    total_trans = fields.Float(compute='_compute_get_total', string='Transferencia a Pagar')
    line_ids = fields.One2many('electronic.payroll.line', 'electronic_id')
    line_tran_ids = fields.One2many('electronic.payroll.line', 'electronic_id', domain=[('pay_form', '=', 'trans')], readonly=True)
    line_cash_ids = fields.One2many('electronic.payroll.line', 'electronic_id', domain=[('pay_form', '=', 'cash')], readonly=True)
    line_cheque_ids = fields.One2many('electronic.payroll.line', 'electronic_id', domain=[('pay_form', '=', 'cheque')], readonly=True)
    sequence = fields.Char(readonly=True)

    @api.onchange('payslip_run_id')
    def onchange_run_id(self):
        self.effective_date = self.payslip_run_id.date_end

    def set_line_ids(self):
        for electronic in self:
            if electronic.line_ids:
                line_ids = self.env["electronic.payroll.line"]
                line_ids.search([("electronic_id", "=", electronic.id)]).sudo().unlink()
                # raise UserError(_('Already the lines are loaded.'))

            lines = []
            for slip in electronic.payslip_run_id.slip_ids:

                employee_id = slip.employee_id
                amount = slip._get_salary_line_total('NET')

                no_file = False
                if not amount or not employee_id.bank_account_id:
                    no_file = True

                lines.append(
                    (
                        0,
                        0,
                        {
                            'employee_id': employee_id.id,
                            'amount': amount,
                            'no_file': no_file,
                        },
                    )
                )

            electronic.line_ids = lines

    def generate_txt(self):
        if not self.line_ids:
            raise UserError(_('There are no lines to generate the file.'))

        # Validar que el diario tenga una cuenta bancaria asociada
        if not self.journal_id.bank_account_id:
            raise UserError(_(
                "Configuración de Nómina Electrónica Incompleta\n\n"
                "El diario '%s' no tiene una cuenta bancaria asociada.\n\n"
                "SOLUCIÓN:\n"
                "1. Vaya a: Contabilidad > Configuración > Diarios\n"
                "2. Abra el diario: %s\n"
                "3. En la pestaña 'Configuración Avanzada', complete el campo 'Número de Cuenta'\n"
                "4. Seleccione o cree una cuenta bancaria de la empresa\n"
                "5. Asegúrese de que la cuenta bancaria tenga configurado el 'Tipo de Nómina Electrónica'"
            ) % (self.journal_id.name, self.journal_id.name))

        ep_type = self.journal_id.bank_account_id.electronic_payroll_type
        if not ep_type:
            raise UserError(_(
                "Configuración de Nómina Electrónica Incompleta\n\n"
                "La cuenta bancaria '%s' del diario '%s' no tiene configurado el Tipo de Nómina Electrónica.\n\n"
                "SOLUCIÓN:\n"
                "1. Vaya a: Contabilidad > Configuración > Cuentas Bancarias\n"
                "2. Abra la cuenta bancaria: %s\n"
                "3. Complete el campo 'Tipo de Nómina Electrónica' seleccionando su banco:\n"
                "   • Banco BHD\n"
                "   • Banco Popular\n"
                "   • Banco Lopez de Haro\n"
                "   • Banco Reservas\n"
                "   • Banco Caribe\n"
                "4. Guarde los cambios e intente generar el archivo nuevamente"
            ) % (
                self.journal_id.bank_account_id.acc_number,
                self.journal_id.name,
                self.journal_id.bank_account_id.acc_number
            ))

        # ============================================================================
        # VALIDACIONES COMPLETAS DE CONFIGURACIÓN
        # Verificar TODOS los campos necesarios para evitar valores "False" en el TXT
        # ============================================================================

        errors = []
        warnings = []

        # 1. Validar RNC de la compañía
        if not self.company_id.vat:
            errors.append(
                "• RNC de la Compañía: No configurado\n"
                "  → Ir a: Configuración > Usuarios y Compañías > Compañías\n"
                "  → Abrir su compañía y completar el campo 'RNC'"
            )

        # 2. Validar Email (para el archivo TXT)
        bank_account = self.journal_id.bank_account_id
        if not bank_account.electronic_payroll_email and not self.company_id.email:
            warnings.append(
                "• Email de Nómina: No configurado (se enviará vacío)\n"
                "  → RECOMENDADO: Ir a: Contabilidad > Configuración > Cuentas Bancarias\n"
                "  → Abrir la cuenta: %s\n"
                "  → Completar el campo 'Email Payroll'\n"
                "  → ALTERNATIVA: Configurar email en su compañía" % bank_account.acc_number
            )

        # 3. Validar Código del Banco (para el nombre del archivo)
        if not bank_account.electronic_payroll_bank_code:
            warnings.append(
                "• Código del Banco: No configurado (se usará '00001' por defecto)\n"
                "  → RECOMENDADO: Ir a: Contabilidad > Configuración > Cuentas Bancarias\n"
                "  → Abrir la cuenta: %s\n"
                "  → Completar el campo 'Bank Code' con el código de 5 dígitos asignado por su banco"
                % bank_account.acc_number
            )

        # 4. Validar empleados sin cuenta bancaria
        records_no_bank = self.line_tran_ids.filtered(lambda r: not r.bank_account_id)
        if records_no_bank:
            employee_names = ', '.join(records_no_bank.mapped('employee_id.name')[:5])
            if len(records_no_bank) > 5:
                employee_names += f' ... y {len(records_no_bank) - 5} más'
            errors.append(
                f"• Empleados sin Cuenta Bancaria ({len(records_no_bank)}):\n"
                f"  → {employee_names}\n"
                f"  → Ir a: Nómina > Empleados\n"
                f"  → Completar el campo 'Cuenta Bancaria' para cada empleado"
            )

        # 5. Validar empleados sin identificación (cédula/pasaporte)
        records_no_id = self.line_tran_ids.filtered(
            lambda r: not r.employee_id.identification_id and not r.employee_id.passport_id
        )
        if records_no_id:
            employee_names = ', '.join(records_no_id.mapped('employee_id.name')[:5])
            if len(records_no_id) > 5:
                employee_names += f' ... y {len(records_no_id) - 5} más'
            errors.append(
                f"• Empleados sin Cédula/Pasaporte ({len(records_no_id)}):\n"
                f"  → {employee_names}\n"
                f"  → Ir a: Nómina > Empleados\n"
                f"  → Completar el campo 'Identification No' (cédula) o 'Passport No' (pasaporte)"
            )

        # Si hay errores críticos, mostrar mensaje completo
        if errors:
            error_message = (
                "⚠️ CONFIGURACIÓN INCOMPLETA - No se puede generar el archivo TXT\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Los siguientes campos OBLIGATORIOS están incompletos:\n\n"
            )
            error_message += '\n\n'.join(errors)
            error_message += (
                "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Complete estos campos e intente generar el archivo nuevamente."
            )
            raise UserError(_(error_message))

        # Si solo hay advertencias, mostrar pero continuar
        if warnings:
            warning_message = (
                "⚡ CONFIGURACIÓN OPCIONAL INCOMPLETA\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "El archivo se generará con valores por defecto para:\n\n"
            )
            warning_message += '\n\n'.join(warnings)
            warning_message += (
                "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Se recomienda configurar estos campos para evitar problemas con el banco.\n"
                "¿Desea continuar de todas formas?\n\n"
                "Nota: El archivo se generará correctamente, pero algunos bancos pueden\n"
                "rechazarlo si falta el Email o el Código del Banco."
            )
            # Registrar advertencia en el log
            _logger.warning(warning_message)

        # ============================================================================
        # Generar el archivo TXT
        # ============================================================================

        file_io, name_report = generate_data_for_bank(ep_type, self)

        self.write({'binary': file_io, 'binary_name': name_report})

    def account_payment_method(self, date=None):
        """
        Method to create account Payment for each employee and Post it.

        :param date: Date the payment will be registered.
        """

        if not date:
            date = fields.Date.today()

        Payments = self.env['account.payment']

        line_ids = self.line_ids.filtered(lambda r: r.no_file is False)

        name = self.name
        payment_method_id = self.journal_id.inbound_payment_method_ids[0]
        journal_id = self.journal_id.id
        currency_id = self.company_id.currency_id.id
        for line in line_ids:
            partner_id = line.employee_id.address_home_id
            # partner_id.property_account_receivable_id = self.company_id.electronic_payroll_account_account.id
            payment_info = {
                'partner_id': partner_id.id,
                'payment_type': 'outbound',
                'partner_type': 'supplier',
                'amount': line.amount,
                'journal_id': journal_id,
                'currency_id': currency_id,
                'payment_date': date,
                'communication': _('Electronic Payroll: %s' % name),
                'payment_method_id': payment_method_id.id,
            }
            if hasattr(Payments, 'force_destination_account_id'):
                payment_info['force_destination_account_id'] = self.company_id.electronic_payroll_account_account.id

            payment_id = self.env['account.payment'].create(payment_info)
            Payments += payment_id

        self.write({'payment_count': len(line_ids), 'date_payment': date})
        Payments.post()
        Payments.create_batch_payment()


class ElectronicPayrollLine(models.Model):
    _name = 'electronic.payroll.line'
    _description = 'Electronic Payroll Line'

    electronic_id = fields.Many2one(
        'electronic.payroll',
        string='Electonic Payroll')
    # MODIFICADO: Arturo Diaz Lora - 2026-03-14 10:00
    # Razón: Agregar company_id related para soporte multi-company
    company_id = fields.Many2one('res.company', related='electronic_id.company_id', store=True, index=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Employee',
        readonly=True)

    bank_account_id = fields.Many2one(
        'res.partner.bank',
        related='employee_id.bank_account_id')
    pay_form = fields.Selection(
        related='employee_id.pay_form')

    amount = fields.Float('Amount', readonly=True)

    no_file = fields.Boolean(string='Fuera de Archivo')
