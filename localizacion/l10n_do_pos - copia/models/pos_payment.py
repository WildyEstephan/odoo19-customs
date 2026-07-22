from odoo import models, fields, api, _
from odoo.tools import float_is_zero
import logging

_logger = logging.getLogger(__name__)


class PosPayment(models.Model):
    _inherit = "pos.payment"

    credit_note_id = fields.Integer()
    note = fields.Char()
    res_model = fields.Char()

    def _create_payment_moves(self, is_reverse=False):
        """
        Interviene la creación del asiento contable para verificar si el método de pago usado es tipo Nota de Crédito.
        Si es NC, concilia la factura del POS con la nota de crédito.

        Autor: Arturo Diaz Lora
        Fecha: 2025-11-28
        Razón: El código anterior solo devolvía el movimiento pero NO conciliaba.
               Ahora se realiza la conciliación automática entre la factura y la NC.

        MODIFICADO: Arturo Diaz Lora - 2026-01-23
        Razón: Corregido error cuando accounting_partner está vacío.
               Ahora usa account_default_pos_receivable_account_id como fallback.

        :return: account.move
        """
        moves = self.env['account.move']
        records = self
        credit_note_payments = self.env['pos.payment']  # Pagos con NC para conciliar después
        payments_without_partner = self.env['pos.payment']  # Pagos sin partner

        for payment in self:
            order = payment.pos_order_id
            payment_method = payment.payment_method_id

            if payment_method.type == 'credit_note':
                _logger.info(f"[L10N_DO_POS] Procesando pago con Nota de Credito: {payment.note}")

                info = order.credit_note_info_from_ui(payment.note)
                _logger.info(f"[L10N_DO_POS] Info de NC: {info}")

                if info.get('id'):
                    credit_note = self.env[info['model']].browse(info['id'])
                    payment.write({'res_model': info['model']})

                    # Obtener el account.move de la NC
                    if credit_note._name == 'pos.order':
                        credit_note_move = credit_note.account_move
                    else:
                        credit_note_move = credit_note

                    moves |= credit_note_move
                    credit_note_payments |= payment
                    _logger.info(f"[L10N_DO_POS] NC encontrada: {credit_note_move.name} (ID: {credit_note_move.id})")

                records -= payment

            # Verificar si el pago tiene partner válido para evitar error de account_id NULL
            elif not payment.partner_id:
                payments_without_partner |= payment
                records -= payment
                _logger.info(f"[L10N_DO_POS] Pago sin partner detectado, procesando con cuenta default")

        # Procesar pagos sin partner manualmente con cuenta default
        for payment in payments_without_partner:
            move = self._create_payment_move_without_partner(payment, is_reverse)
            if move:
                moves |= move

        # Procesar pagos normales (no NC y con partner)
        rstl = super(PosPayment, records)._create_payment_moves(is_reverse)
        rstl |= moves

        # Conciliar las notas de crédito con las facturas del POS
        for payment in credit_note_payments:
            try:
                self._reconcile_credit_note_with_invoice(payment)
            except Exception as e:
                _logger.error(f"[L10N_DO_POS] Error conciliando NC: {e}")

        return rstl

    def _create_payment_move_without_partner(self, payment, is_reverse=False):
        """
        Crea el movimiento de pago cuando no hay partner.
        Usa la cuenta default de POS de la compañía.

        AGREGADO: Arturo Diaz Lora - 2026-01-23
        Razón: Manejar pagos sin partner usando account_default_pos_receivable_account_id
        """
        order = payment.pos_order_id
        payment_method = payment.payment_method_id

        if payment_method.type == 'pay_later' or float_is_zero(payment.amount, precision_rounding=order.currency_id.rounding):
            return None

        pos_session = order.session_id
        journal = pos_session.config_id.journal_id
        company = order.company_id

        # Usar la cuenta default de POS como fallback
        default_receivable_account = company.account_default_pos_receivable_account_id
        if not default_receivable_account:
            _logger.error(f"[L10N_DO_POS] No hay cuenta default de POS configurada en la compañía")
            return None

        _logger.info(f"[L10N_DO_POS] Usando cuenta default de POS: {default_receivable_account.id}")

        payment_move = self.env['account.move'].with_context(default_journal_id=journal.id).create({
            'journal_id': journal.id,
            'date': fields.Date.context_today(order, order.date_order),
            'ref': _('Invoice payment for %(order)s (%(account_move)s) using %(payment_method)s',
                    order=order.name,
                    account_move=order.account_move.name if order.account_move else '',
                    payment_method=payment_method.name),
            'pos_payment_ids': payment.ids,
        })

        payment.write({'account_move_id': payment_move.id})

        amounts = pos_session._update_amounts(
            {'amount': 0, 'amount_converted': 0},
            {'amount': payment.amount},
            payment.payment_date
        )

        # Línea de crédito con cuenta default de POS
        credit_line_vals = pos_session._credit_amounts({
            'account_id': default_receivable_account.id,
            'partner_id': False,
            'move_id': payment_move.id,
            'no_followup': False,
        }, amounts['amount'], amounts['amount_converted'])

        # Línea de débito
        debit_account_id = payment_method.receivable_account_id.id or default_receivable_account.id
        debit_line_vals = pos_session._debit_amounts({
            'account_id': debit_account_id,
            'move_id': payment_move.id,
            'partner_id': False,
            'no_followup': False,
        }, amounts['amount'], amounts['amount_converted'])

        self.env['account.move.line'].create([credit_line_vals, debit_line_vals])
        payment_move._post()

        _logger.info(f"[L10N_DO_POS] Movimiento de pago creado sin partner: {payment_move.id}")

        return payment_move

    def _reconcile_credit_note_with_invoice(self, payment):
        """
        Concilia una nota de crédito con la factura de la orden POS.

        Autor: Arturo Diaz Lora
        Fecha: 2025-11-28
        Razón: Implementar la conciliación automática entre NC y factura del POS.
        """
        order = payment.pos_order_id
        invoice = order.account_move

        if not invoice:
            _logger.warning(f"[L10N_DO_POS] Orden {order.name} no tiene factura asociada")
            return

        # Obtener la nota de crédito
        info = order.credit_note_info_from_ui(payment.note)
        if not info.get('id'):
            _logger.warning(f"[L10N_DO_POS] No se encontro NC con NCF: {payment.note}")
            return

        credit_note = self.env[info['model']].browse(info['id'])
        if credit_note._name == 'pos.order':
            credit_note_move = credit_note.account_move
        else:
            credit_note_move = credit_note

        _logger.info(f"[L10N_DO_POS] ========== CONCILIACION NC ==========")
        _logger.info(f"[L10N_DO_POS] Factura: {invoice.name} (ID: {invoice.id})")
        _logger.info(f"[L10N_DO_POS] Factura saldo: {invoice.amount_residual}")
        _logger.info(f"[L10N_DO_POS] NC: {credit_note_move.name} (ID: {credit_note_move.id})")
        _logger.info(f"[L10N_DO_POS] NC saldo: {credit_note_move.amount_residual}")
        _logger.info(f"[L10N_DO_POS] Monto a conciliar: {payment.amount}")

        # Buscar las líneas a conciliar
        # La factura tiene líneas de cuenta por cobrar (receivable)
        # La NC tiene líneas de cuenta por cobrar con signo opuesto
        invoice_receivable_lines = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
        )
        credit_note_receivable_lines = credit_note_move.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
        )

        _logger.info(f"[L10N_DO_POS] Lineas factura por cobrar: {len(invoice_receivable_lines)}")
        _logger.info(f"[L10N_DO_POS] Lineas NC por cobrar: {len(credit_note_receivable_lines)}")

        if invoice_receivable_lines and credit_note_receivable_lines:
            # Combinar las líneas para conciliar
            lines_to_reconcile = invoice_receivable_lines | credit_note_receivable_lines

            _logger.info(f"[L10N_DO_POS] Lineas a conciliar: {lines_to_reconcile.ids}")

            # Realizar la conciliación
            lines_to_reconcile.reconcile()

            _logger.info(f"[L10N_DO_POS] Conciliacion exitosa!")
            _logger.info(f"[L10N_DO_POS] Factura saldo despues: {invoice.amount_residual}")
            _logger.info(f"[L10N_DO_POS] NC saldo despues: {credit_note_move.amount_residual}")
        else:
            _logger.warning(f"[L10N_DO_POS] No se encontraron lineas para conciliar")
            if not invoice_receivable_lines:
                _logger.warning(f"[L10N_DO_POS] - Factura no tiene lineas receivable sin conciliar")
            if not credit_note_receivable_lines:
                _logger.warning(f"[L10N_DO_POS] - NC no tiene lineas receivable sin conciliar")

        _logger.info(f"[L10N_DO_POS] =======================================")
