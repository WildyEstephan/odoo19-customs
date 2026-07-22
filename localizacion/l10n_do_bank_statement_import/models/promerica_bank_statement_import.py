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
        ('promerica', 'Banco Promerica')
    ])


class AccountBankStatementImport(models.TransientModel):
    _inherit = 'account.bank.statement.wizard'

    
    def get_reader_bp(self, stmt):
        sheet = stmt.sheet_by_index(0)
        reader = []
        for row_idx in range(0, sheet.nrows):
            row = []
            for col_idx in range(0, sheet.ncols):
                cell_obj = sheet.cell(row_idx, col_idx)
                row.append(cell_obj.value)
            reader.append(row)
        return reader
    
    def _check_bp_file(self, reader_st):
        
        column_headers = {
            0: "Fecha de Posteo",
            1: "Fecha Efectiva",
            2: "No. Secuencia",
            3: "Código de Transacción",
            4: "No. Referencia",
            5: "Descripción",
            6: "Retiros",
            7: "Depósitos",
            8: "Balance",
        }

        try:
            row = self.get_reader_bp(reader_st)[7]
            for c, col in enumerate(row):
                col = col.strip()
                if not col == column_headers[c]:
                    return False
            return True
        except:
            return False
    
    def _import_promerica_statement(self, rec, statement_id):
        """
        Process data from txt and generate bank statement for Banco BHD
        :param rec: account.bank.statement.import record

        """
        data_file = base64.b64decode(rec.data_file)

        with open('/tmp/statement.xlsx', 'wb') as w_file:
            w_file.write(base64.b64decode(self.data_file))

        with xlrd.open_workbook('/tmp/statement.xlsx') as data:
            if self._check_bp_file(data):
                
                reader = self.get_reader_bp(data)
                line = reader[4][0].split('/')
                account_number = line[1]
                self._get_journal_id(account_number, rec)
                balance_start = False
                balance_end_real = False
                statement_line = []
                for line in reader[8:]:
                    try:
                        if not balance_start:
                            balance_start = float(line[8])
                        balance_end_real = float(line[8])
                        statement_line.append((0, 0, {
                            'date': dt.strptime(line[1], "%d/%m/%Y"),
                            'payment_ref': "{} - {}".format(str(line[5]).strip(), str(line[4]).strip()),
                            'journal_id': rec.journal_id.id,
                            'amount': float(line[6]) * -1 if float(line[6]) > 0 else float(line[7])
                        }))
                    except IndexError:
                        continue
                    except Exception:
                        raise ValidationError('Error reading statement values,'
                                        '\nFile does not meet BPM statement file structure')
                if statement_line:
                    statement_id.line_ids.unlink()
                    statement_id.balance_start = balance_start
                    statement_id.balance_end_real = balance_end_real
                    statement_id.write({'line_ids': statement_line})
 