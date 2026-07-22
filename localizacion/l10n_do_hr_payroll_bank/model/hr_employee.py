
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class HREmployee(models.Model):
    _inherit = 'hr.employee'

    pay_form = fields.Selection([
        ('trans', 'Transferencia Bancaria'),
        ('cash', 'Efectivo'),
        ('cheque', 'Cheque')
    ], string='Forma de Pago')

    bank_account_id = fields.Many2one(
        'res.partner.bank',
        string='Cuenta Bancaria'
    )

    payment_journal_id = fields.Many2one(
        'account.journal',
        string='Diario de Pago',
        domain="[('type', '=', 'bank')]",
        help='Diario bancario que se utilizará para generar los pagos de cheques o efectivo'
    )

    @api.constrains('pay_form', 'payment_journal_id')
    def _check_payment_journal_required(self):
        """Validar que el diario de pago sea obligatorio para cheques y efectivo"""
        for employee in self:
            if employee.pay_form in ('cheque', 'cash') and not employee.payment_journal_id:
                raise ValidationError(_(
                    'El empleado %s tiene forma de pago "%s" pero no tiene configurado un Diario de Pago.\n\n'
                    'Por favor, seleccione un diario bancario en el campo "Diario de Pago".'
                ) % (employee.name, dict(employee._fields['pay_form'].selection).get(employee.pay_form)))
