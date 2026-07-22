from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    use_credit_note = fields.Boolean("Usar para Nota de Crédito")
    type = fields.Selection(selection_add=[('credit_note', 'Nota de Crédito')])
    l10n_do_payment_form = fields.Selection(
        selection="_get_l10n_do_payment_form",
        string="Forma de Pago",
    )

    @api.depends('journal_id', 'split_transactions', 'type')
    def _compute_type(self):
        super()._compute_type()
        for pm in self:
            if pm.use_credit_note:
                pm.type = 'credit_note'

    def _get_l10n_do_payment_form(self):
        return self.env['account.journal'].sudo()._get_l10n_do_payment_form()

    @api.onchange('cash_journal_id')
    def change_cash_journal_id(self):
        self.l10n_do_payment_form = self.cash_journal_id.l10n_do_payment_form

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create para asegurar que is_cash_count se calcule correctamente
        después de crear un nuevo método de pago.

        Esto previene el problema donde el saldo de efectivo muestra 0 en sesiones POS
        cuando is_cash_count no está correctamente calculado.
        """
        records = super().create(vals_list)

        # Forzar recálculo de is_cash_count para métodos con journal tipo 'cash'
        cash_methods = records.filtered(lambda pm: pm.journal_id and pm.journal_id.type == 'cash')
        if cash_methods:
            _logger.info(f"[L10N_DO_POS] Forcing is_cash_count recalculation for {len(cash_methods)} cash payment methods")
            cash_methods._ensure_is_cash_count_computed()

        return records

    def write(self, vals):
        """
        Override write para asegurar que is_cash_count se recalcule cuando
        cambia el journal asociado al método de pago.

        Esto previene inconsistencias en el cálculo de saldos de efectivo.
        """
        result = super().write(vals)

        # Si se cambió el journal, recalcular is_cash_count
        if 'journal_id' in vals or 'use_credit_note' in vals:
            cash_methods = self.filtered(lambda pm: pm.journal_id and pm.journal_id.type == 'cash')
            if cash_methods:
                _logger.info(f"[L10N_DO_POS] Forcing is_cash_count recalculation after write for {len(cash_methods)} cash payment methods")
                cash_methods._ensure_is_cash_count_computed()

        return result

    def _ensure_is_cash_count_computed(self):
        """
        Fuerza el recálculo de los campos computed 'type' e 'is_cash_count'.

        Este método debe llamarse cuando:
        - Se crea un nuevo método de pago con journal tipo 'cash'
        - Se modifica el journal de un método de pago existente
        - Se necesita corregir registros con is_cash_count incorrecto

        Soluciona el problema donde sesiones POS muestran saldo de efectivo = 0
        debido a is_cash_count = False cuando debería ser True.
        """
        if not self:
            return

        # Invalidar caché para forzar recálculo
        self.invalidate_recordset(['type', 'is_cash_count'])

        # Forzar recálculo de campos computed
        self._compute_type()
        self._compute_is_cash_count()

        # Log para debugging
        for pm in self:
            _logger.info(
                f"[L10N_DO_POS] Payment method '{pm.name}': "
                f"journal_type={pm.journal_id.type if pm.journal_id else 'None'}, "
                f"type={pm.type}, is_cash_count={pm.is_cash_count}"
            )
