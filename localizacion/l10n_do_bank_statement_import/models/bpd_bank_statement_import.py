from odoo import models, fields, _
import base64
from datetime import datetime as dt
from odoo import models

class InheritedAccountJournal(models.Model):
    _inherit = "account.journal"
    
    statement_import_type = fields.Selection(selection_add=[
        ('popular', 'Banco Popular')
    ])


class AccountBankStatementImport(models.TransientModel):
    _inherit = 'account.bank.statement.wizard'

    def _import_popular_statement(self, rec, statement_id):
        """
        Process data from txt and generate bank statement for Banco Popular
        :param rec: account.bank.statement.wizard record
        """

        # Convert binary data to latin1
        data = base64.b64decode(rec.data_file)
        with open('/tmp/statement.txt', 'w+') as w_file:
            w_file.write(data.decode('latin1'))

        with open('/tmp/statement.txt', 'r+') as r_file:

            account = r_file.readline().split(",")[0].lstrip('0')
            self._get_journal_id(account, rec)

        # Write statement lines

        with open('/tmp/statement.txt', 'r') as data:
            statement_line = []
            for line in data:
                
                amount = line.split(",")[3].lstrip('0')
                amount = amount if line.split(",")[4] == 'CR' else str(float(amount) * -1)
                statement_line.append((0, 0, {
                    'date': dt.strptime(line.split(",")[1], "%d/%m/%Y").strftime("%Y-%m-%d"),
                    'partner_id': self._get_partner_id(line.split(",")[2]),
                    'payment_ref': str(line.split(",")[5]).strip(),
                    'journal_id': rec.journal_id.id,
                    'account_number': line.split(",")[2].lstrip('0') if len(line.split(",")[2].lstrip('0')) == 9 else '',
                    'amount': amount * -1 if rec.journal_id.is_tc else amount
                }))
           
            if statement_line:
                statement_id.line_ids.unlink()
                statement_id.write({'line_ids': statement_line})
