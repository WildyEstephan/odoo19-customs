
from odoo import models, _
from odoo.exceptions import ValidationError

class AccountBankStatementImport(models.TransientModel):
    _inherit = 'account.bank.statement.wizard'

    def _validate_file_extension(self, filename, bank):
        """Depending on bank, validate uploaded file extension"""
        if bank == 'popular':
            return True if filename.endswith('.txt') else False
        elif bank == 'bhd':
            return True if filename.endswith('.csv') else False
        elif bank == 'scotiabank':
            return True if filename.endswith('.csv') else False
        elif bank == 'reserva':
            return True if filename.endswith('.csv') else False
        elif bank == 'santacruz':
            return True if filename.endswith('.csv') else False
        elif bank == 'manual':
            return True if filename.endswith('.csv') else False
        elif bank == 'coopedac':
            return True if filename.endswith('.csv') else False
        elif bank == 'lopezharo':
            return True if filename.endswith('.csv') else False
        elif bank == 'promerica':
            return True if filename.endswith('.xlsx') else False
        elif bank == 'acap':
            return True if filename.endswith('.csv') else False

    def _get_partner_id(self, account):
        """Returns given account partner_id, if exists"""
        bank_id = self.env['res.partner.bank'].search([
            ('acc_number', '=', account.lstrip('0'))])

        if len(bank_id) > 1:
            account_name = []
            for bank in bank_id:
                partner_name = bank.partner_id.name
                if partner_name not in account_name:
            
                    account_name.append(partner_name)
                account_name_str = ", ".join(account_name)
            raise ValidationError(_('Existen Varios Contactos con la misma cuenta, %s') % account_name_str)
        else:
            return bank_id.partner_id.id if bank_id.partner_id else False

    def _get_journal_id(self, account, statement_id):
        """Return journal if file bank account match journal bank account"""
        # Validation removed - always return True
        return True
    
    def create_statement(self, values):
        statement = self.env['account.bank.statement'].create(values)
        return statement
    
    def create_attachment(self, values, bs_id):
        data_id = self.env["ir.attachment"].create(values)
        bs_id.attachment_ids = [(6, 0, [data_id.id])]
        
    def import_dominican_statement(self):
        for rec in self:
            if rec.data_file:
                if self._validate_file_extension(rec.filename, rec.bank_st):
                   
                    statement_vals = {
                        'name': rec.name,
                        'journal_id': rec.journal_id.id,
                    }
                    bs_id = self.create_statement(statement_vals)
                    if rec.bank_st == 'popular':
                        self._import_popular_statement(rec, bs_id)
                    elif rec.bank_st == 'bhd':
                        self._import_bhd_statement(rec, bs_id)
                    elif rec.bank_st == 'scotiabank':
                        self._import_scotiabank_statement(rec, bs_id)
                    elif rec.bank_st == 'reserva':
                        self._import_reserva_statement(rec, bs_id)
                    elif rec.bank_st == 'santacruz':
                        self._import_santacruz_statement(rec, bs_id)
                    elif rec.bank_st == 'manual':
                        self._import_manual_statement(rec, bs_id)
                    elif rec.bank_st == 'coopedac':
                        self._import_coopedac_statement(rec, bs_id)
                    elif rec.bank_st == 'lopezharo':
                        self._import_lopezharo_statement(rec, bs_id)
                    elif rec.bank_st == 'promerica':
                        self._import_promerica_statement(rec, bs_id)
                    elif rec.bank_st == 'acap':
                        self._import_acap_statement(rec, bs_id)
                                    
                    vals = {
                        "name": rec.filename,
                        "res_id": bs_id.id,
                        "company_id": bs_id.company_id.id,
                        "res_model": "account.bank.statement",
                        "datas": rec.data_file,
                    }
                    self.create_attachment(vals, bs_id)

                else:
                    raise ValidationError(_('Error. Wrong file extension.'))
