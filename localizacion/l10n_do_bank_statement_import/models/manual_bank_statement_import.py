import base64
from datetime import datetime as dt

from odoo import models, _
from csv import reader
import io


class AccountBankStatementImport(models.TransientModel):
    _inherit = 'account.bank.statement.wizard'

    def _import_manual_statement(self, rec, statement_id):
        """
        Process data from txt and generate bank statement for Banco BHD
        :param rec: account.bank.statement.import record

        """
        file_reader = []
        data = base64.b64decode(rec.data_file)
        data_file = io.StringIO(data.decode("latin1"))
        data_file.seek(0)
        csv_reader = reader(data_file, delimiter=',')
        file_reader.extend(csv_reader)
        
        with open('/tmp/statement.txt', 'w+') as w_file:
            [w_file.write(";".join(row)+'\n') for row in file_reader]
   
        with open('/tmp/statement.txt', 'r+') as r_file:
            first_line = r_file.readlines()[1]
        
        statement_line = []
        with open('/tmp/statement.txt', 'r') as data:
            next(data) # To Skip the Header
            
            for line in data:

                if line.split(";")[0]:
                    date = dt.strptime(line.split(";")[0], "%d/%m/%Y").strftime("%Y-%m-%d")
                    debit  = line.split(";")[3].lstrip('0').replace(',','')
                    credit  = line.split(";")[4].lstrip('0').replace(',','')
                    amount = 0.0
                    if debit != '0' and not credit:
                        amount = float(debit)  * -1

                    if credit != '0' and not debit:
                        amount = float(credit) 
    
                    document = line.split(";")[2]

                    statement_line.append((0, 0, {
                        'date': date,
                        'payment_ref': line.split(";")[1] if line.split(";")[1] else line.split(";")[2],
                        'journal_id': rec.journal_id.id,
                        'narration': line.split(";")[5] if line.split(";")[5] else '',
                        'amount': amount }))

            if statement_line:
                statement_id.line_ids.unlink()
                statement_id.write({'line_ids': statement_line})