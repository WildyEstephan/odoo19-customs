
from odoo import models, api, fields, _


class AccountMoveReversal(models.TransientModel):
    _inherit = "account.move.reversal"

    def reverse_moves(self, is_modify=False):
        res = super(AccountMoveReversal, self.with_context(
                propagate_is_modify=is_modify,
        )).reverse_moves(is_modify)
        if isinstance(res, dict):
            move = self.env['account.move']
            if 'res_id' in res:
                inv_obj = move.search([('id', '=', res['res_id'])])
            elif res['domain']:
                for d in res['domain']:
                    if d[0] == 'id':
                        inv_obj = move.search([('id', '=', d[2][0])])
                        break

            if inv_obj:
                active_id = self.env.context['active_id']
                move_active = self.env['account.move'].search([('id', '=', active_id)])

                vals = {
                    'l10n_do_ecf_modification_code': self.l10n_do_ecf_modification_code,
                    'invoice_payment_term_id': move_active.invoice_payment_term_id.id,
                }

                inv_obj.write(vals)

        return res
