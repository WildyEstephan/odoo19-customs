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
        ('coopedac', 'COOPEDAC')
    ])


class AccountBankStatementImport(models.TransientModel):
    _inherit = 'account.bank.statement.wizard'

    def _import_coopedac_statement(self, rec, statement_id):
        """
        Process data from txt and generate bank statement for Banco BHD
        :param rec: account.bank.statement.import record

        """
        def _to_digit(num):
            if num:
                num = num.replace("RD$ ", "")
                return num.replace(",", "")
            else:
                return 0
        
        data = base64.b64decode(rec.data_file)
        with open('/tmp/statement.txt', 'w+') as w_file:
            w_file.write(data.decode('utf-8'))

        statement_line = []

        with open('/tmp/statement.txt', 'r') as data:
            header = False
            for fline in reader(data, delimiter=',', quotechar='"'):
                if not header:
                    header = True
                    continue
                
                amount = float(_to_digit(fline[8])) if float(_to_digit(fline[8])) != 0.0 else float(_to_digit(fline[7]))

                statement_line.append((0, 0, {
                    'date': dt.strptime(fline[1].rstrip(), "%d/%m/%Y").strftime("%Y-%m-%d"),
                    'payment_ref': str(fline[4]).strip(),
                    'journal_id': rec.journal_id.id,
                    'amount': float(amount),
                }))

            if statement_line:
                statement_id.line_ids.unlink()
                statement_id.write({'line_ids': statement_line})
