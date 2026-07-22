
from odoo import models, fields

class InheritedAccountJournal(models.Model):
    _inherit = "account.journal"

    statement_import_type = fields.Selection([
        ('manual', 'Plantilla Manual'),
        ],
        default='manual', 
        string=u"Formato de Conciliacion del Banco")

    is_tc = fields.Boolean(
        string='Es Tarjeta de Credito ?',
    )
    
    def import_account_statement(self):
        """return action to import bank/cash statements.
        This button should be called only on journals with type =='bank'"""
        action = self.env["ir.actions.actions"]._for_xml_id(
            "l10n_do_bank_statement_import.action_bank_statement_import_line_wizard"
        )
        action["context"] = {"journal_id": self.id}
        return action
