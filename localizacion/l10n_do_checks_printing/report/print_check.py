#  Copyright (c) 2015 - Marcos Organizador de Negocios SRL.
#  (<https://marcos.do/>)
#  Write by Eneldo Serrata (eneldo@marcos.do)
from odoo import models, api


class PrintCheck(models.AbstractModel):
    _name = 'report.l10n_do_checks_printing.check_print_report'

    @api.model
    def _get_report_values(self, docids, data=None):
        records = self.env['account.payment'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': records.model,
            'docs': records,
            'data': data,
        }

