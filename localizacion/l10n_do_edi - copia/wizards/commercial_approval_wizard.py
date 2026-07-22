# -*- coding: utf-8 -*-
import base64
import json
import logging
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime as dt
from lxml import etree
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from collections import OrderedDict as od
import xmltodict
import requests

_logger = logging.getLogger(__name__)

class L10nDoCommercialApprovalWizard(models.TransientModel):
    _name = 'l10n.do.commercial.approval.wizard'
    _description = 'Wizard para Aprobación Comercial'

    move_id = fields.Many2one('account.move', string='Factura', required=True)
    status = fields.Selection([
        ('1', 'e-CF Aceptado (puede incluir advertencias)'),
        ('2', 'e-CF Rechazado'),
    ], string='Estado de aprobación comercial', default='1', required=True)
    detail = fields.Char(string='Detalle de aprobación comercial')
    date_approval = fields.Char(string='Fecha de Aprobación (dd-mm-yyyy hh:mm:ss)')
    show_date_field = fields.Boolean(string='Mostrar campo de fecha', compute='_compute_show_date_field')
    
    @api.depends('move_id')
    def _compute_show_date_field(self):
        for record in self:
            if record.move_id and record.move_id.company_id:
                record.show_date_field = record.move_id.company_id.l10n_do_ecf_environment != 'production'
            else:
                record.show_date_field = False

    def action_accept(self):
        """Procesa la aprobación comercial"""
        self.ensure_one()
        
        # Validaciones básicas
        if not self.move_id.l10n_latam_document_number:
            raise UserError(_("La factura debe tener un número de documento válido"))
        
        if not self.move_id.company_id.l10n_do_ecf_activated:
            raise UserError(_("La facturación electrónica no está activada en la empresa"))
        
        if not self.move_id.company_id.l10n_do_pkcs12_file:
            raise UserError(_("No se encontró el certificado PKCS#12 en la empresa"))
        
        xml_data = None
        signed_filename = None
        
        try:
            # 1. Generar XML de aprobación comercial
            xml_data = self._generate_commercial_approval_xml()
            
            # 2. Firmar XML
            signed_filename = self._sign_commercial_approval_xml(xml_data)
            
            # 3. Enviar a la DGII usando el mismo método que account_edi_format.py
            response = self._send_commercial_approval_xml(signed_filename)
            
            # 4. Guardar resultado
            self._save_commercial_approval_result(response)

            # 5. Adjuntar XML firmado al chatter
            attachment_ids = []
            if signed_filename:
                try:
                    with open(signed_filename, 'r', encoding='utf-8') as f:
                        signed_xml_content = f.read()
                    
                    # Crear archivo adjunto con el XML firmado
                    attachment_name = f"xml_aprobacion_comercial_{self.move_id.l10n_latam_document_number or 'success'}.xml"
                    attachment = self.env['ir.attachment'].create({
                        'name': attachment_name,
                        'type': 'binary',
                        'datas': base64.b64encode(signed_xml_content.encode('utf-8')),
                        'res_model': 'account.move',
                        'res_id': self.move_id.id,
                        'mimetype': 'application/xml',
                    })
                    
                    attachment_ids.append(attachment.id)
                    
                except Exception as read_error:
                    _logger.error(f"Error adjuntando XML en caso de éxito: {str(read_error)}")

            # 6. Agregar mensaje de éxito al chatter y cerrar wizard
            success_message = f"✅ Aprobación comercial procesada correctamente.\n\n"
            success_message += f"📋 Detalles:\n"
            success_message += f"   - Estado: {'Aceptado' if self.status == '1' else 'Rechazado'}\n"
            success_message += f"   - Detalle: {self.detail or 'N/A'}\n"
            success_message += f"   - Fecha: {dt.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
            success_message += f"📄 Respuesta DGII:\n{json.dumps(response, ensure_ascii=False, indent=2)}"
            
            if attachment_ids:
                success_message += f"\n\n📎 XML firmado adjuntado como archivo"
            
            self.move_id.message_post(
                body=success_message,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                attachment_ids=attachment_ids
            )
            
            return {'type': 'ir.actions.act_window_close'}
            
        except Exception as e:
            # Log detallado del error con XML y respuesta
            error_details = f"❌ Error en aprobación comercial: {str(e)}"
            
            # Adjuntar XML firmado al chatter si existe
            attachment_ids = []
            if signed_filename:
                try:
                    with open(signed_filename, 'r', encoding='utf-8') as f:
                        signed_xml_content = f.read()
                    
                    # Crear archivo adjunto con el XML firmado
                    attachment_name = f"xml_aprobacion_comercial_{self.move_id.l10n_latam_document_number or 'error'}.xml"
                    attachment = self.env['ir.attachment'].create({
                        'name': attachment_name,
                        'type': 'binary',
                        'datas': base64.b64encode(signed_xml_content.encode('utf-8')),
                        'res_model': 'account.move',
                        'res_id': self.move_id.id,
                        'mimetype': 'application/xml',
                    })
                    
                    attachment_ids.append(attachment.id)
                    error_details += f"\n\n📎 XML firmado adjuntado como archivo"
                    
                except Exception as read_error:
                    error_details += f"\n\n⚠️ No se pudo adjuntar el XML firmado: {str(read_error)}"
            
            # Log del error detallado
            _logger.error(error_details)
            
            # Agregar mensaje al chatter de la factura con archivos adjuntos
            self.move_id.message_post(
                body=error_details,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                attachment_ids=attachment_ids
            )
            
            # Cerrar wizard sin mostrar notificación sticky
            return {'type': 'ir.actions.act_window_close'}

    def action_reject(self):
        """Cierra el wizard sin hacer nada"""
        return {'type': 'ir.actions.act_window_close'}

    def _generate_commercial_approval_xml(self):
        """Genera el XML de aprobación comercial según el formato especificado"""
        try:
            move = self.move_id
            move.l10n_do_date_commercial_approval = dt.now()
            move.l10n_do_status_commercial_approval = self.status
            move.l10n_do_detail_commercial_approval = self.detail
            
            # Estructura del XML según el formato de aprobación comercial
            detalle_aprobacion = od({
                'Version': '1.0',
                'RNCEmisor': move.partner_id.vat or '',
                'eNCF': move.l10n_latam_document_number,
                'FechaEmision': dt.strftime(move.invoice_date, "%d-%m-%Y"),
                'MontoTotal': move.amount_untaxed,
                'RNCComprador': move.company_id.vat,
                'Estado': move.l10n_do_status_commercial_approval,
            })
            
            # Agregar DetalleMotivoRechazo solo si hay contenido (antes de FechaHoraAprobacionComercial)
            if move.l10n_do_detail_commercial_approval and move.l10n_do_status_commercial_approval == '2':
                detalle_aprobacion['DetalleMotivoRechazo'] = move.l10n_do_detail_commercial_approval
            
            # Agregar FechaHoraAprobacionComercial al final
            # Validar y usar el campo date_approval si está disponible
            if self.date_approval:
                try:
                    # Validar formato dd-mm-yyyy hh:mm:ss
                    parsed_date = dt.strptime(self.date_approval.strip(), "%d-%m-%Y %H:%M:%S")
                    detalle_aprobacion['FechaHoraAprobacionComercial'] = self.date_approval.strip()
                except ValueError:
                    # Si el formato no es correcto, usar la fecha de la factura
                    detalle_aprobacion['FechaHoraAprobacionComercial'] = dt.strftime(move.l10n_do_date_commercial_approval, "%d-%m-%Y %H:%M:%S")
            else:
                # Si no hay date_approval, usar la fecha de la factura
                detalle_aprobacion['FechaHoraAprobacionComercial'] = dt.strftime(move.l10n_do_date_commercial_approval, "%d-%m-%Y %H:%M:%S")
            
            approval_data = od({
                'ACECF': od({
                    'DetalleAprobacionComercial': detalle_aprobacion
                })
            })
            
            xml_string = xmltodict.unparse(approval_data)
            return xml_string
            
        except Exception as e:
            error_msg = f"❌ Error generando XML de aprobación comercial: {str(e)}\n\n"
            error_msg += f"📋 Datos de la factura:\n"
            error_msg += f"   - RNC Emisor: {move.partner_id.vat or 'N/A'}\n"
            error_msg += f"   - eNCF: {move.l10n_latam_document_number or 'N/A'}\n"
            error_msg += f"   - Fecha: {move.invoice_date or 'N/A'}\n"
            error_msg += f"   - Monto: {move.amount_untaxed or 'N/A'}\n"
            error_msg += f"   - RNC Comprador: {move.company_id.vat or 'N/A'}\n"
            error_msg += f"   - Estado: {self.status}\n"
            error_msg += f"   - Detalle: {self.detail or 'N/A'}"
            _logger.error(error_msg)
            raise UserError(_(error_msg))

    def _sign_commercial_approval_xml(self, xml_data):
        """Firma el XML de aprobación comercial"""
        try:
            move = self.move_id
            company = move.company_id
            
            if not company.l10n_do_pkcs12_file or not company.l10n_do_pkcs12_password:
                raise ValidationError(_("No se encontró el certificado en la empresa o la contraseña está vacía"))
            
            # Crear archivo temporal
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as temp_xml_file:
                temp_xml_file.write(xml_data.encode("utf-8"))
                temp_xml_file_path = temp_xml_file.name
            
            # Firmar XML usando el mismo método que account_edi_format.py
            signed_filename = temp_xml_file_path.replace('.xml', '_signed.xml')
            self._sign_xml(temp_xml_file_path, signed_filename, company)
            
            return signed_filename
            
        except Exception as e:
            error_msg = f"❌ Error firmando XML de aprobación comercial: {str(e)}\n\n"
            error_msg += f"📋 Datos de la empresa:\n"
            error_msg += f"   - RNC: {company.vat or 'N/A'}\n"
            error_msg += f"   - Certificado PKCS#12: {'Sí' if company.l10n_do_pkcs12_file else 'No'}\n"
            error_msg += f"   - Contraseña: {'Sí' if company.l10n_do_pkcs12_password else 'No'}\n"
            error_msg += f"   - Ambiente: {company.l10n_do_ecf_environment or 'N/A'}\n\n"
            error_msg += f"📄 XML Original (primeros 500 caracteres):\n{xml_data[:500]}..."
            _logger.error(error_msg)
            raise UserError(_(error_msg))

    def _sign_xml(self, xml_path, output_path, company):
        """Firma el XML usando el certificado PKCS#12 - mismo método que account_edi_format.py"""
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.primitives.hashes import SHA256
            from cryptography.hazmat.primitives.serialization import pkcs12
            
            p12_content = base64.b64decode(company.l10n_do_pkcs12_file)
            key, cert, _ = pkcs12.load_key_and_certificates(p12_content, company.l10n_do_pkcs12_password.encode())
            cert_b64 = base64.b64encode(cert.public_bytes(encoding=serialization.Encoding.DER)).decode()
            
            parser = etree.XMLParser(remove_blank_text=True)
            tree = etree.parse(xml_path, parser)
            root = tree.getroot()
            
            # Calcular digest usando el mismo método que account_edi_format.py
            xml_c14n = etree.tostring(root, method="c14n", exclusive=False, with_comments=False).decode()
            import hashlib
            digest = hashlib.sha256(xml_c14n.encode()).digest()
            digest_value = base64.b64encode(digest).decode()
            
            # Crear firma usando el mismo patrón que account_edi_format.py
            ns_ds = "http://www.w3.org/2000/09/xmldsig#"
            ns_xsd = "http://www.w3.org/2001/XMLSchema"
            ns_xsi = "http://www.w3.org/2001/XMLSchema-instance"
            signature = etree.Element("Signature", nsmap={None: ns_ds})
            signed_info = etree.SubElement(signature, "SignedInfo", nsmap={None: ns_ds, "xsd": ns_xsd, "xsi": ns_xsi})
            
            etree.SubElement(signed_info, "CanonicalizationMethod", Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315")
            etree.SubElement(signed_info, "SignatureMethod", Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256")
            
            reference = etree.SubElement(signed_info, "Reference", URI="")
            transforms = etree.SubElement(reference, "Transforms")
            etree.SubElement(transforms, "Transform", Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature")
            etree.SubElement(reference, "DigestMethod", Algorithm="http://www.w3.org/2001/04/xmlenc#sha256")
            etree.SubElement(reference, "DigestValue").text = digest_value
            
            # Firmar
            signed_info_str = etree.tostring(signed_info, method="c14n", exclusive=False, with_comments=False)
            signer = key.sign(signed_info_str, padding.PKCS1v15(), SHA256())
            signature_value = base64.b64encode(signer).decode()
            
            etree.SubElement(signature, "SignatureValue").text = signature_value
            
            # Información de clave
            key_info = etree.SubElement(signature, "KeyInfo")
            x509_data = etree.SubElement(key_info, "X509Data")
            etree.SubElement(x509_data, "X509Certificate").text = cert_b64
            
            root.append(signature)
            tree.write(output_path, encoding="utf-8", xml_declaration=True, pretty_print=True)
            
        except Exception as e:
            error_msg = f"Error firmando XML: {str(e)}"
            _logger.error(error_msg)
            raise UserError(_(error_msg))

    def _send_commercial_approval_xml(self, signed_filename):
        """Envía el XML de aprobación comercial a la DGII usando el mismo patrón que account_edi_format.py"""
        move = self.move_id
        company = move.company_id

        # Obtener token de autenticación usando el mismo método
        token = self._get_token(company)
        
        # Determinar URL según ambiente usando las constantes de account_edi_format.py
        if company.l10n_do_ecf_environment == 'pre_certification':
            url_aprobacion = "https://ecf.dgii.gov.do/testecf/aprobacioncomercial/api/aprobacioncomercial"
        elif company.l10n_do_ecf_environment == 'certification':
            url_aprobacion = "https://ecf.dgii.gov.do/certecf/aprobacioncomercial/api/aprobacioncomercial"
        elif company.l10n_do_ecf_environment == 'production':
            url_aprobacion = "https://ecf.dgii.gov.do/ecf/aprobacioncomercial/api/aprobacioncomercial"
        else:
            raise ValidationError(_("Ambiente no válido en la configuración de la empresa"))
        
        # Preparar headers y archivo usando el mismo patrón que _send_xml_to_dgii
        headers = {
            "accept": "application/json",
            "Authorization": f"bearer {token}"
        }
        

        
        with open(signed_filename, 'rb') as file:
            files = {
                "xml": (f"{company.vat}_{move.l10n_latam_document_number}_approval.xml", file, "text/xml")
            }
            
            try:
                response = requests.post(url_aprobacion, headers=headers, files=files, timeout=20)
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.HTTPError as errh:
                error_msg = f"❌ Error HTTP: {errh} - Código: {response.status_code}"
                if hasattr(response, 'text') and response.text:
                    error_msg += f"\n\nDetalle del error:\n{response.text}"
                _logger.error(error_msg)
                raise UserError(_(error_msg))
                
            except requests.exceptions.ConnectionError as errc:
                error_msg = f"❌ Error de Conexión: {errc}"
                _logger.error(error_msg)
                raise UserError(_(error_msg))
                
            except requests.exceptions.Timeout as errt:
                error_msg = f"⏳ Timeout: {errt}"
                _logger.error(error_msg)
                raise UserError(_(error_msg))
                
            except requests.exceptions.RequestException as err:
                error_msg = f"❌ Error inesperado: {err}"
                _logger.error(error_msg)
                raise UserError(_(error_msg))

    def _get_token(self, company):
        """Obtiene el token de autenticación de la DGII usando el mismo método que account_edi_format.py"""
        try:
            edi_format = self.env['account.edi.format'].search([('code', '=', 'dgii_ecf')], limit=1)
            if not edi_format:
                raise ValidationError(_("No se encontró el formato EDI DGII"))
            
            return edi_format._get_token(company)
            
        except Exception as e:
            error_msg = f"❌ Error obteniendo token de autenticación: {str(e)}\n\n"
            error_msg += f"📋 Datos de la empresa:\n"
            error_msg += f"   - RNC: {company.vat or 'N/A'}\n"
            error_msg += f"   - Ambiente: {company.l10n_do_ecf_environment or 'N/A'}\n"
            error_msg += f"   - Certificado P12: {'Sí' if company.l10n_do_pkcs12_file else 'No'}\n"
            error_msg += f"   - Contraseña P12: {'Sí' if company.l10n_do_pkcs12_password else 'No'}\n"
            error_msg += f"   - Formato EDI encontrado: {'Sí' if edi_format else 'No'}"
            _logger.error(error_msg)
            raise UserError(_(error_msg))

    def _save_commercial_approval_result(self, response):
        """Guarda el resultado de la aprobación comercial"""
        try:
            move = self.move_id
            
            # Guardar campos en la factura
            move.write({
                'l10n_do_status_commercial_approval': self.status,
                'l10n_do_detail_commercial_approval': self.detail,
                'l10n_do_result_commercial_approval': json.dumps(response, ensure_ascii=False),
                'l10n_do_dgii_commercial_approval': True,
            })
            
        except Exception as e:
            error_msg = f"❌ Error guardando resultado de aprobación comercial: {str(e)}\n\n"
            error_msg += f"📋 Datos de la factura:\n"
            error_msg += f"   - ID: {move.id}\n"
            error_msg += f"   - Número: {move.name or 'N/A'}\n"
            error_msg += f"   - Estado: {self.status}\n"
            error_msg += f"   - Detalle: {self.detail or 'N/A'}\n\n"
            error_msg += f"📄 Respuesta de DGII:\n{json.dumps(response, ensure_ascii=False, indent=2)}"
            _logger.error(error_msg)
            raise UserError(_(error_msg)) 