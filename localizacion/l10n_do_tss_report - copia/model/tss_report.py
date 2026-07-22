from logging import warn, warning
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import base64
from datetime import datetime as dt
import calendar

class tss_report(models.Model):
    _name = 'tss.report'
    _description = 'Archivo de Autodeterminacion TSS'
    _inherit = ['mail.thread']
    
    name = fields.Char(string='Periodo', required=True, size=7)
    company_id = fields.Many2one('res.company',
                                 'Company',
                                 default=lambda self: self.env.user.company_id,
                                 required=True)
    
    tipo_de_archivo = fields.Selection([('AM','AM'), ('AR','AR')],
                            size=2, required=True,
                             copy=False)

    state = fields.Selection([('draft', 'Nuevo'),
                            ('generated', 'Generado'), ('sent', 'Enviado')],
                            default='draft',
                            track_visibility='onchange',
                             copy=False)

    def _valid_field_parameter(self, field, name):
        return name in ['size', 'track_visibility'] or super(tss_report, self)._valid_field_parameter(field, name)
    
    report = fields.Binary(u"Reporte", readonly=True)
    report_name = fields.Char(u"Nombre de Reporte", size=40, readonly=True)
    line_count = fields.Integer(u"Total de registros", compute='_compute_tss_resume')
    total_salario_cot = fields.Float(u"Total Salario Cotizable", compute='_compute_tss_resume')
    total_otras_rem = fields.Float(u"Total Otros Remuneraciones", compute='_compute_tss_resume')

    _name_unique = models.Constraint(
        'UNIQUE(name, company_id, tipo_de_archivo)',
        'You cannot have more than one report by period.',
    )

    def _compute_tss_resume(self):
        for rec in self:
            data = {
                "line_count": 0,
                "total_salario_cot" : 0,
                "total_otras_rem": 0,

            }
            tss_line_ids = self.env["tss.report.line"].search([("tss_report_id", "=", rec.id)])
            for line in tss_line_ids:
                data["line_count"] += 1
                data["total_salario_cot"] += line.SALARIO_COT
                data["total_otras_rem"] += line.OTRAS_REM


            rec.line_count = abs(data["line_count"])
            rec.total_salario_cot = abs(data["total_salario_cot"])
            rec.total_otras_rem = abs(data["total_otras_rem"])


    def _validate_date_format(self, date):
        """Validate date format <MM/YYYY>"""
        if date is not None:
            error = _('Error. Date format must be MM/YYYY')
            if len(date) == 7:
                try:
                    dt.strptime(date, '%m/%Y')
                except ValueError:
                    raise ValidationError(error)
            else:
                raise ValidationError(error)

    def _get_formated_date(self, date):

        return dt.strptime(date, '%Y-%m-%d').strftime('%d%m%Y') \
            if isinstance(date, str) else date.strftime('%d%m%Y') \
            if date else ""
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._validate_date_format(vals.get('name'))
        return super(tss_report, self).create(vals_list)
    
    def write(self, vals):

        self._validate_date_format(vals.get('name'))

        return super(tss_report, self).write(vals)
    
    def state_sent(self):
        for report in self:
            report.state = 'sent'

    def generate_report(self):
        if self.state == 'generated':
            action = self.env.ref(
                'l10n_do_tss_report.tss_report_regenerate_wizard_action').read()[0]
            action['context'] = {'default_report_id': self.id}
            return action
        else:
            self._generate_report()

    def _generate_report(self):
        for rec in self:

            hr_payslip_obj = self.env['hr.payslip']
            hr_payslip_run_obj = self.env['hr.payslip.run']
            hr_payslip_line_obj = self.env['hr.payslip.line']
            tss_report_line_obj = self.env['tss.report.line']
            tss_report_line_obj.search([('tss_report_id', '=', rec.id)]).unlink()

            month, year = self.name.split('/')
            last_day = calendar.monthrange(int(year), int(month))[1]
            date_from = '{}-{}-01'.format(year, month)
            date_to = '{}-{}-{}'.format(year, month, last_day)

            domain_filters = []

            if rec.name:
                domain_filters.append(("date_start", ">=", date_from))
                domain_filters.append(("date_end", "<=", date_to))

            # MODIFICADO: Arturo Diaz Lora - 2026-03-14 10:00
            # Razón: Filtrar por company_id para soporte multi-company
            domain_filters.append(("company_id", "=", rec.company_id.id))

            payslip_run_ids = hr_payslip_run_obj.search(domain_filters)

            if not payslip_run_ids:
                    raise ValidationError(_('No existen nominas registradas!\n'
                                            "Por favor seleccione otro periodo."))

            payslip_ids = hr_payslip_obj.search([('payslip_run_id', 'in', payslip_run_ids.ids)])

            output = set()
            for line in payslip_ids:
                output.add(line.employee_id)
            
            for employee_id in output:

                nombres = (employee_id.tss_names) or ''
           
                primer_apellido = (employee_id.tss_first_lastname) or ''
                if not employee_id.tss_second_lastname:
                    segundo_apellido = ''
                else:
                    segundo_apellido = (employee_id.tss_second_lastname) or ''
                aporte_voluntario = 0.00
                rnc_ced_agent_ret = ''
                rem_ot_agent = 0.00
                saldo_favor_periodo = 0.00
                salario_infotep = 0.00
                # En Odoo 19, accedemos a través de version_id (antes contract_id)
                tipo_ingreso = str(employee_id.income_type or '0001')
                salario_regalia = 0.00
                cesantia_preaviso_indem = 0.00
                retencion_pension_alimenticia = 0.00
                basic = 0.00
                allowance = 0.00
                salario_cotizable = 0.00
                salario_isr = 0.00

                if not employee_id.birthday:
                    fecha_nacimiento = ''
                else:
                    fecha_nacimiento = self._get_formated_date(employee_id.birthday)

                if not employee_id.gender:
                    raise ValidationError(_(u'Genero no definido! \n' 
                                            u'El siguiente empleado %s no tiene genero '
                                            u'definido (Masculino / Femenino ), favor '
                                            u'corrregir antes de continuar.  '
                                        ) % employee_id.name)
                elif employee_id.gender == 'male':
                    sexo = 'M'
                elif employee_id.gender == 'female':
                    sexo = 'F'
                else:
                    sexo = ''

                if not employee_id.identification_id and not employee_id.passport_id and not employee_id.nss_id:
                    raise ValidationError(_(u'Cédula / Pasaporte / NSS !No encontrado!\n'
                                        u"El siguiente empleado %s no posee un No. de Cedula, Pasaporte o NSS "
                                        u"registrado, favor corregir antes de continuar"
                                        % employee_id.name))
                # elif not employee_id.identification_id and employee_id.passport_id:
                #     numero_doc = employee_id.passport_id
                #     tipo_doc = 'P'
                elif employee_id.identification_id==employee_id.passport_id and employee_id.country_id.code !='DO':
                    numero_doc = employee_id.passport_id
                    tipo_doc = 'P'
                elif employee_id.identification_id:
                    if (employee_id.identification_id and not
                            len("".join(employee_id.identification_id).strip()) in [11, 13]):
                        raise ValidationError(_(u'Cédula Incorrecta' u"Verifique el No. de Identificacion "
                                                                        u"de este empleado: %s" % employee_id.name))
                    numero_doc = "".join(employee_id.identification_id).strip()
                    tipo_doc = 'C'
                else:
                    numero_doc = ''
                    tipo_doc = 'N'

                #Salario ISR y Salario INFOTEP
                slip_basic_ids = hr_payslip_line_obj.search([("slip_id", "in", payslip_ids.ids),
                    ('employee_id', '=', employee_id.id), ("category_id.code","=","SALARIO"), ("amount",">",0)])
                for slip_basic_line in slip_basic_ids:
                    basic += slip_basic_line.amount
                    salario_infotep += slip_basic_line.amount

                slip_allowance_ids = hr_payslip_line_obj.search([("slip_id", "in",payslip_ids.ids),
                    ('employee_id', '=', employee_id.id), ("category_id.code","=","OREM"), ("amount",">",0)])
                for slip_allowance_line in slip_allowance_ids:
                    allowance += slip_allowance_line.amount
                
                #Prestaciones
                prestaciones = ['PREA','CESAN']
                slip_prestaciones_ids = hr_payslip_line_obj.search([("slip_id", "in",payslip_ids.ids),
                    ('employee_id', '=', employee_id.id), ("code","in",prestaciones), ("amount",">",0)])
                for slip_prestaciones_line in slip_prestaciones_ids:
                        cesantia_preaviso_indem += slip_prestaciones_line.amount

                # Arturo Diaz Lora - 2025-12-22
                # Actualizado: Busca REGP (nuevo código) y REPA (legacy) para compatibilidad
                # Migrado desde V17 donde se cambió REPA -> REGP
                slip_regalia_ids = hr_payslip_line_obj.search([("slip_id", "in",payslip_ids.ids),
                    ('employee_id', '=', employee_id.id), ("code","in",["REGP", "REPA"]), ("amount",">",0)])
                for slip_regalia_line in slip_regalia_ids:
                        salario_regalia += slip_regalia_line.amount



                salario_cotizable = basic
                salario_isr = basic
                otras_remuneraciones = allowance

                tipo_registro = 'D'

                values = {
                    u'TIPO_REGISTRO': tipo_registro,
                    u'CLAVE_NOMINA': str(employee_id.payrolltype_id.sequence if employee_id.payrolltype_id else '001'),
                    u'NUMERO_DOC': numero_doc.replace("-", ""),
                    u'NOMBRES': nombres.upper(),
                    u'PRIMER_APELLIDO': primer_apellido.upper(),
                    u'SEGUNDO_APELLIDO': segundo_apellido.upper(),
                    u'SEXO': sexo,
                    u'TIPO_DOCUMENTO': tipo_doc,
                    u'FECHA_NAC': fecha_nacimiento,
                    u'SALARIO_COT': abs(salario_cotizable),
                    u'APORTE_VOL': abs(aporte_voluntario),
                    u'SALARIO_ISR': abs(salario_isr),
                    u'OTRAS_REM': abs(otras_remuneraciones),
                    u'RNC_CED_AGENT_RET': rnc_ced_agent_ret,
                    u'REM_OT_AGENT': abs(rem_ot_agent),
                    u'SALDO_FAVOR_PERIODO': abs(saldo_favor_periodo),
                    u'REGALIA_PASCUAL': abs(salario_regalia),
                    u'PREAVISO_CESANTIA_INDEM': abs(cesantia_preaviso_indem),
                    U'RETENCION_PENSION_ALIMENTICIA':abs(retencion_pension_alimenticia),
                    u'SALARIO_INFOTEP': abs(salario_infotep),
                    u'TIPO_INGRESO': tipo_ingreso,
                    u'tss_report_id': rec.id,
                }

                tss_report_line_obj.create(values)

            self.action_generate_txt(rec.id)
            self.state = 'generated'

    def get_detail_tree_view(self):
        return {
            'name': 'Detalle',
            'view_mode': 'list',
            'res_model': 'tss.report.line',
            'type': 'ir.actions.act_window',
            'view_id':
                self.env.ref('l10n_do_tss_report.tss_report_line_tree').id,
            'domain': [('tss_report_id', '=', self.id)]
        }

    def _format_other_ing(self, valor, pos):

        if valor > 0:
            return str(pos+str('%.2f' % valor).zfill(16))
        else:
            return ""
    def action_generate_txt(self,ids):
        path = '/tmp/autodeterminacion_tss.txt'
        f = open(path,'w', encoding="utf-8")

        #Report header
        
        header_obj = self.env["tss.report"]
        header = header_obj.browse(ids)

        if not header.company_id.vat:

            raise ValidationError(_('u"Debe configurar el RNC de la empresa!"!\n'))

        tipo_registro = str('E')
        document_header = str(header.company_id.vat.replace('-', '').rjust(11))
        proceso = str(header.tipo_de_archivo)

        month, year = header.name.split('/')
        period_month = month
        period_year = year
        period = str(period_month + period_year)
        header_str = tipo_registro + proceso + document_header + period

        f.write(header_str + '\n')

        # Report Detail Lines
        tss_line_ids = self.env["tss.report.line"].search([("tss_report_id", "=", header.id)])
        for line in tss_line_ids:
            tipo_registro = str(line.TIPO_REGISTRO)
            clave_nomina = str(line.CLAVE_NOMINA).zfill(3)
            numero_doc = str(line.NUMERO_DOC).ljust(25, ' ')
            nombres = str((line.NOMBRES)).ljust(50, ' ')
            primer_apellido = str((line.PRIMER_APELLIDO)).ljust(40, ' ')
            segundo_apellido = str((line.SEGUNDO_APELLIDO)).ljust(40, ' ')
            sexo = str(line.SEXO).ljust(1,' ')
            tipo_documento = str(line.TIPO_DOCUMENTO).ljust(1,' ')
            fecha_nac = str(line.FECHA_NAC).ljust(8,' ')
            salario_cot = str('%.2f' % line.SALARIO_COT).zfill(16)
            aporte_vol = str('%.2f' % line.APORTE_VOL).zfill(16)
            salario_isr = str('%.2f' % line.SALARIO_ISR).zfill(16)
            otras_rem = str('%.2f' % line.OTRAS_REM).zfill(16)
            rnc_ced_agent_ret = str(line.RNC_CED_AGENT_RET).rjust(11)
            rem_ot_agent = str('%.2f' % line.REM_OT_AGENT).zfill(16)
            extra = '0000000000000.00'
            saldo_favor_periodo = str('%.2f' % line.SALDO_FAVOR_PERIODO).zfill(16)
            salario_regalia = self._format_other_ing(line.REGALIA_PASCUAL, '01')
            cesantia_preaviso_indem = self._format_other_ing(line.PREAVISO_CESANTIA_INDEM,'02')
            retencion_pension_alimenticia = self._format_other_ing(line.RETENCION_PENSION_ALIMENTICIA, '03')
            salario_infotep = str('%.2f' % line.SALARIO_INFOTEP).zfill(16)
            tipo_ingreso = str(line.TIPO_INGRESO)

            line_str = tipo_registro + clave_nomina + tipo_documento + numero_doc + nombres + primer_apellido + segundo_apellido\
                       + sexo  + fecha_nac + salario_cot + aporte_vol + salario_isr + otras_rem\
                       + rnc_ced_agent_ret + rem_ot_agent +extra + saldo_favor_periodo + salario_infotep + tipo_ingreso\
                       + salario_regalia + cesantia_preaviso_indem + retencion_pension_alimenticia

            f.write(line_str + '\n')

        #Report foother
        tipo_registro = str('S')
        numero_registro = str(header.line_count + 2).zfill(6)
        footer_str = tipo_registro + numero_registro
        f.write(footer_str)

        f.close()

        f = open(path,'rb')
        report = base64.b64encode(f.read())
        f.close()
        report_name = str(header.tipo_de_archivo) + '_' + document_header.replace(' ', '') +'_'+ period  +'.txt'
        self.write({'report': report, 'report_name': report_name})
        return True


class tss_report_line(models.Model):
    _name = 'tss.report.line'
    _description = 'Linea de Tss'
    _order = "NOMBRES asc"

    TIPO_REGISTRO = fields.Char(u'Tipo de Registro', size=1, required = True)
    CLAVE_NOMINA = fields.Char(u'Clave Nomina', required=True)
    TIPO_DOCUMENTO = fields.Selection([('C', u'C'), ('N', u'N'), ('P', u'P')], size=1, string=u'Tipo Doc.', required=True)
    NUMERO_DOC = fields.Char(u"Numero Documento", required=True)
    NOMBRES = fields.Char(u'Nombres', required=True)
    PRIMER_APELLIDO = fields.Char(u'1er. Apellido', required=True)
    SEGUNDO_APELLIDO = fields.Char(u'2do. Apellido', required=False)
    SEXO = fields.Selection([('M', u'M'), ('F', u'F'), (' ', u' ')], size=1, string=u'Sexo', required=False)
    FECHA_NAC = fields.Char(u"Fecha Nacimiento", size=8, required=False)
    SALARIO_COT = fields.Float(u'Salario Cotizable', required=True)
    APORTE_VOL = fields.Float(u'Aporte Voluntario', required=False)
    SALARIO_ISR = fields.Float(u'Salario ISR', required=False)
    TIPO_INGRESO = fields.Selection([('0001', u'Normal'),
                                            ('0002', u'Trabajador ocasional (no fijo)'),
                                            ('0003', u'Asalariado por hora o labora tiempo parcial'),
                                            ('0004',u'No laboró mes completo por razones varias'),
                                            ('0005',u'Salario prorrateado semanal/bisemanal'),
                                            ('0006',u'Pensionado antes de la Ley 87-01'),
                                            ('0007',u'Exento por Ley de pago al SDSS'),
                                            ('0008',u'Trabajador con salario sectorizado')], size=4, string=u'Tipo Ingreso', required=False)

    def _valid_field_parameter(self, field, name):
        return name == 'size' or super(tss_report_line, self)._valid_field_parameter(field, name)

    OTRAS_REM = fields.Float(u'Otras Remuneraciones', required=False)
    RNC_CED_AGENT_RET = fields.Char(u"RNC/Ced. Agent. Ret", size=11, required=False)
    REM_OT_AGENT = fields.Float(u'Remuneracion Otros Agentes', required=False)
    SALDO_FAVOR_PERIODO = fields.Float(u'Saldo a Favor del Periodo', required=False)
    REGALIA_PASCUAL = fields.Float(u'Regalia Pascual (Salario 13)', required=False)
    PREAVISO_CESANTIA_INDEM = fields.Float(u'Preaviso, Cesantia, Viatico e Indemminzaciones por Accidentes Laborales', required=False)
    RETENCION_PENSION_ALIMENTICIA = fields.Float(u'Retencion Pension Alimentica', required=False)
    SALARIO_INFOTEP = fields.Float(u'Salario Infotep', required=False)
    tss_report_id = fields.Many2one('tss.report', ondelete='cascade')
    # MODIFICADO: Arturo Diaz Lora - 2026-03-14 10:00
    # Razón: Agregar company_id related para soporte multi-company
    company_id = fields.Many2one('res.company', related='tss_report_id.company_id', store=True, index=True)
