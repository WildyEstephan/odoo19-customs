import logging
from odoo import models, fields, api, _
_logger = logging.getLogger(__name__)


class account_bank_statement_wizard(models.TransientModel):
    _name= "account.bank.statement.wizard"
    _description = "Dominican Bank Report"

    data_file = fields.Binary(string="Subir Archivo", attachment=False)
    filename = fields.Char('File Name')

    bank_st = fields.Char(compute='_get_bank_name', string="Bank Name",)

    name = fields.Char(string="Nombre Extracto", required=True)
    journal_id = fields.Many2one(
        string='Diario',
        comodel_name='account.journal',
        ondelete='restrict',
        readonly=True
    )
    
    @api.model
    def default_get(self, fields):

        res = super().default_get(fields)
        active_id = self.env.context.get('journal_id')
        if 'bank_st' in fields:
            bs_id = self.env["account.journal"].browse(active_id)
            res.update({
                'journal_id': bs_id.id,
                'bank_st': bs_id.statement_import_type
            })

        return res
    
    def _get_bank_name(self):
        active_id = self.env.context.get('journal_id')
        bs_id = self.env["account.journal"].browse(active_id)
        self.bank_st = bs_id.statement_import_type
