import re
import base64
from datetime import datetime as dt

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class InheritedAccountJournal(models.Model):
    _inherit = "account.journal"
    
    statement_import_type = fields.Selection(selection_add=[
        ('scotiabank', 'Scotiabank')
    ])


class AccountBankStatementImport(models.TransientModel):
    _inherit = 'account.bank.statement.wizard'

    def _import_scotiabank_statement(self, rec, statement_id):
        """
        Process data from txt and generate bank statement for Banco BHD
        :param rec: account.bank.statement.wizard record
        """
        # Convert binary data to latin1
        values = self._prepare_dict(rec.data_file)
        data = base64.b64decode(rec.data_file)
        with open('/tmp/statement.txt', 'w+') as w_file:
             w_file.write(data.decode('latin1'))
        with open('/tmp/statement.txt', 'r+') as r_file:
            account = values['acc_number']
            self._get_journal_id(account, rec)

            time_now = dt.now().strftime("%Y-%m-%d")

            for item in values['data']:
                # This is to prevent error data from extra empty column
                if len(item.keys()) != 4:
                    continue

                file_date = item.get('Fecha').rstrip()
                date = dt.strptime(file_date, "%d/%m/%Y").strftime("%Y-%m-%d")
                document = item.get('Documento')
                reference = document if document != '0' else False

                vals = {
                    'date': date,
                    'payment_ref': item.get('Descripcion'),
                    'journal_id': rec.journal_id.id,
                    'ref': reference,
                    'amount': float(item.get('Monto').replace(',', ''))
                }
                statement_id.line_ids = [[0, 0, vals]]

    def _prepare_dict(self, data_file):
        decoded_data = base64.b64decode(data_file)
        data = str(decoded_data, 'utf-8')
        header = False
        values_dict = {'data': []}
        for record in (z.split(';') for z in data.split('\n')):
            if record[0] and not record[1]:
                acc_number = record[0].split(' ')
                values_dict['acc_number'] = acc_number[2]
                continue
            elif not header:
                header = record
                header[-1] = record[-1].replace("\r","")
                continue
            else:
                record[-1] = record[-1].replace("\r", "")
                values_dict['data'].append(dict(zip(header, record)))
        return values_dict