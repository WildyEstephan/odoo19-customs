import base64
from datetime import datetime as dt

from odoo import models, fields, api, _
from odoo.tools import pycompat
from odoo.exceptions import ValidationError
import csv
from csv import reader
import io

class InheritedAccountJournal(models.Model):
    _inherit = "account.journal"

    statement_import_type = fields.Selection(selection_add=[
        ('santacruz', 'Santa Cruz')
    ])


class AccountBankStatementImport(models.TransientModel):
    _inherit = 'account.bank.statement.wizard'

    def _import_santacruz_statement(self, rec, statement_id):
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
        
        statement_line = []
        with open('/tmp/statement.txt', 'r') as data:
            
            for r in range(8):
                next(data)  # To Skip the Header

            for line in data:
                if len(line.split(";"))== 1:
                    continue
                    
                date = dt.strptime(line.split(
                    ";")[0], "%d/%m/%Y").strftime("%Y-%m-%d")
                          
                debit = 0.0 if line.split(";")[2] =="" else float(line.split(";")[2].replace(',', ''))
                credit = 0.0 if line.split(";")[3] =="" else float(line.split(";")[3].replace(',', ''))
                amount = 0.0
                
                if debit != 0.0 and not credit:
                    amount = float(debit) * -1

                if credit != 0.0 and not debit:
                    amount = float(credit)
                    
                statement_line.append((0, 0, {
                    'date': date,
                    'payment_ref': str(line.split(";")[1]).strip(),
                    'journal_id': rec.journal_id.id,
                    'amount': amount}))

            if statement_line:
                statement_id.line_ids.unlink()
                statement_id.write({'line_ids': statement_line})
