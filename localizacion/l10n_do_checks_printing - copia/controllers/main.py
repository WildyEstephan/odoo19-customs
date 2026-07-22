import logging
import re

from odoo import http, tools, _
from odoo.http import request

def slug(text):
    """
    Convierte una cadena de texto en un slug, eliminando caracteres especiales y reemplazando espacios con guiones.
    """
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text).strip('-')
    return text


_logger = logging.getLogger(__name__)


class BankChequeManagement(http.Controller):
    @http.route('/astra/bank/cheque/<model("check.report.config"):bank_cheque_id>', type='http', auth="user", website=True)
    def bank_cheque_management(self, bank_cheque_id, **post):
        values = {"bank_cheque_obj": bank_cheque_id}
        return request.render("l10n_do_checks_printing.bank_cheque_management_template", values)

    @http.route('/astra/bank/cheque/update', type='http', auth="user", website=True)
    def bank_cheque_update_attrs(self, **post):
        is_updated = False
        if post.get("cheque_attribute_line_id"):
            is_updated = request.env["bank.cheque.attribute.line"].browse(
                int(post.get('cheque_attribute_line_id'))).write({
                    "top_displacement": int(post.get("y1", 0)),
                    "left_displacement": int(post.get("x1")) if post.get("x1") else 0,
                    "height": int(post.get("h")) if post.get("h") else 0,
                    "width": int(post.get("w")) if post.get("w") else 0,
                    # "font_size": post.get(""),
                    # "font_family": post.get(""),
                })
        values = {
            "bank_cheque_obj": request.env["check.report.config"].browse(int(post.get('bank_cheque_id')))
            if post.get('bank_cheque_id') else False,
        }
        if is_updated:
            values.update({
                "updated_cheque_attribute_line_id": int(post.get('cheque_attribute_line_id'))
            })
        return request.redirect("/astra/bank/cheque/%s" % slug(values.get("bank_cheque_obj")))

    @http.route('/astra/bank/cheque/preview/<model("check.report.config"):bank_cheque_id>', type='http', auth="user", website=True)
    def bank_cheque_preview(self, bank_cheque_id, **post):
        values = {"bank_cheque_obj": bank_cheque_id}
        return request.render("l10n_do_checks_printing.bank_cheque_priview", values)
