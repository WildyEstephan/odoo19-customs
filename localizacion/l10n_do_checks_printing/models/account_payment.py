from odoo import models, api, fields, _
from odoo.exceptions import ValidationError
from . import number_to_word


class AccountPayment(models.Model):
    _inherit = "account.payment"

    amont_in_word = fields.Char("En letras", compute="_compute_amont_in_word")
    check_name = fields.Many2one("res.partner", string="A nombre de")

    @api.depends("amount")
    def _compute_amont_in_word(self):
        for rec in self:
            rec.amont_in_word = number_to_word.to_word(rec.amount, rec.currency_id.name)

    @api.onchange('amount', 'currency_id')
    def _onchange_amount(self):
        if self.amount and self.currency_id:
            self.check_amount_in_words = number_to_word.to_word(self.amount, self.currency_id.name)

    @api.onchange("check_number")
    def onchange_check_number(self):
        for payment in self:
            if payment.payment_method_code == "check_printing":
                if not payment.check_number:
                    return True
                check_duplicate = payment.search([
                    ('journal_id', '=', payment.journal_id.id),
                    ('check_number', '=', payment.check_number),
                    ('state', '!=', 'cancel'),
                    ('payment_type', '=', 'outbound'),
                    ('payment_method_code', '=', "check_printing")])
                names = "\n".join([str(p.payment_reference or p.name) for p in check_duplicate])
                msg = "Este número de cheque: %s, fue usado.\n Estos son los " \
                      "conceptos:\n %s." % (payment.check_number, names)
                if len(check_duplicate) > 1:
                    raise ValidationError(_(msg))

    def action_post(self):
        for rec in self:
            if rec.payment_type == 'outbound':
                rec.onchange_check_number()
        return super().action_post()

    def do_print_checks(self):
        check_layout = self[0].journal_id.check_layout
        if check_layout:
            return self.env.ref('l10n_do_checks_printing.printing_check_report_action').report_action(self)
        return super(AccountPayment, self).do_print_checks()

    def print_checks(self):
        res = super().print_checks()
        if not self[0].journal_id.check_manual_sequencing:
            if self.check_number and len(self.check_number) > 0:
                res["context"].update({"default_next_check_number": self.check_number})
        self.filtered(lambda r: r.state == 'posted' and not r.is_move_sent).write({'is_move_sent': True})      
        return res