from odoo import models, fields, api, _
import logging
_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    ecf_id = fields.Many2one(related='account_move.ecf_id', string='ECF Document', copy=False)
    l10n_do_ecf_send_state = fields.Selection(related='account_move.l10n_do_ecf_send_state', string='DGII State',
                                              store=True, copy=False, readonly=True)

    # QR
    l10n_do_ecf_security_code = fields.Char(string="e-CF Security Code", related="account_move.l10n_do_ecf_security_code")
    l10n_do_ecf_sign_date = fields.Datetime(string="e-CF Sign Date", related="account_move.l10n_do_ecf_sign_date")
    l10n_do_electronic_stamp = fields.Text(string="Electronic Stamp", related="account_move.l10n_do_electronic_stamp")
    QR_code = fields.Binary(string="Code QR", related="account_move.QR_code")

    def _export_for_ui(self, order):
        result = super(PosOrder, self)._export_for_ui(order)
        result.update({
            'l10n_do_ecf_security_code': order.l10n_do_ecf_security_code,
            'l10n_do_ecf_sign_date': order.l10n_do_ecf_sign_date.strftime('%Y-%m-%d %H:%M:%S') if order.l10n_do_ecf_sign_date else False,
            'QR_code': order.QR_code,
        })
        return result

    @api.model
    def create_from_ui(self, orders, draft=False):
        res = super(PosOrder, self).create_from_ui(orders, draft)

        for record in res:
            order = self.browse(record.get('id'))
            record['l10n_do_ecf_security_code'] = order.l10n_do_ecf_security_code
            record['l10n_do_ecf_sign_date'] = order.l10n_do_ecf_sign_date.strftime('%Y-%m-%d %H:%M:%S') if order.l10n_do_ecf_sign_date else False
            record['QR_code'] = order.QR_code

        return res
