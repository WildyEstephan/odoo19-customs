
import base64
import io
import logging

from odoo.exceptions import UserError

from .interface import GeneratorInterface

_logger = logging.getLogger(__name__)



class PopularGenerator(GeneratorInterface):

    name = 'Banco Popular'
    code = 'BPD'

    def generate_txt(self, obj):

        full = '{:%Y%m%d}'.format(obj.effective_date)
        create_date = '{:%Y%m%d}'.format(obj.create_date)
        hour_date = '{:%Hh%Mm}'.format(obj.create_date)
        rnc = obj.company_id.vat
        seq = obj.sequence
        if not seq:
            seq = obj.env['ir.sequence'].next_by_code('BPD')
            if not seq:
                # Si la secuencia no existe, generar número basado en ID o timestamp
                import time
                seq = str(int(time.time()))[-7:].zfill(7)
            obj.sequence = seq
        file_io = io.BytesIO()

        credit_lines = 0  # cantidad credito / Cuantas Trans. (lineas) se haran.
        amount_credit = 0  # monto credito / El total de Dinero a Trans.

        lines = ''
        position = 1
        for line in obj.line_ids:
            if line.no_file:
                continue

            employee_id = line.employee_id
            name = str(self.remove_accent(employee_id.name)).upper()

            # Tipo de Documento
            # RN - RNC
            # CE - Cedula
            # PS - Pasaporte
            # OT - Otro (NUmero de Suplidor, ETC)
            doc_type = 'CE'

            city_code = employee_id.country_id.code
            if not city_code or city_code == 'DO':
                num_doc = employee_id.identification_id
                if not num_doc:
                    raise UserError("%s no tiene una Cedula establecida" % employee_id.name)

            else:
                num_doc = employee_id.passport_id
                doc_type = 'PS'
                if not num_doc:
                    raise UserError("%s no tiene una Pasaporte establecido" % employee_id.name)

            num_doc = num_doc.replace(' ', '').replace('-', '')
            credit_lines += 1
            amount_credit += line.amount

            bank_account_id = line.bank_account_id
            account_type = 1 if bank_account_id.account_type == 'CC' else 2
            cod_operation = 22 if account_type == '1' else 32

            account = str(bank_account_id.acc_number).replace('-', '')

            amount = str('%.2f' % line.amount).replace('.', '').zfill(13)

            work_email = employee_id.work_email[0:40].ljust(40) if employee_id.work_email else ' '.ljust(40)
            send_email = employee_id.work_email and '1' or ' '

            #if work_email:

            linea = "N{rnc}{seq}{posicion}{cuenta}{tipo_cuenta}{moneda}{cod_banco_destino}{digi}{cod_ope}{monto}{tipoid}{id}{nombre}{num_ref}{concepto}{fecha_vencimiento}{forma_contacto}{email_empl}{fax}00{filler}".format(
                rnc=str(rnc).ljust(15),
                seq=str(seq).zfill(7),
                posicion=str(position).zfill(7),
                cuenta=str(account).ljust(20),
                tipo_cuenta=account_type,
                moneda=214,
                cod_banco_destino='10101070',
                digi='8',
                cod_ope=cod_operation,
                monto=str(amount).ljust(13),
                tipoid=doc_type,
                id=num_doc.ljust(15),
                nombre=name.ljust(35)[:35],
                num_ref=' '.ljust(12),
                concepto=self.description.ljust(40), fecha_vencimiento=' '.ljust(4),
                forma_contacto=send_email,
                email_empl=work_email,
                fax=' '.ljust(12),
                filler=' '.ljust(79)

            )

            lines += linea + '\n'
            position += 1

        amount_credit = str('%.2f' % amount_credit).replace('.', '').zfill(13)
        credit_lines = str(credit_lines).zfill(11)

        # Obtener email con valor por defecto
        payroll_email = obj.journal_id.bank_account_id.electronic_payroll_email or obj.company_id.email or ''

        header = 'H{rnc}{nombre}{seq}{tipo}{fec}{cd}{md}{numtrans}{totalapagar}{num_afil}{create_date}{hour}{email}{resp_banco}{filler}'.format(
            rnc=str(rnc).ljust(15), nombre=obj.company_id.name.ljust(35)[:35],
            seq=str(seq).zfill(7), tipo='01',
            fec=full, cd='00000000000', md='0000000000000',
            numtrans=credit_lines, totalapagar=amount_credit, num_afil='000000000000000',
            create_date=create_date, hour=hour_date,
            email=str(payroll_email).ljust(40), resp_banco=' ',
            filler=''.ljust(136)
        )

        d = '{}\r\n'.format(header)
        file_io.write(str.encode(d))
        file_io.write(str.encode(lines))
        file_value = file_io.getvalue()
        try:
            report = base64.encodebytes(file_value)
        except:
            report = base64.b64encode(file_value)
            
        date = obj.effective_date
        day = date.day
        month = date.month
        # Obtener código del banco con valor por defecto
        bank_code = obj.journal_id.bank_account_id.electronic_payroll_bank_code or '00001'
        name_report = 'PE{num:>05}{ts}{mm:>02}{dd:>02}{seq}E'.format(
            num=bank_code,
            ts='01', mm=month, dd=day, seq=str(obj.sequence).zfill(7)
        )
        obj.name = "PAGO - " + str(obj.payslip_run_id.name)
        binary_ext = 'TXT'
        report_name = "{}.{}".format(name_report, binary_ext)
        file_io.close()
        return report, report_name
