import base64
import xlrd
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
        ('acap', 'Asociación Cibao de Ahorros y Préstamos')
    ])


class AccountBankStatementImport(models.TransientModel):
    _inherit = 'account.bank.statement.wizard'

    def _check_acap_file(self, reader_st):
        
        column_headers = {
            0: "FECHA TRANSACCION", 1: "FECHA ENTRADA",
            2: "NUMERO REFERENCIA", 3: "DESCRIPCION",
            4: "DESCRIPCION_2", 5: "DESCRIPCION_3",
            6: "ORIGEN", 7: "VALOR",
            8: "SALDO",
        }

        # Here we only read the first row
        for row in reader_st:
            for i, col in enumerate(row):
                if not col == column_headers[i]:
                    return False
            return True
        return True
    
    def _import_acap_statement(self, rec, statement_id):
        """
        Process data from txt and generate bank statement for Banco BHD
        :param rec: account.bank.statement.import record

        """
        data_file = base64.b64decode(rec.data_file)

        with open('/tmp/statement.csv', 'w', newline='') as w_file:
            w_file.write(data_file.decode('latin1'))

        with open('/tmp/statement.csv', newline='') as data:
            reader = csv.reader((x.replace('\0', '') for x in data), delimiter=';', quotechar='"')

            if self._check_acap_file(reader):
                
                balance_start = False
                balance_end_real = False
                statement_line = []
                for line in reader:
                    try:
                        if not balance_start:
                            balance_start = float(line[8])
                        balance_end_real = float(line[8])

                        statement_line.append((0, 0, {
                            'date': dt.strptime(line[0], "%Y%m%d"),
                            'payment_ref': "{} - {}".format(str(line[3]).strip(), str(line[2]).strip()),
                            'journal_id': rec.journal_id.id,
                            'amount': line[7] if line[6] == 'CR' else float(line[7]) * -1,
                        }))
                    except IndexError:
                        continue
                
                if statement_line:
                    statement_id.line_ids.unlink()
                    statement_id.balance_start = balance_start
                    statement_id.balance_end_real = balance_end_real
                    statement_id.write({'line_ids': statement_line})
 