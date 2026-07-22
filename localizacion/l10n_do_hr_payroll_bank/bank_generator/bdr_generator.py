
import base64
import io
import logging

from odoo.exceptions import UserError

from .interface import GeneratorInterface

_logger = logging.getLogger(__name__)

# Códigos de banco según especificación Banco Popular - Pagos Electrónicos 2023
BANK_CODES = {
    'BANRESERVAS_DOP': ('10101010', '6'),
    'BANRESERVAS_USD': ('80101010', '5'),
    'SCOTIABANK_DOP': ('10101030', '0'),
    'SCOTIABANK_USD': ('80101030', '9'),
    'POPULAR_DOP': ('10101070', '8'),
    'POPULAR_USD': ('80101070', '7'),
    'BHD_DOP': ('10101230', '8'),
    'BHD_USD': ('80101230', '7'),
}


class BDRTemplate(GeneratorInterface):
    """
    Generador para Banco de Reservas (BanReservas)
    Formato según especificación de Pagos Electrónicos 2023
    Compatible con formato de Banco Popular ACH
    """

    name = 'Banco de Reservas'
    code = 'BDR'

    def get_bank_code_and_digit(self, bank_name, currency_name='DOP'):
        """
        Obtiene el código de banco y dígito verificador
        según la tabla de códigos de banco del PDF
        """
        key = f"{bank_name}_{currency_name}"
        if key in BANK_CODES:
            return BANK_CODES[key]
        # Si no encuentra, usa BanReservas DOP por defecto
        return BANK_CODES.get('BANRESERVAS_DOP', ('10101010', '6'))

    def generate_txt(self, obj):
        """
        Genera archivo TXT según formato estándar de Pagos Electrónicos

        Estructura:
        - Registro Header (H): Línea 1
        - Registros de Transacciones (N): Una por cada empleado

        Nombre del archivo: PE{company_code}01{MMDD}{sequence}E.TXT
        01 = Nómina Automática (TipoServicio)
        """

        # Obtener secuencia
        seq = obj.sequence
        if not seq:
            seq = obj.env['ir.sequence'].next_by_code('BDR')
            if not seq:
                # Si la secuencia no existe, generar número basado en ID o timestamp
                import time
                seq = str(int(time.time()))[-7:].zfill(7)
            obj.sequence = seq

        # Fechas
        effective_date = '{:%Y%m%d}'.format(obj.effective_date)
        create_date = '{:%Y%m%d}'.format(obj.create_date)
        hour_date = '{:%H%M}'.format(obj.create_date)

        # Datos de la compañía
        rnc = obj.company_id.vat or ''
        company_name = obj.company_id.name or ''

        # Cuenta origen de la compañía
        origin_account_obj = obj.journal_id.bank_account_id
        if not origin_account_obj:
            raise UserError("No se ha configurado una cuenta bancaria en el diario de pago")

        email = origin_account_obj.electronic_payroll_email or obj.company_id.email or ''

        file_io = io.BytesIO()

        # Contadores para el header
        credit_count = 0  # Cantidad de créditos (empleados)
        credit_amount = 0  # Monto total de créditos

        # Generar registros de transacciones (N)
        lines = ''
        position = 1

        for line in obj.line_ids:
            if line.no_file:
                continue

            employee_id = line.employee_id
            name = str(self.remove_accent(employee_id.name)).upper()

            # Tipo de Documento (RN=RNC, CE=Cédula, PS=Pasaporte, OT=Otro)
            doc_type = 'CE'
            city_code = employee_id.country_id.code

            if not city_code or city_code == 'DO':
                num_doc = employee_id.identification_id
                if not num_doc:
                    raise UserError(f"{employee_id.name} no tiene una Cédula establecida")
            else:
                num_doc = employee_id.passport_id
                doc_type = 'PS'
                if not num_doc:
                    raise UserError(f"{employee_id.name} no tiene un Pasaporte establecido")

            num_doc = num_doc.replace(' ', '').replace('-', '')

            # Incrementar contadores
            credit_count += 1
            credit_amount += line.amount

            # Cuenta bancaria del empleado
            bank_account_id = line.bank_account_id
            if not bank_account_id:
                raise UserError(f"{employee_id.name} no tiene cuenta bancaria configurada")

            account = str(bank_account_id.acc_number).replace('-', '').ljust(20)

            # Tipo de cuenta (1=CC, 2=Ahorro)
            account_type = '1' if bank_account_id.account_type == 'CC' else '2'

            # Código de operación (22=Cr.Cta.Corriente, 32=Cr.Cta.Ahorro)
            cod_operation = '22' if account_type == '1' else '32'

            # Monto sin decimales, rellenado con ceros a la izquierda (13 dígitos)
            amount = str('%.2f' % line.amount).replace('.', '').zfill(13)

            # Obtener código de banco destino y dígito verificador
            bank_name = bank_account_id.bank_id.name.upper() if bank_account_id.bank_id else 'BANRESERVAS'
            currency_name = bank_account_id.currency_id.name or 'DOP'

            # Mapeo de nombres de banco a claves
            bank_key_map = {
                'BANRESERVAS': 'BANRESERVAS',
                'BANCO DE RESERVAS': 'BANRESERVAS',
                'SCOTIABANK': 'SCOTIABANK',
                'POPULAR': 'POPULAR',
                'BANCO POPULAR': 'POPULAR',
                'BHD': 'BHD',
                'BANCO BHD': 'BHD',
            }

            bank_key = None
            for key, value in bank_key_map.items():
                if key in bank_name:
                    bank_key = value
                    break

            if not bank_key:
                bank_key = 'BANRESERVAS'

            cod_banco_destino, digi = self.get_bank_code_and_digit(bank_key, currency_name)

            # Moneda (214=DOP, 840=USD)
            moneda = '214' if currency_name == 'DOP' else '840'

            # Email del empleado para notificación
            work_email = employee_id.work_email[0:40].ljust(40) if employee_id.work_email else ' '.ljust(40)
            send_email = '1' if employee_id.work_email else ' '

            # Construir registro de transacción (N)
            linea = "N{rnc}{seq}{posicion}{cuenta}{tipo_cuenta}{moneda}{cod_banco}{digi}{cod_ope}{monto}{tipoid}{id}{nombre}{num_ref}{concepto}{fecha_venc}{forma_contacto}{email}{fax}{id_adq}{num_aut}{cod_ret}{cod_raz_rem}{cod_raz_int}{proc_trans}{status}{filler}".format(
                rnc=str(rnc).ljust(15),
                seq=str(seq).zfill(7),
                posicion=str(position).zfill(7),
                cuenta=account,
                tipo_cuenta=account_type,
                moneda=moneda,
                cod_banco=cod_banco_destino,
                digi=digi,
                cod_ope=cod_operation,
                monto=amount,
                tipoid=doc_type,
                id=num_doc.ljust(15),
                nombre=name.ljust(35)[:35],
                num_ref=' '.ljust(12),
                concepto=self.description.ljust(40)[:40],
                fecha_venc=' '.ljust(4),
                forma_contacto=send_email,
                email=work_email,
                fax=' '.ljust(12),
                id_adq='00',  # Identificador de adquiriente
                num_aut=' '.ljust(15),  # Número de autorización (respuesta del banco)
                cod_ret=' '.ljust(3),  # Código retorno remoto
                cod_raz_rem=' '.ljust(3),  # Código razón remoto
                cod_raz_int=' '.ljust(3),  # Código razón interno
                proc_trans=' ',  # Procesador transacción
                status=' '.ljust(2),  # Estatus transacción
                filler=' '.ljust(52)
            )

            lines += linea + '\n'
            position += 1

        # Formatear montos y cantidades para el header
        amount_credit_formatted = str('%.2f' % credit_amount).replace('.', '').zfill(13)
        credit_count_formatted = str(credit_count).zfill(11)

        # Construir registro Header (H)
        header = 'H{rnc}{nombre}{seq}{tipo}{fec}{cant_db}{monto_db}{cant_cr}{monto_cr}{num_afil}{create_date}{hour}{email}{status}{filler}'.format(
            rnc=str(rnc).ljust(15),
            nombre=company_name.ljust(35)[:35],
            seq=str(seq).zfill(7),
            tipo='01',  # 01 = Nómina Automática
            fec=effective_date,
            cant_db='00000000000',  # Cantidad de débitos (0 para nómina)
            monto_db='0000000000000',  # Monto total débitos (0 para nómina)
            cant_cr=credit_count_formatted,
            monto_cr=amount_credit_formatted,
            num_afil='000000000000000',  # Número afiliación (solo para cobros automáticos)
            create_date=create_date,
            hour=hour_date,
            email=str(email).ljust(40)[:40],
            status=' ',  # Estatus (respuesta del banco)
            filler=' '.ljust(136)
        )

        # Escribir header y líneas
        file_io.write(str.encode(header + '\n'))
        file_io.write(str.encode(lines))

        file_value = file_io.getvalue()

        report = base64.encodebytes(file_value)

        # Generar nombre de archivo según formato:
        # PE{company_code}01{MMDD}{sequence}E.TXT
        date = obj.effective_date
        day = date.day
        month = date.month

        # Código de compañía de 5 dígitos
        company_code = origin_account_obj.electronic_payroll_bank_code or '00001'

        name_report = 'PE{num:>05}01{mm:>02}{dd:>02}{seq:>07}E'.format(
            num=company_code,
            mm=month,
            dd=day,
            seq=seq
        )

        obj.name = "PAGO - " + str(obj.payslip_run_id.name)
        binary_ext = 'TXT'
        report_name = "{}.{}".format(name_report, binary_ext)
        file_io.close()

        return report, report_name
