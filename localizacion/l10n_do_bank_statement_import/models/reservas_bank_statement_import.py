import base64
from datetime import datetime as dt

from odoo import models, fields, _
from csv import reader
import io

class InheritedAccountJournal(models.Model):
    _inherit = "account.journal"

    statement_import_type = fields.Selection(selection_add=[
        ('reserva', 'Banreservas')
    ])


class AccountBankStatementImport(models.TransientModel):
    _inherit = 'account.bank.statement.wizard'

    def _import_reserva_statement(self, rec, statement_id):
        """
        Process data from txt and generate bank statement for Banco BHD
        :param rec: account.bank.statement.import record

        """

        file_reader = []
        data = base64.b64decode(rec.data_file)
        data_file = io.StringIO(data.decode("utf-16"))
        data_file.seek(0)
        csv_reader = reader(data_file, delimiter=',')
        file_reader.extend(csv_reader)
        
        with open('/tmp/statement.txt', 'w+') as w_file:
            [w_file.write(";".join(row)+'\n') for row in file_reader]
        
        with open('/tmp/statement.txt', 'r+') as r_file:
            first_line = r_file.readlines()[1]
            account = first_line.split(";")[0]
            self._get_journal_id(account, rec)

        statement_line = []
        with open('/tmp/statement.txt', 'r') as data:
            next(data)  # To Skip the Header

            for line in data:
                
                date = dt.strptime(line.split(
                    ";")[1], "%d/%m/%Y").strftime("%Y-%m-%d")
                          
                debit = float(line.split(";")[4].replace(',', ''))
                credit = float(line.split(";")[5].replace(',', ''))
                amount = 0.0
                
                if debit != 0.0 and not credit:
                    amount = float(debit) * -1

                if credit != 0.0 and not debit:
                    amount = float(credit)
                    
                document = line.split(";")[8]
                
                reference = document if document != '0' else ''

                statement_line.append((0, 0, {
                    'date': date,
                    'payment_ref': str(line.split(";")[2]).strip(),
                    'journal_id': rec.journal_id.id,
                    'amount': amount}))

            if statement_line:
                statement_id.line_ids.unlink()
                statement_id.write({'line_ids': statement_line})
