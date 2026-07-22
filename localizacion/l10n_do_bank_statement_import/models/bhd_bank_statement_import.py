import base64
from datetime import datetime as dt

from odoo import models, fields, _
from csv import reader


class InheritedAccountJournal(models.Model):
    _inherit = "account.journal"
    
    statement_import_type = fields.Selection(selection_add=[('bhd', 'Banco BHD')])


class AccountBankStatementImport(models.TransientModel):
    _inherit = 'account.bank.statement.wizard'

    def _import_bhd_statement(self, rec, statement_id):
        """
        Process data from txt and generate bank statement for Banco BHD
        :param account.bank.statement.wizardt record
        """
        # Convert binary data to latin1
        data = base64.b64decode(rec.data_file)
        with open('/tmp/statement.txt', 'w+') as w_file:
            w_file.write(data.decode('latin1'))

        with open('/tmp/statement.txt', 'r+') as r_file:
            first_line = r_file.readlines()[0]
            account = first_line.split(",")[0].replace('"', '')
            self._get_journal_id(account, rec)

        # Write statement lines
        statement_line = []
        unique_ncfs = {}

        with open('/tmp/statement.txt', 'r') as data:
            header = False
            for fline in reader(data, delimiter=',', quotechar='"'):
                if not header:
                    header = True
                    continue
                
                amount = float(fline[6]) if float(fline[6]) != 0.0 else float(fline[5]) * - 1

                if fline[2]:
                    if fline[2] not in unique_ncfs:
                        unique_ncfs[fline[2]] = {
                            'date': dt.strptime(fline[0].rstrip(), "%d/%m/%Y").strftime("%Y-%m-%d"),
                            'payment_ref': "{} - {}".format(str(fline[2]).strip(), str(fline[4]).strip()),
                            'journal_id': rec.journal_id.id,
                            'amount': float(amount)
                        }
                    else:
                        unique_ncfs[fline[2]]['amount'] += float(amount)

                    continue

                statement_line.append((0, 0, {
                    'date': dt.strptime(fline[0].rstrip(), "%d/%m/%Y").strftime("%Y-%m-%d"),
                    'payment_ref': fline[4],
                    'journal_id': rec.journal_id.id,
                    'amount': float(amount)}))

            if unique_ncfs:
                for ncf in unique_ncfs:
                    
                    statement_line.append([0, 0, unique_ncfs.get(ncf)])

            if statement_line:
                statement_id.line_ids.unlink()
                statement_id.write({'line_ids': statement_line})
