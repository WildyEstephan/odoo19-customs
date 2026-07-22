# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri
import base64
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_do_track_id = fields.Char(string='Track')
    l10n_do_ecf_security_code = fields.Char(string="Código de Seguridad e-CF", copy=False, readonly=True)
    l10n_do_ecf_sign_date = fields.Datetime(string="Fecha de Firma e-CF", copy=False, readonly=False)
    l10n_do_electronic_stamp = fields.Text(string="Sello Electrónico", copy=False, readonly=False)
    qr_code = fields.Binary(string="Código QR", readonly=False, copy=False, attachment=False)
    qr_code_url = fields.Char(string="QR Code URL", compute='_compute_qr_code_url', readonly=True)
    qr_code_data_uri = fields.Text(string="QR Code Data URI", compute='_compute_qr_code_url', readonly=True)
    l10n_do_status_commercial_approval = fields.Selection(
        selection=[
            ('1', 'e-CF Aceptado'),
            ('2', 'e-CF Rechazado'),
        ],
        string=u'Estado de aprobación comercial',
        default='1',
    )
    l10n_do_detail_commercial_approval = fields.Char(string='Detalle del motivo del rechazo')
    l10n_do_date_commercial_approval = fields.Datetime(string='Fecha de aprobación comercial')
    l10n_do_result_commercial_approval = fields.Char(string='Resultado de aprobación comercial')
    l10n_do_dgii_commercial_approval = fields.Boolean(string='Aprobación comercial DGII', default=False, copy=False)
    l10n_do_custom_fields_ids = fields.One2many(
        comodel_name='l10n_do.custom.fields',
        inverse_name='move_id',
        string=u'Campos especiales (deshabilitados)',
        copy=True,
    )
    country_code = fields.Char(
        string='Código de país',
        related='company_id.country_id.code',
        readonly=True,
        store=True
    )
    
    # Campos computados para condiciones de botones
    l10n_do_ecf_send_mode_computed = fields.Char(
        string='Modo de envío EDI',
        compute='_compute_l10n_do_ecf_fields',
        store=True
    )
    
    l10n_do_ecf_activated_computed = fields.Boolean(
        string='EDI activado',
        compute='_compute_l10n_do_ecf_fields',
        store=True
    )
    
    @api.depends('company_id', 'company_id.l10n_do_ecf_send_mode', 'company_id.l10n_do_ecf_activated')
    def _compute_l10n_do_ecf_fields(self):
        """Computar campos de configuración EDI para uso en vistas"""
        for move in self:
            move.l10n_do_ecf_send_mode_computed = move.company_id.l10n_do_ecf_send_mode or 'manual'
            move.l10n_do_ecf_activated_computed = move.company_id.l10n_do_ecf_activated or False

    @api.depends('qr_code')
    def _compute_qr_code_url(self):
        """Genera URL y data URI para el QR code"""
        for move in self:
            if move.qr_code and move.id:
                # Generar URL al controlador (para web view)
                base_url = move.env['ir.config_parameter'].sudo().get_param('web.base.url')
                move.qr_code_url = f'{base_url}/l10n_do/qr/{move.id}'

                # Generar data URI (para PDF con wkhtmltopdf)
                try:
                    move.qr_code_data_uri = image_data_uri(move.qr_code)
                except Exception as e:
                    _logger.error(f"Error generando data URI para QR de factura {move.name}: {str(e)}")
                    move.qr_code_data_uri = False
            else:
                move.qr_code_url = False
                move.qr_code_data_uri = False

    def debug_dgii_button_conditions(self):
        """Método para debuggear las condiciones del botón DGII"""
        self.ensure_one()
        
        conditions = {
            'state': self.state,
            'state_is_posted': self.state in ('posted',),
            'move_type': self.move_type,
            'move_type_valid': self.move_type in ('out_invoice', 'out_refund', 'in_invoice', 'in_refund'),
            'country_code': self.country_code,
            'country_is_do': self.country_code == 'DO',
            'company_send_mode': self.l10n_do_ecf_send_mode_computed,
            'send_mode_is_manual': self.l10n_do_ecf_send_mode_computed == 'manual',
            'ecf_activated': self.l10n_do_ecf_activated_computed,
            'company_id': self.company_id.id,
            'company_name': self.company_id.name,
            'company_country': self.company_id.country_id.name if self.company_id.country_id else 'No definido',
            'company_country_code': self.company_id.country_id.code if self.company_id.country_id else 'No definido',
        }
        
        _logger.info("=== DEBUG CONDICIONES BOTÓN DGII ===")
        _logger.info(f"Factura ID: {self.id} - {self.name}")
        for key, value in conditions.items():
            _logger.info(f"{key}: {value}")
        
        # Verificar condición completa
        button_visible = (
            self.state in ('posted',) and 
            self.move_type in ('out_invoice', 'out_refund', 'in_invoice', 'in_refund') and 
            self.country_code == 'DO' and 
            self.l10n_do_ecf_send_mode_computed == 'manual' and 
            self.l10n_do_ecf_activated_computed
        )
        
        _logger.info(f"RESULTADO: Botón visible = {button_visible}")
        
        # Verificar formato EDI
        edi_format = self.env['account.edi.format'].search([
            ('code', '=', 'dgii_ecf')
        ], limit=1)
        _logger.info(f"Formato EDI 'dgii_ecf' encontrado: {edi_format.id if edi_format else 'No encontrado'}")
        
        _logger.info("====================================")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Debug DGII completado',
                'message': f'Botón visible: {button_visible}. Revisa los logs para más detalles.',
                'type': 'success' if button_visible else 'warning',
            }
        }

    def action_send_to_approval(self):
        """Abre el wizard de aprobación comercial"""
        self.ensure_one()
        return {
            'name': 'Aprobación Comercial',
            'type': 'ir.actions.act_window',
            'res_model': 'l10n.do.commercial.approval.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_id': self.id,
                'default_status': self.l10n_do_status_commercial_approval,
                'default_detail': self.l10n_do_detail_commercial_approval,
            }
        }

    def action_regenerate_qr(self):
        """Regenera el código QR con el formato correcto de la DGII"""
        self.ensure_one()
        _logger.info(f"🔄 Regenerando QR para factura {self.name}")

        try:
            # Validar que la factura tenga los datos necesarios
            if not self.l10n_latam_document_number:
                raise UserError('La factura no tiene NCF asignado')

            if not self.l10n_do_ecf_security_code:
                raise UserError('La factura no tiene código de seguridad')

            # Buscar el formato EDI de DGII
            edi_format = self.env['account.edi.format'].search([
                ('code', '=', 'dgii_ecf')
            ], limit=1)

            if not edi_format:
                raise UserError('No se encontró el formato EDI DGII')

            # Generar el código QR usando el método del formato EDI
            qr_data = edi_format._generate_qr_code(self)

            if not qr_data:
                raise UserError('No se pudo generar el código QR')

            # USAR SQL DIRECTO porque el ORM ignora write() en campos Binary
            # incluso con sudo() y readonly=False
            self.env.cr.execute("""
                UPDATE account_move
                SET qr_code = %s,
                    l10n_do_electronic_stamp = %s,
                    write_date = NOW(),
                    write_uid = %s
                WHERE id = %s
            """, (
                qr_data['qr_image'],
                qr_data['qr_url'],
                self.env.uid,
                self.id
            ))

            # CRÍTICO: Invalidar cache del ORM para que vea el nuevo valor
            self.invalidate_recordset(['qr_code', 'qr_code_data_uri', 'l10n_do_electronic_stamp'])
            # Forzar recálculo del campo computado qr_code_data_uri para el template PDF
            self._compute_qr_code_url()

            # CRÍTICO: Regenerar el PDF con el QR incluido
            if self.invoice_pdf_report_id:
                try:
                    _logger.info(f"🔄 Regenerando PDF con QR para {self.name}")
                    report = self.env['ir.actions.report'].search([
                        ('report_name', '=', 'l10n_do_accounting.l10n_do_report_invoice_with_payments')
                    ], limit=1)
                    if report:
                        pdf_content, _ = report._render_qweb_pdf(report.id, [self.id])
                        self.invoice_pdf_report_id.write({
                            'datas': base64.b64encode(pdf_content),
                        })
                        _logger.info(f"✅ PDF regenerado con QR para {self.name} ({len(pdf_content)} bytes)")
                    else:
                        _logger.warning(f"⚠️ Reporte dominicano no encontrado, eliminando PDF viejo")
                        self.invoice_pdf_report_id.unlink()
                        self.invalidate_recordset(['invoice_pdf_report_id', 'invoice_pdf_report_file'])
                except Exception as e:
                    _logger.error(f"❌ Error regenerando PDF para {self.name}: {e}")

            _logger.info(f"✅ QR regenerado exitosamente (SQL) para factura {self.name}")
            _logger.info(f"📊 URL QR: {qr_data['qr_url']}")

            # Agregar mensaje en el chatter
            self.message_post(
                body=f"🔄 Código QR regenerado exitosamente<br/>URL: {qr_data['qr_url']}"
            )

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '✅ QR Regenerado',
                    'message': f'El código QR ha sido regenerado exitosamente para {self.name}.',
                    'type': 'success',
                }
            }

        except UserError as e:
            _logger.error(f"❌ Error de usuario regenerando QR: {str(e)}")
            raise
        except Exception as e:
            _logger.error(f"❌ Error regenerando QR para factura {self.name}: {str(e)}")
            raise UserError(f'Error al regenerar QR: {str(e)}')

    def action_send_dgii(self):
        """Envía la factura a la DGII inmediatamente y muestra el resultado"""
        self.ensure_one()
        
        _logger.info("=== DEBUG ENVÍO MANUAL A DGII ===")
        _logger.info(f"Factura ID: {self.id} - {self.name}")
        _logger.info(f"Estado: {self.state}")
        
        if self.state != 'posted':
            _logger.error("Factura no está en estado 'posted'")
            raise UserError('Solo se pueden enviar facturas confirmadas a la DGII')
        
        # Buscar el formato EDI de República Dominicana
        edi_format = self.env['account.edi.format'].search([
            ('code', '=', 'dgii_ecf')
        ], limit=1)
        
        _logger.info(f"Formato EDI encontrado: {edi_format.id if edi_format else 'None'}")
        
        if not edi_format:
            _logger.error("No se encontró el formato EDI dgii_ecf")
            raise UserError('No se encontró el formato EDI para República Dominicana')
        
        try:
            # FORZAR REGENERACIÓN COMPLETA: Eliminar documento EDI existente
            edi_document = self.edi_document_ids.filtered(lambda d: d.edi_format_id == edi_format)
            if edi_document:
                _logger.info(f"🗑️ ELIMINANDO documento EDI existente: ID {edi_document.id}, Estado: {edi_document.state}, Blocking: {edi_document.blocking_level}")
                edi_document.unlink()
                _logger.info("✅ Documento EDI eliminado exitosamente")
            
            # Crear nuevo documento EDI limpio
            _logger.info("📝 Creando nuevo documento EDI limpio...")
            edi_document = self.env['account.edi.document'].create({
                'move_id': self.id,
                'edi_format_id': edi_format.id,
                'state': 'to_send'
            })
            _logger.info(f"✅ Documento EDI creado: ID {edi_document.id}")
            
            _logger.info("🚀 Iniciando _process_documents_web_services()...")

            # Procesar el documento EDI usando el framework estándar con contexto manual
            edi_document.with_context(force_manual_send=True)._process_documents_web_services()
            
            _logger.info(f"🏁 _process_documents_web_services() completado. Estado final: {edi_document.state}")
            _logger.info(f"💬 Error en documento: {edi_document.error if edi_document.error else 'Ninguno'}")
            _logger.info(f"📊 Track ID: {self.l10n_do_track_id if hasattr(self, 'l10n_do_track_id') else 'Ninguno'}")
            
            # Obtener resultado basado en el estado del documento EDI
            result_message = ""
            if edi_document.state == 'sent':
                _logger.info("✅ Estado marcado como 'sent' - Generando mensaje de éxito")
                result_message = f"✅ El documento fue enviado correctamente a la DGII\n"
                if self.l10n_do_track_id:
                    result_message += f"trackId: {self.l10n_do_track_id}\n"
                result_message += f"codigo: 1\nestado: Enviado\n"
                if hasattr(self, 'l10n_latam_document_number'):
                    result_message += f"encf: {self.l10n_latam_document_number}\n"
                result_message += f"fechaEnvio: {fields.Datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')}\n"
            elif edi_document.error:
                _logger.error(f"❌ Error en documento EDI: {edi_document.error}")
                result_message = f"❌ Error al procesar documento EDI:\n{edi_document.error}"
            else:
                result_message = f"📤 Documento EDI en proceso (Estado: {edi_document.state})\n"
                result_message += "Revise los mensajes de la factura para ver actualizaciones."
            
            # Mostrar resultado en popup
            return {
                'type': 'ir.actions.act_window',
                'name': 'Resultado del envío a DGII',
                'res_model': 'dgii.result.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_message': result_message,
                    'default_move_id': self.id,
                }
            }
            
        except Exception as e:
            # En caso de error, mostrar el error
            return {
                'type': 'ir.actions.act_window',
                'name': 'Error en envío a DGII',
                'res_model': 'dgii.result.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_message': f"❌ Error al enviar a DGII:\n{str(e)}",
                    'default_move_id': self.id,
                }
            }

    @api.model
    def _ensure_edi_format_compatibility(self):
        """Asegurar que los journals tengan el formato EDI correcto configurado"""
        # Buscar el formato EDI de República Dominicana
        edi_format = self.env['account.edi.format'].search([
            ('code', '=', 'dgii_ecf')
        ], limit=1)
        
        if edi_format:
            # Configurar formato EDI en journals de facturas para compañías de RD
            # Obtener compañías con ECF activado y filtrar por país en Python
            all_companies = self.env['res.company'].search([
                ('l10n_do_ecf_activated', '=', True)
            ])
            # Filtrar por país DO en Python (country_id es campo computado)
            do_companies = all_companies.filtered(lambda c: c.country_id and c.country_id.code == 'DO')
            if not do_companies:
                return
            journals = self.env['account.journal'].search([
                ('type', 'in', ['sale', 'purchase']),
                ('company_id', 'in', do_companies.ids)
            ])
            
            for journal in journals:
                if edi_format not in journal.edi_format_ids:
                    journal.write({
                        'edi_format_ids': [(4, edi_format.id)]
                    })
                    _logger.info(f"Formato EDI 'dgii_ecf' agregado al journal {journal.name}")

    def _post(self, soft=True):
        # Asegurar configuración EDI antes del proceso
        self._ensure_edi_format_compatibility()
        
        # Llamar al método padre primero (esto incluye el procesamiento EDI estándar)
        result = super()._post(soft)
        
        # El sistema EDI estándar ya se encarga del procesamiento automático
        # Solo agregamos logging para debug si es necesario
        for move in self.filtered(lambda m: m.company_id.country_id.code == 'DO' and m.company_id.l10n_do_ecf_activated):
            if move.state == 'posted' and move.move_type in ['out_invoice', 'out_refund']:
                _logger.info(f"Factura DGII procesada: {move.name} - Estado EDI: {move.edi_state}")
                
                # Solo agregar mensaje si hay documentos EDI procesados
                if move.edi_document_ids:
                    for edi_doc in move.edi_document_ids.filtered(lambda d: d.edi_format_id.code == 'dgii_ecf'):
                        if edi_doc.state == 'to_send':
                            move.with_context(no_new_invoice=True).message_post(
                                body="📤 Documento EDI preparado para envío a DGII"
                            )
        
        return result

    def button_process_edi_web_services(self):
        """Procesar documentos EDI manualmente"""
        self.ensure_one()
        
        # Buscar documentos EDI pendientes
        edi_docs_to_process = self.edi_document_ids.filtered(
            lambda d: d.state in ('to_send', 'to_cancel') and d.blocking_level != 'error'
        )
        
        if not edi_docs_to_process:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sin documentos EDI',
                    'message': 'No hay documentos EDI pendientes de procesar.',
                    'type': 'warning',
                }
            }
        
        # Procesar los documentos
        edi_docs_to_process._process_documents_web_services()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Documentos EDI procesados',
                'message': f'Se procesaron {len(edi_docs_to_process)} documento(s) EDI.',
                'type': 'success',
            }
        }
    #     res = super()._post(soft)
    #     # 3) Devolvemos el recordset ya "posted" para hacer el envío EDI
    #     if to_process:
    #         # Agrupamos por formato
    #         for fmt in to_process.mapped('journal_id.edi_format_ids'):
    #             invs = to_process.filtered(lambda inv: fmt in inv.journal_id.edi_format_ids)
    #             # Creamos o marcamos documentos en estado to_send
    #             docs = self.env['account.edi.document']
    #             for inv in invs:
    #                 doc = docs.search([
    #                     ('move_id', '=', inv.id),
    #                     ('edi_format_id', '=', fmt.id),
    #                 ], limit=1)
    #                 if not doc:
    #                     doc = docs.create({
    #                         'move_id':       inv.id,
    #                         'edi_format_id': fmt.id,
    #                         'state':         'to_send',
    #                     })
    #                 docs |= doc
    #             # Procesamos síncronamente (llama internamente a _post_invoice_edi + post‐procesado)
    #             docs._process_documents_web_services(job_count=len(docs))
    #     return res