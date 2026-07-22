
import base64
import io
import logging

from .interface import GeneratorInterface

_logger = logging.getLogger(__name__)


class BHDTemplate(GeneratorInterface):

    name = 'Banco BHD'
    code = 'BHD'

    def generate_txt(self, obj):
        file_io = io.BytesIO()

        lines = ''
        for line in obj.line_ids:
            if line.no_file:
                continue

            name = self.remove_accent(line.employee_id.name)
            identificacion = line.employee_id.identification_id.strip().replace('-', '') or '',
            account = line.bank_account_id.acc_number.replace('-', '')
            amount = str('%.2f' % line.amount)

            lines += "%s;%s;%s;%s;%s;\n" % (account, name, identificacion, amount, obj.description)

        file_io.write(str.encode(lines))

        report_value = file_io.getvalue()

        report = base64.encodebytes(report_value)

        # Generar nombre del archivo
        date = obj.effective_date
        day = date.day
        month = date.month
        year = date.year

        # Establecer el campo name del objeto
        obj.name = "PAGO - " + str(obj.payslip_run_id.name)

        # Nombre del archivo: BHD_NOMINA_YYYYMMDD.TXT
        name_report = 'BHD_NOMINA_{year:04d}{month:02d}{day:02d}'.format(
            year=year,
            month=month,
            day=day
        )

        binary_ext = 'TXT'
        report_name = "{}.{}".format(name_report, binary_ext)
        file_io.close()

        return report, report_name

