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
        ('lopezharo', 'Banco Lopez de Haro')
    ])


class AccountBankStatementImport(models.TransientModel):
    _inherit = 'account.bank.statement.wizard'

    def _check_blh_file(self, reader_st):
        
        headers = {
            0: "Fecha de Posteo",
            1: "Fecha Efectiva",
            2: "No. Cheque",
            3: "No. Referencia",
            4: "Descripción",
            5: "Retiros",
            6: "Depósitos",
            7: "Balance",
        }

        try:
            for r, row in enumerate(reader_st[8][:8]):
                if not row == headers[r]:
                    return False
        except:
            return False
        return True
    
    def _import_lopezharo_statement(self, rec, statement_id):
        """
        Process data from txt and generate bank statement for Banco BHD
        :param rec: account.bank.statement.import record

        """
        data_file = base64.b64decode(rec.data_file)

        with open('/tmp/statement.csv', 'w', newline='\n') as w_file:
                w_file.write(data_file.decode('latin1'))

        with open('/tmp/statement.csv', newline='\n') as data:
                reader = csv.reader((x.replace('\0', '').replace('Ã³', 'ó') for x in data), delimiter=',', quotechar='"')
                reader = [l for l in reader]

                if not self._check_blh_file(reader):
                    raise ValidationError(_("Formato Proporcionado Erroneo"))
                
                account_number = reader[3][7] if reader[3][7] else False
                self._get_journal_id(account_number, rec)
                
                statement_line = []
                for i, line in enumerate(reader[9:]):
                    try:
                        statement_line.append((0, 0, {
                            'date': dt.strptime(line[1], "%d/%m/%Y"),
                            'payment_ref': str(line[4]).strip(),
                            'journal_id': rec.journal_id.id,
                            'amount': float(str(line[6]).replace(",", "")) if float(str(line[6]).replace(",", "")) else float(str(line[5]).replace(",", "")) * -1
                        }))
                    except(IndexError, ValueError):
                        continue
                if statement_line:
                    statement_id.line_ids.unlink()
                    statement_id.write({'line_ids': statement_line})
 