# -*- coding: utf-8 -*-
from collections import OrderedDict as od
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding
from datetime import datetime as dt
from lxml import etree
from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError, RedirectWarning
from odoo.modules.module import get_module_path
from typing import Dict, List, Any, Union
from markupsafe import Markup
from urllib.parse import quote

import base64
import hashlib
import json
import logging
import re
import requests
import os
import tempfile
import xml.etree.ElementTree as ET
import xmlrpc.client
import xmltodict
import pyqrcode

PRE_CERTIFICATION_URL = {
    'semilla': "https://ecf.dgii.gov.do/testecf/autenticacion/api/Autenticacion/Semilla",
    'validar_semilla': "https://ecf.dgii.gov.do/testecf/autenticacion/api/Autenticacion/ValidarSemilla",
    'recepcion': "https://ecf.dgii.gov.do/testecf/recepcion/api/FacturasElectronicas",
    'consulta': "https://ecf.dgii.gov.do/testecf/consultaresultado/api/Consultas/Estado",
    'recepcion_fc': "https://fc.dgii.gov.do/testecf/recepcionfc/api/recepcion/ecf",
    'aprobacion_comercial': "https://ecf.dgii.gov.do/testecf/aprobacioncomercial/api/aprobacioncomercial",
}
CERTIFICATION_URL = {
    'semilla': "https://ecf.dgii.gov.do/certecf/autenticacion/api/Autenticacion/Semilla",
    'validar_semilla': "https://ecf.dgii.gov.do/certecf/autenticacion/api/Autenticacion/ValidarSemilla",
    'recepcion': "https://ecf.dgii.gov.do/certecf/recepcion/api/FacturasElectronicas",
    'consulta': "https://ecf.dgii.gov.do/certecf/consultaresultado/api/Consultas/Estado",
    'recepcion_fc': "https://fc.dgii.gov.do/certecf/recepcionfc/api/recepcion/ecf",
    'aprobacion_comercial': "https://ecf.dgii.gov.do/certecf/aprobacioncomercial/api/aprobacioncomercial",
}
PRODUCTION_URL = {
    'semilla': "https://ecf.dgii.gov.do/ecf/autenticacion/api/Autenticacion/Semilla",
    'validar_semilla': "https://ecf.dgii.gov.do/ecf/autenticacion/api/Autenticacion/ValidarSemilla",
    'verificar_estado': "https://statusecf.dgii.gov.do/api/estatusservicios/verificarestado",
    'recepcion': "https://ecf.dgii.gov.do/ecf/recepcion/api/FacturasElectronicas",
    'consulta': "https://ecf.dgii.gov.do/ecf/consultaresultado/api/Consultas/Estado",
    'recepcion_fc': "https://fc.dgii.gov.do/ecf/recepcionfc/api/recepcion/ecf",
    'aprobacion_comercial': "https://ecf.dgii.gov.do/ecf/aprobacioncomercial/api/aprobacioncomercial",
}

URL = 'https://ecf.counter.overloadsolutions.com.do'
DB = 'ODOOV18'
USERNAME = 'info@overloadsolutions.com.do'
PASSWORD = 'e50ba066ad399f9d1d7739ce3f43d05bbe43dab3'

RESUMEN_AMOUNT_LIMIT = 250000

_logger = logging.getLogger(__name__)

# Módulo EDI con correcciones IndicadorFacturacion
_logger.debug("Módulo l10n_do_edi cargado - versión get_invoicing_indicator simplificada")

class AccountEdiFormatDGII(models.Model):
    _inherit = 'account.edi.format'

    def _get_tax_group_safe(self, external_id, fallback_name):
        """Obtiene un grupo de impuestos de forma segura con fallback"""
        try:
            return self.env.ref(external_id)
        except ValueError:
            # Fallback: buscar por nombre si no existe el External ID
            tax_group = self.env['account.tax.group'].search([
                ('name', 'ilike', fallback_name),
                ('country_id.code', '=', 'DO')
            ], limit=1)
            if not tax_group:
                # Crear el grupo si no existe
                tax_group = self.env['account.tax.group'].create({
                    'name': fallback_name,
                    'country_id': self.env.ref('base.do').id
                })
            return tax_group

    def json_to_string(self, data):
        """Formatea la respuesta de DGII de manera legible y profesional"""

        # DEBUG: Mostrar TODA la respuesta de DGII para identificar campos de error
        _logger.info(f"🔍 DEBUG DGII - RESPUESTA COMPLETA: {data}")

        # Extraer valores principales
        track_id = data.get('trackId', 'N/A')
        codigo = data.get('codigo', 'N/A')
        estado = data.get('estado', 'N/A')
        rnc = data.get('rnc', 'N/A')
        encf = data.get('encf', 'N/A')
        secuencia = data.get('secuenciaUtilizada', False)

        # Extraer mensajes de error de la lista 'mensajes' de la DGII
        error_dgii = ""
        mensajes_dgii = data.get('mensajes', [])
        if mensajes_dgii and isinstance(mensajes_dgii, list):
            errores_list = []
            for msg in mensajes_dgii:
                codigo_error = msg.get('codigo', '')
                valor_error = msg.get('valor', '')
                if valor_error:
                    if codigo_error:
                        errores_list.append(f"[{codigo_error}] {valor_error}")
                    else:
                        errores_list.append(valor_error)
            error_dgii = "<br/>".join(errores_list)

        # Fallback: Buscar campos de error alternativos si no hay mensajes
        if not error_dgii:
            error_dgii = data.get('mensaje', data.get('error', data.get('motivo', data.get('descripcion', ''))))

        _logger.info(f"🔍 DEBUG DGII - Errores extraídos: '{error_dgii}'")
        fecha_recepcion = data.get('fechaRecepcion', 'N/A')

        # Formatear fecha si está disponible
        if fecha_recepcion != 'N/A':
            try:
                from datetime import datetime
                # Convertir formato americano a formato más legible
                dt = datetime.strptime(fecha_recepcion, '%m/%d/%Y %I:%M:%S %p')
                fecha_recepcion = dt.strftime('%d/%m/%Y %H:%M:%S')
            except:
                pass

        # Determinar icono de estado y color según código
        if codigo == '1':
            estado_icon = "✅"
            color_border = "#28a745"
            titulo_estado = "🟢 DOCUMENTO AUTORIZADO EXITOSAMENTE"
            color_titulo = "#28a745"
        elif codigo == '4':
            estado_icon = "⚠️"
            color_border = "#ffc107"
            titulo_estado = "🟡 DOCUMENTO AUTORIZADO CON ADVERTENCIAS"
            color_titulo = "#ffc107"
        else:
            estado_icon = "❌"
            color_border = "#dc3545"
            titulo_estado = "🔴 DOCUMENTO RECHAZADO"
            color_titulo = "#dc3545"

        secuencia_text = "Sí" if secuencia else "No"

        # Construir sección de error si existe
        error_section = ""
        if error_dgii and str(error_dgii).strip():
            error_section = f"""
    <div style="margin-top: 15px; padding: 10px; background-color: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px;">
        <strong style="color: #721c24;">⚠️ MOTIVO DEL RECHAZO DGII:</strong><br/>
        <span style="color: #721c24;">{error_dgii}</span>
    </div>"""

        # Construir mensaje formateado
        mensaje = f"""
<div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 4px solid {color_border};">
    <h4 style="color: {color_titulo}; margin: 0 0 10px 0;">{titulo_estado}</h4>

    <div style="margin-bottom: 15px;">
        <strong>📋 INFORMACIÓN DE AUTORIZACIÓN DGII:</strong><br/>
        • <strong>Estado:</strong> {estado} {estado_icon}<br/>
        • <strong>e-NCF:</strong> {encf}<br/>
        • <strong>RNC:</strong> {rnc}<br/>
        • <strong>Fecha de Recepción:</strong> {fecha_recepcion}
    </div>

    <div style="font-size: 0.9em; color: #6c757d;">
        <strong>📄 DETALLES TÉCNICOS:</strong><br/>
        • <strong>Track ID:</strong> {track_id}<br/>
        • <strong>Código de Respuesta:</strong> {codigo}<br/>
        • <strong>Secuencia Utilizada:</strong> {secuencia_text}
    </div>

    {error_section}
</div>"""

        return mensaje.strip()
    
    def _format_dgii_message(self, response, message_type="success"):
        """Genera mensaje formateado según el tipo de respuesta DGII"""
        
        # Valores base
        track_id = response.get('trackId', '')
        codigo = response.get('codigo', '')
        estado = response.get('estado', 'Procesado')
        rnc = response.get('rnc', '')
        encf = response.get('encf', '')
        secuencia = response.get('secuenciaUtilizada', False)
        fecha_recepcion = response.get('fechaRecepcion', '')
        
        # Formatear fecha
        fecha_formateada = ''
        if fecha_recepcion:
            try:
                from datetime import datetime
                dt = datetime.strptime(fecha_recepcion, '%m/%d/%Y %I:%M:%S %p')
                fecha_formateada = dt.strftime('%d/%m/%Y %H:%M:%S')
            except:
                fecha_formateada = fecha_recepcion
        
        secuencia_text = "Sí" if secuencia else "No"
        
        # Configurar según tipo de mensaje
        if message_type == "success":
            color = "#28a745"
            icon = "🟢"
            titulo = "DOCUMENTO AUTORIZADO EXITOSAMENTE"
            estado_icon = "✅"
        elif message_type == "warning":
            color = "#ffc107"
            icon = "🟡"
            titulo = "DOCUMENTO AUTORIZADO CON ADVERTENCIAS"
            estado_icon = "⚠️"
        else:
            color = "#dc3545"
            icon = "🔴"
            titulo = "ERROR EN AUTORIZACIÓN"
            estado_icon = "❌"
        
        # Construir información principal
        info_principal = []
        info_principal.append(f"• <strong>Estado:</strong> {estado} {estado_icon}")
        
        if encf:
            info_principal.append(f"• <strong>e-NCF:</strong> {encf}")
        
        if rnc:
            info_principal.append(f"• <strong>RNC:</strong> {rnc}")
        
        if fecha_formateada:
            info_principal.append(f"• <strong>Fecha de Recepción:</strong> {fecha_formateada}")
        
        # Construir detalles técnicos
        detalles_tecnicos = []
        
        if track_id:
            detalles_tecnicos.append(f"• <strong>Track ID:</strong> {track_id}")
        
        if codigo:
            codigo_texto = f"{codigo} (Éxito)" if codigo == '1' else f"{codigo}"
            detalles_tecnicos.append(f"• <strong>Código de Respuesta:</strong> {codigo_texto}")
        
        detalles_tecnicos.append(f"• <strong>Secuencia Utilizada:</strong> {secuencia_text}")
        
        # Mensaje formateado
        mensaje = f"""
<div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 4px solid {color};">
    <h4 style="color: {color}; margin: 0 0 10px 0;">{icon} {titulo}</h4>
    
    <div style="margin-bottom: 15px;">
        <strong>📋 INFORMACIÓN DE AUTORIZACIÓN DGII:</strong><br/>
        {'<br/>'.join(info_principal)}
    </div>
    
    <div style="font-size: 0.9em; color: #6c757d;">
        <strong>📄 DETALLES TÉCNICOS:</strong><br/>
        {'<br/>'.join(detalles_tecnicos)}
    </div>
</div>"""
        
        return mensaje.strip()
    
    def _format_dgii_message_simple(self, response, message_type="success"):
        """Genera mensaje formateado en texto plano para evitar escape de HTML"""

        # Valores base
        track_id = response.get('trackId', '')
        codigo = response.get('codigo', '')
        estado = response.get('estado', 'Procesado')

        # Corregir estado cuando es código 4: "Aceptado Condicional" -> "Aceptado"
        # El código 4 significa "Aceptado con advertencias", no "Condicional"
        if str(codigo) == '4' and 'condicional' in estado.lower():
            estado = 'Aceptado'
        elif str(codigo) == '1':
            estado = 'Aceptado'

        rnc = response.get('rnc', '')
        encf = response.get('encf', '')
        secuencia = response.get('secuenciaUtilizada', False)
        fecha_recepcion = response.get('fechaRecepcion', '')
        
        # Formatear fecha
        fecha_formateada = ''
        if fecha_recepcion:
            try:
                from datetime import datetime
                dt = datetime.strptime(fecha_recepcion, '%m/%d/%Y %I:%M:%S %p')
                fecha_formateada = dt.strftime('%d/%m/%Y %H:%M:%S')
            except:
                fecha_formateada = fecha_recepcion
        
        secuencia_text = "Sí" if secuencia else "No"
        
        # Configurar según tipo de mensaje
        if message_type == "success":
            titulo = "🟢 DOCUMENTO AUTORIZADO EXITOSAMENTE"
            estado_icon = "✅"
        elif message_type == "warning":
            titulo = "🟡 DOCUMENTO AUTORIZADO CON ADVERTENCIAS"
            estado_icon = "⚠️"
        else:
            titulo = "🔴 ERROR EN AUTORIZACIÓN"
            estado_icon = "❌"
        
        # Construir mensaje en texto plano
        mensaje_partes = [titulo, ""]
        
        # Información principal
        mensaje_partes.append("📋 INFORMACIÓN DE AUTORIZACIÓN DGII:")
        mensaje_partes.append(f"• Estado: {estado} {estado_icon}")
        
        if encf:
            mensaje_partes.append(f"• e-NCF: {encf}")
        
        if rnc:
            mensaje_partes.append(f"• RNC: {rnc}")
        
        if fecha_formateada:
            mensaje_partes.append(f"• Fecha de Recepción: {fecha_formateada}")
        
        mensaje_partes.append("")  # Línea vacía
        
        # Detalles técnicos
        mensaje_partes.append("📄 DETALLES TÉCNICOS:")
        
        if track_id:
            mensaje_partes.append(f"• Track ID: {track_id}")
        
        if codigo:
            if codigo == '1':
                codigo_texto = f"{codigo} (Éxito)"
            elif str(codigo) == '4':
                codigo_texto = f"{codigo} (Aceptado con advertencias)"
            else:
                codigo_texto = f"{codigo}"
            mensaje_partes.append(f"• Código de Respuesta: {codigo_texto}")

        mensaje_partes.append(f"• Secuencia Utilizada: {secuencia_text}")

        # Si es código 4, agregar sección de advertencias
        if str(codigo) == '4':
            # Buscar advertencias en la respuesta
            advertencia = response.get('mensaje', response.get('descripcion', response.get('errores', '')))

            if advertencia:
                mensaje_partes.append("")  # Línea vacía
                mensaje_partes.append("⚠️ ADVERTENCIA:")

                # Formatear advertencia
                if isinstance(advertencia, list):
                    for adv in advertencia:
                        mensaje_partes.append(f"{adv}")
                elif isinstance(advertencia, dict):
                    for k, v in advertencia.items():
                        mensaje_partes.append(f"{k}: {v}")
                else:
                    mensaje_partes.append(f"{advertencia}")

                # Agregar nota informativa
                mensaje_partes.append("")
                mensaje_partes.append("ℹ️ Este documento ha sido ACEPTADO por la DGII. La advertencia es informativa y no afecta la validez del comprobante fiscal.")

        return "\n".join(mensaje_partes)

    def _generate_xml_normal(self, invoice):
        """Genera XML como factura normal (ECF) para extraer código de seguridad"""
        return self._generate_xml(invoice, is_resumen=False)

    def _generate_xml_resumen(self, invoice, security_code):
        """Genera XML resumen (RFCE) con el código de seguridad extraído"""
        return self._generate_xml(invoice, is_resumen=True, security_code=security_code)

    def _extract_security_code(self, signed_filename):
        """Extrae los primeros 6 dígitos del SignatureValue del XML firmado y la fecha de firma"""
        try:
            tree = ET.parse(signed_filename)
            root = tree.getroot()
            
            ns = {'ds': 'http://www.w3.org/2000/09/xmldsig#'}
            sig_value_el = root.find('.//ds:SignatureValue', ns)
            
            # Extraer fecha de firma también
            fecha_hora_el = root.find('FechaHoraFirma')
            fecha_hora_texto = fecha_hora_el.text if fecha_hora_el is not None else None
            fecha_dt = dt.strptime(fecha_hora_texto, "%d-%m-%Y %H:%M:%S") if fecha_hora_texto else None
            
            if sig_value_el is not None and sig_value_el.text:
                return {
                    'security_code': sig_value_el.text[:6],
                    'sign_date': fecha_dt
                }
            else:
                _logger.error("No se encontró SignatureValue en el XML firmado")
                return None
        except Exception as e:
            _logger.error(f"Error extrayendo código de seguridad: {e}")
            return None

    def _sign_xml_normal(self, xml_data, company):
        """Firma el XML normal y retorna la ruta del archivo firmado"""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as temp_xml_file:
            temp_xml_file.write(xml_data.encode("utf-8"))
            temp_xml_file_path = temp_xml_file.name
        
        signed_filename = temp_xml_file_path.replace('.xml', '_signed.xml')
        self._sign_xml(temp_xml_file_path, signed_filename, company)
        
        return signed_filename

    @api.model
    def _is_compatible_with_journal(self, journal):
        """Determina si este formato EDI es compatible con el journal"""
        if not hasattr(self, 'code') or self.code != 'dgii_ecf':
            return super()._is_compatible_with_journal(journal)
        
        company = journal.company_id
        return (company.country_id.code == 'DO' and 
                company.l10n_do_ecf_activated and 
                journal.type in ('sale', 'purchase'))

    def _is_enabled_by_default_on_journal(self, journal):
        """Determina si debe estar habilitado por defecto"""
        if not hasattr(self, 'code') or self.code != 'dgii_ecf':
            return super()._is_enabled_by_default_on_journal(journal)
        
        # Solo activar automáticamente si está en modo automático
        return journal.company_id.l10n_do_ecf_send_mode == 'automatic'

    def _needs_web_services(self):
        """Indica que este formato EDI necesita servicios web"""
        try:
            if hasattr(self, 'code') and self.code == "dgii_ecf":
                return True
        except:
            # En caso de error de transacción, asumir que no necesita web services
            return False
        return super()._needs_web_services()

    def _get_move_applicability(self, move):
        """Determina si el formato EDI aplica a esta factura y qué métodos usar"""
        if not hasattr(self, 'code') or self.code != 'dgii_ecf':
            return super()._get_move_applicability(move)

        _logger.info(f"🔍 Verificando aplicabilidad para factura {move.name}")
        _logger.info(f"📍 País: {move.company_id.country_id.code}")
        _logger.info(f"⚡ ECF activado: {move.company_id.l10n_do_ecf_activated}")
        _logger.info(f"📄 Tipo de movimiento: {move.move_type}")

        # Verificar si aplica para esta factura
        if (move.company_id.country_id.code != "DO" or
            not move.company_id.l10n_do_ecf_activated or
            move.move_type not in ['out_invoice', 'out_refund', 'in_invoice', 'in_refund']):
            _logger.info("❌ Formato EDI NO aplica para esta factura")
            return {}

        # ✅ CORRECCIÓN CRÍTICA: Solo procesar comprobantes ELECTRÓNICOS
        # Los comprobantes tradicionales (B01, B02, B14, B15, etc.) NO deben pasar por EDI
        # Solo los comprobantes con prefijo 'E' (E31-E47) deben procesarse
        if move.l10n_latam_document_type_id:
            doc_prefix = move.l10n_latam_document_type_id.doc_code_prefix or ''
            _logger.info(f"📋 Tipo de documento: {doc_prefix}")

            # Verificar si es comprobante electrónico (prefijo 'E')
            if not doc_prefix.startswith('E'):
                _logger.info(f"⚠️ Comprobante '{doc_prefix}' NO es electrónico - EDI NO aplica")
                return {}

            # Validar que sea un tipo de e-CF válido (31-47)
            ncf_type = self.get_l10n_do_ncf_type(move)
            valid_ecf_types = ['31', '32', '33', '34', '41', '43', '44', '45', '46', '47']
            if ncf_type not in valid_ecf_types:
                _logger.info(f"⚠️ Tipo e-CF '{ncf_type}' no es válido para EDI - EDI NO aplica")
                return {}
        else:
            # Si no hay tipo de documento, no procesar por EDI
            _logger.info("⚠️ Sin tipo de documento asignado - EDI NO aplica")
            return {}

        _logger.info("✅ Formato EDI SÍ aplica - Retornando métodos")

        # Retornar los métodos que maneja este formato
        return {
            'post': self._post_invoice_edi,
            'edi_content': self._get_invoice_edi_content,
        }
    
    def _get_invoice_edi_content(self, invoice):
        """Genera el contenido EDI para la factura (XML)"""
        xml_data = self._generate_xml(invoice, is_resumen=False)
        return xml_data.encode('utf-8')

    def _is_required_for_invoice(self, invoice):
        """Método legacy - ahora se usa _get_move_applicability"""
        if not hasattr(self, 'code') or self.code != 'dgii_ecf':
            return super()._is_required_for_invoice(invoice)
        
        return bool(self._get_move_applicability(invoice))

    def _check_move_configuration(self, move):
        """Verificar configuración de la factura"""
        errors = super()._check_move_configuration(move)
        
        # Agregar validaciones específicas para DGII si es necesario
        if hasattr(self, 'code') and self.code == 'dgii_ecf':
            if not move.company_id.l10n_do_ecf_activated:
                errors.append("ECF no está activado para esta compañía")
            if move.company_id.country_id.code != 'DO':
                errors.append("Esta compañía no está en República Dominicana")
        
        return errors

    def _has_license(self, vat):
        try:
            common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
            uid = common.authenticate(DB, USERNAME, PASSWORD, {})
            models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')

            partner = models.execute_kw(
                DB, uid, PASSWORD,
                'res.partner', 'search_read',
                [[['vat', '=', vat]]],
                {'fields': ['id'], 'limit': 1}
            )
            if not partner:
                return False

            sale_order = models.execute_kw(
                DB, uid, PASSWORD,
                'sale.order', 'search_read',
                [[['state', '=', 'sale'], ['partner_id', '=', partner[0]['id']]]],
                {'fields': ['id', 'client_order_ref'], 'limit': 1}
            )
            if not sale_order:
                return False

            count = int(sale_order[0].get('client_order_ref') or 0)
            models.execute_kw(
                DB, uid, PASSWORD,
                'sale.order', 'write',
                [[sale_order[0]['id']], {'client_order_ref': str(count + 1)}]
            )
            return True

        except Exception:
            _logger.exception("Error verificando licencia para VAT %s", vat)
            return False


    def format_response_fc(self, data: dict) -> str:
        lineas = []
        if "codigo" in data:
            lineas.append(f"Código: {data['codigo']}")
        if "estado" in data:
            lineas.append(f"Estado: {data['estado']}")
        if "mensajes" in data:
            mensajes = data.get("mensajes", [])
            if mensajes != None:    
                for msg in mensajes:
                    codigo_msg = msg.get("codigo")
                    valor_msg = msg.get("valor")
                    if codigo_msg is not None:
                        lineas.append(f"Código: {codigo_msg}")
                    if valor_msg is not None:
                        lineas.append(f"Valor: {valor_msg}")
        if "encf" in data:
            lineas.append(f"Encf: {data['encf']}")
        if "secuenciaUtilizada" in data:
            lineas.append(f"Secuencia utilizada: {data['secuenciaUtilizada']}")
        return "<br/>".join(lineas)


    def _post_invoice_edi(self, invoices):
        """Procesar envío EDI para facturas (método principal para v17)"""
        _logger.info("🎯 === EJECUTANDO _post_invoice_edi ===")
        _logger.info(f"📊 Facturas a procesar: {len(invoices)}")
        for inv in invoices:
            _logger.info(f"📝 Factura: {inv.name} (ID: {inv.id})")

        edi_result = {}

        for inv in invoices:
            # 🔍 VERIFICAR MODO DE ENVÍO ANTES DE PROCESAR
            company_send_mode = inv.company_id.l10n_do_ecf_send_mode or 'manual'
            force_manual_send = self.env.context.get('force_manual_send', False)

            _logger.info(f"🚦 Modo de envío configurado para {inv.name}: {company_send_mode}")
            _logger.info(f"🔧 Envío manual forzado: {force_manual_send}")

            # Solo procesar automáticamente si está en modo 'automatic' O es envío manual forzado
            if company_send_mode != 'automatic' and not force_manual_send:
                _logger.info(f"⏸️ Saltando envío automático para {inv.name} - Modo: {company_send_mode}")
                edi_result[inv] = {
                    'success': False,
                    'error': f'Envío manual configurado - Use botón "Enviar a DGII"',
                    'attachment': None,
                    'blocking_level': False  # No bloquear, solo informar
                }
                continue

            if force_manual_send:
                _logger.info(f"🔓 Procesando envío manual forzado para {inv.name}")
            else:
                _logger.info(f"⚡ Procesando envío automático para {inv.name}")
            _logger.info(f"🔄 Procesando factura: {inv.name}")
            # Inicializar resultado por defecto
            edi_result[inv] = {'success': False, 'error': '', 'attachment': None}
            
            if inv.move_type not in ['out_invoice', 'out_refund', 'in_invoice', 'in_refund']:
                edi_result[inv]['error'] = f"Tipo de documento no soportado: {inv.move_type}"
                continue  # Ignorar si no es factura o nota de crédito de cliente

            # 🔒 VALIDACIÓN CRÍTICA: Las facturas de proveedor (vendor bills) NO se envían a DGII
            # excepto E41, E43, E47 que son facturas autogeneradas por la empresa
            if inv.move_type in ['in_invoice', 'in_refund']:
                ncf_type = self.get_l10n_do_ncf_type(inv)
                # Solo permitir facturas autogeneradas (compras, gastos menores, pagos exterior)
                allowed_purchase_ncf = ['41', '43', '47']
                if ncf_type not in allowed_purchase_ncf:
                    msg = (f"⏸️ Factura de proveedor {inv.name} con tipo {ncf_type} NO se envía a DGII. "
                           f"Las facturas de proveedor son documentos RECIBIDOS, no emitidos por la empresa. "
                           f"Solo se envían E41, E43, E47 que son autogeneradas.")
                    _logger.info(msg)
                    edi_result[inv] = {
                        'success': False,
                        'error': msg,
                        'attachment': None,
                        'blocking_level': False  # No bloquear, es comportamiento esperado
                    }
                    continue

            # Verificar licencia solo si no está habilitada la omisión
            if not inv.company_id.l10n_do_ecf_skip_license and not self._has_license(inv.company_id.vat):
                error_msg = "Existe algún problema con su licencia para emitir ECF, póngase en contacto con su proveedor"
                edi_result[inv]['error'] = error_msg
                inv.with_context(no_new_invoice=True).message_post(body=_(error_msg))                
                continue

            try:
                token = self._get_token(inv.company_id)

                # Verificación de estado DGII (solo en producción)
                # NOTA: Esta API a veces retorna 401, por lo que se hace opcional
                if inv.company_id.l10n_do_ecf_environment == 'production':
                    try:
                        self._check_state_dgii(inv.company_id, token)
                        _logger.info("✅ Verificación de estado DGII exitosa")
                    except Exception as e:
                        _logger.warning(f"⚠️ No se pudo verificar estado de servicios DGII: {e}. Continuando con el proceso...")

                # 1. Generar XML ECF
                l10n_do_ncf_type = self.get_l10n_do_ncf_type(inv)
                is_resumen = l10n_do_ncf_type == "32" and inv.amount_total < RESUMEN_AMOUNT_LIMIT
                
                if is_resumen:
                    # Para resúmenes, generar primero XML normal para extraer código de seguridad
                    _logger.info(f"Generando XML normal para resumen {inv.l10n_latam_document_number}")
                    
                    # Generar XML normal
                    xml_normal = self._generate_xml_normal(inv)
                    
                    # Firmar XML normal
                    signed_normal_filename = self._sign_xml_normal(xml_normal, inv.company_id)
                    
                    # Extraer código de seguridad y fecha de firma
                    security_data = self._extract_security_code(signed_normal_filename)
                    
                    if not security_data or not security_data.get('security_code'):
                        edi_result[inv]['error'] = "No se pudo extraer el código de seguridad del XML normal"
                        inv.with_context(no_new_invoice=True).message_post(
                            body=_("Error: No se pudo extraer el código de seguridad del XML normal. Proceso cancelado."),
                        )
                        continue
                    
                    security_code = security_data['security_code']
                    sign_date = security_data.get('sign_date')

                    _logger.info(f"Código de seguridad extraído: {security_code}")
                    _logger.info(f"Fecha de firma extraída: {sign_date}")

                    # ========================================================================
                    # CAMBIO CRÍTICO: Guardar el código de seguridad del XML NORMAL
                    # ========================================================================
                    # Este es el código que debe usarse en el QR y que fue enviado en el resumen
                    # DEBE guardarse ANTES de generar el resumen, NO después
                    inv.write({
                        'l10n_do_ecf_security_code': security_code,
                        'l10n_do_ecf_sign_date': sign_date,
                    })
                    _logger.info(f"✅ Código de seguridad guardado en factura: {security_code}")

                    # Crear attachment del XML normal
                    with open(signed_normal_filename, 'rb') as file:
                        normal_signed_data = file.read()
                    normal_attachment_id = self.env['ir.attachment'].create({
                        'name': str(inv.company_id.vat) + str(inv.l10n_latam_document_number) + "_normal.xml",
                        'datas': base64.b64encode(normal_signed_data),
                        'mimetype': 'application/xml',
                        'res_model': 'account.move',
                        'res_id': inv.id,
                        'type': 'binary',
                        'description': 'XML normal generado para extraer código de seguridad del documento %s (%s).' % (inv.l10n_latam_document_number, inv.name),
                    })
                    
                    # Generar XML resumen con el código de seguridad
                    _logger.info(f"Generando XML resumen con código: {security_code}")
                    
                    xml_data = self._generate_xml_resumen(inv, security_code)
                else:
                    # Para facturas normales, usar el flujo actual
                    xml_data = self._generate_xml(inv, is_resumen)
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as temp_xml_file:
                    temp_xml_file.write(xml_data.encode("utf-8"))  
                    temp_xml_file_path = temp_xml_file.name

                # 2. Firmar el documento
                signed_filename = '/tmp/' + str(inv.company_id.vat) + str(inv.l10n_latam_document_number) + '.xml'
                self._sign_xml(temp_xml_file_path, signed_filename, inv.company_id)
                with open(signed_filename, 'rb') as file:
                    signed_data = file.read()
                attachment_id = self.env['ir.attachment'].create({
                    'name': str(inv.company_id.vat) + str(inv.l10n_latam_document_number) + ".xml",
                    'datas': base64.b64encode(signed_data),
                    'mimetype': 'application/xml',
                    'res_model': 'account.move',
                    'res_id': inv.id,
                    'type': 'binary',
                    'description': 'Archivo generado para el documento %s (%s).' % (inv.l10n_latam_document_number, inv.name),
                })
                
                # 3. Enviar a la DGII u otra entidad fiscal
                response = self._send_xml_to_dgii(signed_filename, inv.company_id, token, is_resumen)

                if is_resumen:
                    # Códigos exitosos para resúmenes: 1 (Aceptado), 3 (En Proceso), 4 (Advertencia)
                    if (str(response.get('codigo')) == '1' or str(response.get('codigo')) == '4') and (response != {}):

                        # ========================================================================
                        # CAMBIO CRÍTICO: NO extraer código del resumen firmado
                        # ========================================================================
                        # El código de seguridad del XML NORMAL ya fue guardado (líneas 580-583)
                        # El resumen firmado tiene un SignatureValue DIFERENTE que NO debe usarse
                        # ELIMINADO: extracción del SignatureValue del resumen

                        if str(response.get('codigo')) == '1':
                            formatted_message = self._format_dgii_message_simple(response, "success")
                            inv.with_context(no_new_invoice=True).message_post(
                                body=formatted_message,
                                attachment_ids=[normal_attachment_id.id, attachment_id.id],
                            )
                        elif str(response.get('codigo')) == '4':
                            # Código 4 = Aceptado con advertencias, usar título amarillo
                            formatted_message = self._format_dgii_message_simple(response, "warning")

                            # Guardar estado de aprobación como Aceptado ('1') con detalles de advertencia
                            warning_detail = response.get('mensaje', response.get('descripcion', response.get('errores', 'Documento aceptado con advertencias')))
                            if isinstance(warning_detail, list):
                                warning_detail = " | ".join([str(e) for e in warning_detail])
                            elif isinstance(warning_detail, dict):
                                warning_detail = " | ".join([f"{k}: {v}" for k, v in warning_detail.items()])

                            inv.write({
                                'l10n_do_status_commercial_approval': '1',  # Aceptado (con advertencias)
                                'l10n_do_detail_commercial_approval': str(warning_detail)[:255] if warning_detail else 'Documento aceptado con advertencias',
                                'l10n_do_result_commercial_approval': json.dumps(response, ensure_ascii=False),
                            })

                            inv.with_context(no_new_invoice=True).message_post(
                                body=formatted_message,
                                attachment_ids=[normal_attachment_id.id, attachment_id.id],
                            )

                        edi_result[inv] = {
                            'success': True,
                            'attachment': attachment_id
                        }

                        # El código de seguridad y fecha ya fueron guardados del XML NORMAL (líneas 580-583)
                        # NO sobrescribir aquí, solo generar QR
                        _logger.info(f"📝 Código de seguridad del XML normal: {inv.l10n_do_ecf_security_code}")
                        _logger.info(f"📝 Fecha de firma del XML normal: {inv.l10n_do_ecf_sign_date}")

                        # Generar código QR con el código correcto
                        qr_data = self._generate_qr_code(inv)
                        if qr_data:
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
                                inv.id
                            ))
                            # CRÍTICO: Invalidar cache del ORM para que vea el nuevo valor
                            inv.invalidate_recordset(['qr_code', 'qr_code_data_uri', 'l10n_do_electronic_stamp'])
                            # Forzar recálculo del campo computado qr_code_data_uri para el template PDF
                            inv._compute_qr_code_url()

                            # CRÍTICO: Regenerar el PDF con el QR incluido
                            if inv.invoice_pdf_report_id:
                                try:
                                    _logger.info(f"🔄 Regenerando PDF con QR para {inv.name}")
                                    # Buscar el reporte dominicano
                                    report = self.env['ir.actions.report'].search([
                                        ('report_name', '=', 'l10n_do_accounting.l10n_do_report_invoice_with_payments')
                                    ], limit=1)
                                    if report:
                                        # Generar nuevo PDF
                                        pdf_content, _ = report._render_qweb_pdf(report.id, [inv.id])
                                        # Actualizar el attachment existente
                                        inv.invoice_pdf_report_id.write({
                                            'datas': base64.b64encode(pdf_content),
                                        })
                                        _logger.info(f"✅ PDF regenerado con QR para {inv.name} ({len(pdf_content)} bytes)")
                                    else:
                                        _logger.warning(f"⚠️ Reporte dominicano no encontrado, eliminando PDF viejo")
                                        inv.invoice_pdf_report_id.unlink()
                                        inv.invalidate_recordset(['invoice_pdf_report_id', 'invoice_pdf_report_file'])
                                except Exception as e:
                                    _logger.error(f"❌ Error regenerando PDF para {inv.name}: {e}")

                            _logger.info(f"✅ QR generado con código correcto (SQL): {qr_data['qr_url']}")
                        else:
                            _logger.warning(f"⚠️ No se pudo generar QR para factura {inv.name}")
                    
                    else:
                        # Para resúmenes: documento recibido por DGII pero rechazado por validación
                        formatted_message = self.json_to_string(response)
                        edi_result[inv]['error'] = formatted_message
                        
                        # Usar markup para renderizar HTML correctamente
                        inv.with_context(no_new_invoice=True).message_post(
                            body=Markup(formatted_message),
                            attachment_ids=[normal_attachment_id.id, attachment_id.id],
                        )

                else:

                    if response.get('error'):
                        error_msg = f"Error: {response.get('error')}<br/>{response.get('mensaje', '')}"
                        edi_result[inv] = {'success': False, 'error': error_msg, 'attachment': attachment_id}
                        
                        # Usar markup para renderizar HTML correctamente
                        inv.with_context(no_new_invoice=True).message_post(
                            body=Markup(f"❌ <b>Error de conexión con DGII:</b><br/>{error_msg}"),
                            attachment_ids=attachment_id.ids,
                        )

                    elif response.get('trackId'):

                        tree = ET.parse(signed_filename)
                        root = tree.getroot()

                        ns = {'ds': 'http://www.w3.org/2000/09/xmldsig#'}
                        sig_value_el = root.find('.//ds:SignatureValue', ns)         
                        sig_value_texto = sig_value_el.text if sig_value_el is not None else None           

                        fecha_hora_el = root.find('FechaHoraFirma')
                        fecha_hora_texto = fecha_hora_el.text if fecha_hora_el is not None else None
                        fecha_dt = dt.strptime(fecha_hora_texto, "%d-%m-%Y %H:%M:%S")

                        trackId = response.get('trackId')
                        inv.write({
                            'l10n_do_track_id': trackId,
                        })

                        response = self._check_dgii(
                            inv.company_id, 
                            token, 
                            trackId,
                        )

                        if (str(response.get('codigo')) == '1' or str(response.get('codigo')) == '4') and (response != {}):

                            if response.get('codigo') == '1':
                                formatted_message = self._format_dgii_message_simple(response, "success")
                                inv.with_context(no_new_invoice=True).message_post(
                                    body=formatted_message,
                                    attachment_ids=attachment_id.ids,
                                )
                            elif response.get('codigo') == '4':
                                # Código 4 = Aceptado con advertencias, usar título amarillo
                                formatted_message = self._format_dgii_message_simple(response, "warning")

                                # Guardar estado de aprobación como Aceptado ('1') con detalles de advertencia
                                warning_detail = response.get('mensaje', response.get('descripcion', response.get('errores', 'Documento aceptado con advertencias')))
                                if isinstance(warning_detail, list):
                                    warning_detail = " | ".join([str(e) for e in warning_detail])
                                elif isinstance(warning_detail, dict):
                                    warning_detail = " | ".join([f"{k}: {v}" for k, v in warning_detail.items()])

                                inv.with_context(no_new_invoice=True).message_post(
                                    body=formatted_message,
                                    attachment_ids=attachment_id.ids,
                                )
                            edi_result[inv] = {
                                'success': True,
                                'attachment': attachment_id
                            }

                            # Preparar valores de write
                            write_vals = {
                                'l10n_do_ecf_security_code': sig_value_texto[0:6],
                                'l10n_do_ecf_sign_date': fecha_dt,
                                'l10n_do_status_commercial_approval': '1',  # Aceptado (con o sin advertencias)
                                'l10n_do_result_commercial_approval': json.dumps(response, ensure_ascii=False),
                            }

                            # Agregar detalle de advertencia si código es '4'
                            if response.get('codigo') == '4':
                                warning_detail_local = response.get('mensaje', response.get('descripcion', response.get('errores', 'Documento aceptado con advertencias')))
                                if isinstance(warning_detail_local, list):
                                    warning_detail_local = " | ".join([str(e) for e in warning_detail_local])
                                elif isinstance(warning_detail_local, dict):
                                    warning_detail_local = " | ".join([f"{k}: {v}" for k, v in warning_detail_local.items()])
                                write_vals['l10n_do_detail_commercial_approval'] = str(warning_detail_local)[:255]

                            inv.write(write_vals)
                            
                            # Generar código QR
                            qr_data = self._generate_qr_code(inv)
                            if qr_data:
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
                                    inv.id
                                ))
                                # CRÍTICO: Invalidar cache del ORM para que vea el nuevo valor
                                inv.invalidate_recordset(['qr_code', 'qr_code_data_uri', 'l10n_do_electronic_stamp'])
                                # Forzar recálculo del campo computado qr_code_data_uri para el template PDF
                                inv._compute_qr_code_url()

                                # CRÍTICO: Regenerar el PDF con el QR incluido
                                if inv.invoice_pdf_report_id:
                                    try:
                                        _logger.info(f"🔄 Regenerando PDF con QR para {inv.name}")
                                        report = self.env['ir.actions.report'].search([
                                            ('report_name', '=', 'l10n_do_accounting.l10n_do_report_invoice_with_payments')
                                        ], limit=1)
                                        if report:
                                            pdf_content, _ = report._render_qweb_pdf(report.id, [inv.id])
                                            inv.invoice_pdf_report_id.write({
                                                'datas': base64.b64encode(pdf_content),
                                            })
                                            _logger.info(f"✅ PDF regenerado con QR para {inv.name} ({len(pdf_content)} bytes)")
                                        else:
                                            _logger.warning(f"⚠️ Reporte dominicano no encontrado, eliminando PDF viejo")
                                            inv.invoice_pdf_report_id.unlink()
                                            inv.invalidate_recordset(['invoice_pdf_report_id', 'invoice_pdf_report_file'])
                                    except Exception as e:
                                        _logger.error(f"❌ Error regenerando PDF para {inv.name}: {e}")

                                _logger.info(f"✅ QR generado con SQL directo para {inv.name}")
                            else:
                                _logger.warning(f"No se pudo generar QR para factura {inv.name}")
                            
                        else:
                            # Documento recibido por DGII pero rechazado por validación
                            formatted_message = self.json_to_string(response)
                            edi_result[inv]['error'] = formatted_message

                            # Extraer mensajes de error para guardar en la factura
                            error_detail = ""
                            mensajes_dgii = response.get('mensajes', [])
                            if mensajes_dgii and isinstance(mensajes_dgii, list):
                                errores_list = []
                                for msg in mensajes_dgii:
                                    codigo_error = msg.get('codigo', '')
                                    valor_error = msg.get('valor', '')
                                    if valor_error:
                                        if codigo_error:
                                            errores_list.append(f"[{codigo_error}] {valor_error}")
                                        else:
                                            errores_list.append(valor_error)
                                error_detail = " | ".join(errores_list)

                            # Fallback: Buscar campos de error alternativos
                            if not error_detail:
                                error_detail = response.get('mensaje', response.get('error', response.get('motivo', response.get('descripcion', 'Error desconocido'))))

                            # Actualizar campos de rechazo en la factura
                            try:
                                inv.write({
                                    'l10n_do_status_commercial_approval': '2',  # Rechazado
                                    'l10n_do_detail_commercial_approval': error_detail[:255] if error_detail else 'Rechazado por DGII',
                                    'l10n_do_result_commercial_approval': json.dumps(response, ensure_ascii=False),
                                })
                                _logger.info(f"✅ Campos de rechazo actualizados en factura {inv.name}")
                            except Exception as write_error:
                                _logger.error(f"❌ Error al actualizar campos de rechazo en factura {inv.name}: {str(write_error)}")

                            # Usar markup para renderizar HTML correctamente
                            inv.with_context(no_new_invoice=True).message_post(
                                body=Markup(formatted_message),
                                attachment_ids=attachment_id.ids,
                            )

            except Exception as e:
                # Autor: Arturo Diaz Lora
                # Fecha: 2025-11-22 22:45
                # Razón: Corregir UnboundLocalError al usar _() que no está importado
                error_msg = f"Error durante el procesamiento EDI: {str(e)}"
                edi_result[inv]['error'] = error_msg
                inv.with_context(no_new_invoice=True).message_post(
                    body=error_msg  # Usar error_msg directamente en lugar de _()
                )
                _logger.error(f"Error procesando EDI para factura {inv.name}: {str(e)}", exc_info=True)

        return edi_result
    
    def is_company_currency(self, invoice):
        return invoice.currency_id == invoice.company_id.currency_id


    def is_l10n_do_partner(self, invoice):
        return invoice.partner_id.country_id and invoice.partner_id.country_id.code == "DO"


    def reorder_dict(self, original: Dict[str, Any], desired_order: List[str]) -> Dict[str, Any]:
        """
        Devuelve un nuevo diccionario con las mismas parejas clave-valor de `original`,
        pero reordenadas según `desired_order`.  
        - Las claves en `desired_order` que existen en `original` aparecerán primero, en ese orden.  
        - Cualquier otra clave de `original` que no esté en `desired_order` se añadirá al final, 
        en su orden original de aparición.

        :param original: Diccionario a reordenar.
        :param desired_order: Lista con el orden deseado de algunas (o todas) las claves.
        :return: Un nuevo dict ordenado.
        """
        ordered = od()
        # 1) Añade en el orden deseado sólo las claves que existan
        for key in desired_order:
            if key in original:
                ordered[key] = original[key]
        # 2) Añade al final las claves sobrantes
        for key, value in original.items():
            if key not in ordered:
                ordered[key] = value
        return ordered


    def get_l10n_do_ncf_type(self, invoice):
        """
        Indicates if the document Code Type:

        31: Factura de Crédito Fiscal Electrónica
        32: Factura de Consumo Electrónica
        33: Nota de Débito Electrónica
        34: Nota de Crédito Electrónica
        41: Compras Electrónico
        43: Gastos Menores Electrónico
        44: Regímenes Especiales Electrónica
        45: Gubernamental Electrónico
        46: Comprobante para Exportaciones Electrónico
        47: Comprobante para Pagos al Exterior Electrónico
        """
        #self.ensure_one()
        if invoice:
            return invoice.l10n_latam_document_type_id.doc_code_prefix[1:]
        else:
            return False
    

    def get_payment_type(self, invoice):
        """
        Indicates the type of customer payment. Free delivery invoices (code 3)
        are not valid for Crédito Fiscal.

        1 - Al Contado
        2 - Crédito
        3 - Gratuito
        """
        #self.ensure_one()
        if not invoice.invoice_payment_term_id and invoice.invoice_date_due:
            if (invoice.invoice_date_due and invoice.invoice_date) and invoice.invoice_date_due > invoice.invoice_date:
                return 2
            else:
                return 1
        elif not invoice.invoice_payment_term_id:
            return 1
        elif not invoice.invoice_payment_term_id == invoice.env.ref("account.account_payment_term_immediate"):
            return 2
        else:
            return 1
        

    def get_payment_forms(self, invoice):
        """
        1: Efectivo
        2: Cheque/Transferencia/Depósito
        3: Tarjeta de Débito/Crédito
        4: Venta a Crédito
        5: Bonos o Certificados de regalo
        6: Permuta
        7: Nota de crédito
        8: Otras Formas de pago

        """

        payment_dict = {
            "cash": 1,
            "bank": 2,
            "card": 3,
            "credit": 4,
            "swap": 6,
            "credit_note": 7,
            "others": 8,
        }

        payments = []

        # Método compatible con Odoo v17 para obtener pagos reconciliados
        reconciled_partials = invoice._get_all_reconciled_invoice_partials()
        reconciled_payments = invoice._get_reconciled_payments()
        
        for reconciled_partial in reconciled_partials:
            counterpart_line = reconciled_partial['aml']
            payment_move = counterpart_line.move_id
            payment_amount = reconciled_partial['amount']
            payment_currency = reconciled_partial['currency']
            payment_date = payment_move.date
            
            # Buscar si es un pago real
            payment_id = reconciled_payments.filtered(lambda p: p.move_id == payment_move)
            
            # Si encontramos un pago, usar su información
            if payment_id:
                payment_id = payment_id[0]  # Tomar el primer pago si hay múltiples
                
                if payment_id.journal_id.type in ["cash", "bank"]:
                    payment_form = payment_id.journal_id.l10n_do_payment_form
                    if not payment_form:
                        raise ValidationError(
                            _(
                                "Missing *Payment Form* on %s journal"
                                % payment_id.journal_id.name
                            )
                        )
                    payments.append(
                        {
                            "FormaPago": payment_dict[payment_form],
                            "MontoPago": payment_amount,
                        }
                    )
            else:
                # Si no es un pago directo, puede ser una nota de crédito u otro tipo de movimiento
                if payment_move:
                    # Verificar si es una nota de crédito u otro tipo de movimiento
                    if payment_move.move_type in ['out_refund', 'in_refund']:
                        # Es una nota de crédito
                        payments.append(
                            {
                                "FormaPago": payment_dict["credit_note"],
                                "MontoPago": payment_amount,
                            }
                        )
                    else:
                        # Otro tipo de movimiento (permuta)
                        payments.append(
                            {
                                "FormaPago": payment_dict["swap"],
                                "MontoPago": payment_amount,
                            }
                        )
        if abs(invoice.amount_total_signed) > 0:
            total_payment = 0
            if payments:
                for pay in payments:
                    total_payment += pay['MontoPago']

            credit_payment = abs(invoice.amount_total_signed) - total_payment
            if credit_payment > 0:
                payments.append(
                    {
                        "FormaPago": payment_dict["credit"],
                        "MontoPago": abs(credit_payment),
                    }
                )

        return payments
            

    def _get_IdDoc_data(self, invoice, is_resumen, security_code=None):
        """Document Identification values"""

        idDoc_order = [
            "TipoeCF",
            "eNCF",
            "FechaVencimientoSecuencia",
            "IndicadorNotaCredito",
            "IndicadorEnvioDiferido",
            "IndicadorMontoGravado",
            "TipoIngresos",
            "TipoPago",
            "FechaLimitePago",
            "TerminoPago",
        ]

        l10n_do_ncf_type = self.get_l10n_do_ncf_type(invoice)
        itbis_group = self._get_tax_group_safe("l10n_do_edi.tax_group_itbis", "ITBIS")

        id_doc_data = od(
            {
                "TipoeCF": int(self.get_l10n_do_ncf_type(invoice)),
                "eNCF": invoice.l10n_latam_document_number,
                "FechaVencimientoSecuencia": dt.strftime(
                    invoice.l10n_do_ncf_expiration_date, "%d-%m-%Y"
                ),
            }
        )

        # Notas de Débito (33) y Crédito (34) no llevan FechaVencimientoSecuencia
        # Son documentos de modificación vinculados al documento original
        if l10n_do_ncf_type in ("33", "34"):
            del id_doc_data["FechaVencimientoSecuencia"]

        if l10n_do_ncf_type == "34":
            # Autor: Arturo Diaz Lora
            # Fecha: 2025-11-22 22:30
            # Razón: Corregir TypeError cuando no se encuentra la factura de origen
            # Validar que existe NCF de origen antes de buscar la factura
            if invoice.l10n_do_origin_ncf:
                credit_origin_id = invoice.search(
                    [("l10n_latam_document_number", "=", invoice.l10n_do_origin_ncf)], limit=1
                )
                # Solo calcular IndicadorNotaCredito si se encontró la factura de origen
                if credit_origin_id and credit_origin_id.invoice_date:
                    delta = abs(invoice.invoice_date - credit_origin_id.invoice_date)
                    id_doc_data["IndicadorNotaCredito"] = int(delta.days > 30)
                else:
                    # Si no se encuentra la factura, asumir que es <= 30 días (IndicadorNotaCredito = 0)
                    _logger.warning(f"No se encontró la factura de origen '{invoice.l10n_do_origin_ncf}' para la nota de crédito {invoice.name}")
                    id_doc_data["IndicadorNotaCredito"] = 0
            else:
                # Si no hay NCF de origen, asumir que es <= 30 días (IndicadorNotaCredito = 0)
                _logger.warning(f"Nota de crédito {invoice.name} no tiene NCF de origen (l10n_do_origin_ncf vacío)")
                id_doc_data["IndicadorNotaCredito"] = 0

        if invoice.company_id.l10n_do_ecf_deferred_submissions:
            id_doc_data["IndicadorEnvioDiferido"] = 1

        if l10n_do_ncf_type not in ("43", "44", "46", "47") and not is_resumen:
            if "IndicadorMontoGravado" not in id_doc_data:
                id_doc_data["IndicadorMontoGravado"] = None
            
            id_doc_data["IndicadorMontoGravado"] = 1 if any(
                t.price_include
                for t in invoice.invoice_line_ids.tax_ids
                if t.tax_group_id.id == itbis_group.id
            ) else 0
            # id_doc_data["IndicadorMontoGravado"] = int(
            #     any(
            #         True
            #         for t iexit()n invoice.invoice_line_ids.tax_ids.filtered(
            #             lambda tax: tax.tax_group_id.id == itbis_group.id
            #         )
            #         if t.price_include
            #     )
            # )

        if l10n_do_ncf_type not in ("41", "43", "47"):
            # Solo incluir TipoIngresos si tiene un valor válido (no False/None)
            # Esto evita enviar '0' que es rechazado por DGII
            if invoice.l10n_do_income_type:
                id_doc_data["TipoIngresos"] = invoice.l10n_do_income_type
            else:
                # Si no hay tipo de ingreso válido, usar '01' (Ingresos Operacionales) por defecto
                # para facturas de venta que requieren este campo
                if invoice.move_type in ('out_invoice', 'out_refund'):
                    id_doc_data["TipoIngresos"] = '01'
                    _logger.warning(f"⚠️ Factura {invoice.name}: TipoIngresos no definido, usando '01' por defecto")
                # Para otros tipos (notas de crédito/débito sin tipo), no incluir el campo
                elif "TipoIngresos" in id_doc_data:
                    del id_doc_data["TipoIngresos"]

        id_doc_data["TipoPago"] = self.get_payment_type(invoice)

        if (
            invoice.invoice_date_due
            and id_doc_data["TipoPago"] == 2
            and l10n_do_ncf_type != "43"
        ):
            id_doc_data["FechaLimitePago"] = dt.strftime(
                invoice.invoice_date_due, "%d-%m-%Y"
            )

            if l10n_do_ncf_type not in ("34", "43"):
                delta = invoice.invoice_date_due - invoice.invoice_date
                id_doc_data["TerminoPago"] = "%s días" % delta.days

        if invoice.payment_state != "not_paid" and l10n_do_ncf_type not in (
            "34",
            "43",
        ):
            id_doc_data["TablaFormasPago"] = {
                "FormaDePago": self.get_payment_forms(invoice)}
            
        if is_resumen:
            if "FechaVencimientoSecuencia" in id_doc_data:
                del id_doc_data["FechaVencimientoSecuencia"]
            if "IndicadorNotaCredito" in id_doc_data:
                del id_doc_data["IndicadorNotaCredito"]
            if "IndicadorEnvioDiferido" in id_doc_data:
                del id_doc_data["IndicadorEnvioDiferido"]
            # Note: IndicadorMontoGravado is MANDATORY for type 32 even in summary format
            # Do NOT remove IndicadorMontoGravado for type 32 invoices
            if "FechaLimitePago" in id_doc_data:
                del id_doc_data["FechaLimitePago"]
            if "TerminoPago" in id_doc_data:
                del id_doc_data["TerminoPago"]
            # TablaFormasPago may be needed in some cases for summary invoices
            # Do NOT remove it unconditionally

        if invoice.company_id.l10n_do_ecf_environment in ['pre_certification', 'certification']:
            pass  # CAMPOS ESPECIALES DESHABILITADOS
            # CAMPOS ESPECIALES DESHABILITADOS - for custom_line in invoice.l10n_do_custom_fields_ids:
                # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.section == 'IdDoc' and custom_line.name:
                    # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.delete:
                        # CAMPOS ESPECIALES DESHABILITADOS - id_doc_data.pop(custom_line.name, None)
                        # CAMPOS ESPECIALES DESHABILITADOS - continue

                    # CAMPOS ESPECIALES DESHABILITADOS - # Para resúmenes, no permitir agregar campos que deberían estar excluidos
                    # CAMPOS ESPECIALES DESHABILITADOS - if is_resumen and custom_line.name in [
                        # CAMPOS ESPECIALES DESHABILITADOS - 'FechaVencimientoSecuencia', 'IndicadorNotaCredito',
                        # CAMPOS ESPECIALES DESHABILITADOS - 'IndicadorEnvioDiferido', 'FechaLimitePago', 'TerminoPago'
                    # CAMPOS ESPECIALES DESHABILITADOS - ]:
                        # CAMPOS ESPECIALES DESHABILITADOS - continue

                    # CAMPOS ESPECIALES DESHABILITADOS - id_doc_data[custom_line.name] = custom_line.value if custom_line.value else ''

        return self.reorder_dict(id_doc_data, idDoc_order)


    def _get_location_codes(self, state_code, city_name):
        """Mapea códigos de estado y ciudades de Odoo a códigos oficiales DGII"""
        # Mapeo de provincias (códigos de estado Odoo -> códigos DGII)
        provincia_codes = {
            'DN': '010000',  # Distrito Nacional
            'SD': '010000',  # Santo Domingo (alias para DN)
            'AZUA': '020000',     # Azua
            'BAORUCO': '030000',  # Baoruco
            'BARAHONA': '040000', # Barahona
            'DAJABON': '050000',  # Dajabón
            'DUARTE': '060000',   # Duarte
            'ELIAS_PINA': '070000', # Elías Piña
            'EL_SEIBO': '080000',   # El Seibo
            'ESPAILLAT': '090000',  # Espaillat
            'HATO_MAYOR': '100000', # Hato Mayor
            'HERMANAS_MIRABAL': '110000', # Hermanas Mirabal
            'INDEPENDENCIA': '120000', # Independencia
            'LA_ALTAGRACIA': '130000', # La Altagracia
            'LA_ROMANA': '140000',     # La Romana
            'LA_VEGA': '150000',       # La Vega
            'MARIA_TRINIDAD_SANCHEZ': '160000', # María Trinidad Sánchez
            'MONSENOR_NOUEL': '170000',   # Monseñor Nouel
            'MONTE_CRISTI': '180000',     # Monte Cristi
            'MONTE_PLATA': '190000',      # Monte Plata
            'PEDERNALES': '200000',       # Pedernales
            'PERAVIA': '210000',          # Peravia
            'PUERTO_PLATA': '220000',     # Puerto Plata
            'SAMANA': '230000',           # Samaná
            'SAN_CRISTOBAL': '240000',    # San Cristóbal
            'SAN_JOSE_DE_OCOA': '250000', # San José de Ocoa
            'SAN_JUAN': '260000',         # San Juan
            'SAN_PEDRO_DE_MACORIS': '270000', # San Pedro de Macorís
            'SANCHEZ_RAMIREZ': '280000',  # Sánchez Ramírez
            'SANTIAGO': '290000',         # Santiago
            'SANTIAGO_RODRIGUEZ': '300000', # Santiago Rodríguez
            'VALVERDE': '310000',         # Valverde
        }
        
        # Mapeo de municipios principales (Santo Domingo)
        municipio_codes = {
            'Santo Domingo': '010101',  # Santo Domingo de Guzmán (D.M.)
            'santo domingo': '010101',
            'SANTO DOMINGO': '010101',
            'Distrito Nacional': '010101',
            'distrito nacional': '010101',
        }
        
        provincia_code = provincia_codes.get(state_code, '010000')  # Default: Distrito Nacional
        municipio_code = municipio_codes.get(city_name, '010101')   # Default: Santo Domingo
        
        return provincia_code, municipio_code

    def _get_Emisor_data(self, invoice, is_resumen):
        """Issuer (company) values"""

        emisor_order = [
            "RNCEmisor",
            "RazonSocialEmisor",
            "NombreComercial",
            "Sucursal",
            "DireccionEmisor",
            "Municipio",
            "Provincia",
            "TablaTelefonoEmisor",
            "CorreoEmisor",
            "WebSite",
            "ActividadEconomica",
            "CodigoVendedor",
            "NumeroFacturaInterna",
            "NumeroPedidoInterno",
            "ZonaVenta",
            "RutaVenta",
            "InformacionAdicionalEmisor",
            "FechaEmision",
        ]

        issuer_data = od(
            {
                "RNCEmisor": invoice.company_id.vat,
                "RazonSocialEmisor": invoice.company_id.name,
                "NombreComercial": invoice.company_id.name,
            }
        )
        if invoice.company_id.street:
            issuer_data["DireccionEmisor"] = invoice.company_id.street
        
        # Obtener códigos oficiales de DGII para ubicación
        state_code = invoice.company_id.state_id.code if invoice.company_id.state_id else 'DN'
        city_name = invoice.company_id.city if invoice.company_id.city else 'Santo Domingo'
        provincia_code, municipio_code = self._get_location_codes(state_code, city_name)
        
        issuer_data["Municipio"] = municipio_code
        issuer_data["Provincia"] = provincia_code
        if invoice.company_id.email:
            issuer_data["CorreoEmisor"] = invoice.company_id.email
        if invoice.company_id.website:
            issuer_data["WebSite"] = re.sub(r'^https?://', '', invoice.company_id.website).rstrip('/').split('/')[0]            
        if invoice.invoice_user_id:
            if invoice.invoice_user_id.partner_id.ref:
                issuer_data["CodigoVendedor"] = invoice.invoice_user_id.partner_id.ref
        if invoice.name:
            issuer_data["NumeroFacturaInterna"] = invoice.name
        issuer_data["FechaEmision"] = dt.strftime(invoice.invoice_date, "%d-%m-%Y")

        if not invoice.company_id.street or not len(str(invoice.company_id.street).strip()):
            action = self.env.ref("base.action_res_company_form")
            msg = _("Cannot send an ECF if company has no address.")
            raise RedirectWarning(msg, action.id, _("Go to Companies"))
        
        if is_resumen:
            if "FechaVencimientoSecuencia" in issuer_data:
                del issuer_data["FechaVencimientoSecuencia"]
            if "NombreComercial" in issuer_data:
                del issuer_data["NombreComercial"]
            if "Sucursal" in issuer_data:
                del issuer_data["Sucursal"]
            if "DireccionEmisor" in issuer_data:
                del issuer_data["DireccionEmisor"]
            if "Municipio" in issuer_data:
                del issuer_data["Municipio"]
            if "Provincia" in issuer_data:
                del issuer_data["Provincia"]
            if "TablaTelefonoEmisor" in issuer_data:
                del issuer_data["TablaTelefonoEmisor"]
            if "CorreoEmisor" in issuer_data:
                del issuer_data["CorreoEmisor"]
            if "WebSite" in issuer_data:
                del issuer_data["WebSite"]
            if "ActividadEconomica" in issuer_data:
                del issuer_data["ActividadEconomica"]
            if "CodigoVendedor" in issuer_data:
                del issuer_data["CodigoVendedor"]
            if "NumeroFacturaInterna" in issuer_data:
                del issuer_data["NumeroFacturaInterna"]
            if "NumeroPedidoInterno" in issuer_data:
                del issuer_data["NumeroPedidoInterno"]
            if "ZonaVenta" in issuer_data:
                del issuer_data["ZonaVenta"]
            if "RutaVenta" in issuer_data:
                del issuer_data["RutaVenta"]
            if "InformacionAdicionalEmisor" in issuer_data:
                del issuer_data["InformacionAdicionalEmisor"]

        if invoice.company_id.l10n_do_ecf_environment in ['pre_certification', 'certification']:
            pass  # CAMPOS ESPECIALES DESHABILITADOS
            # CAMPOS ESPECIALES DESHABILITADOS - for custom_line in invoice.l10n_do_custom_fields_ids:
                # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.section == 'Emisor' and custom_line.name:
                    # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.delete:
                        # CAMPOS ESPECIALES DESHABILITADOS - issuer_data.pop(custom_line.name, None)
                        # CAMPOS ESPECIALES DESHABILITADOS - continue

                    # CAMPOS ESPECIALES DESHABILITADOS - # Para resúmenes, no permitir agregar campos que deberían estar excluidos
                    # CAMPOS ESPECIALES DESHABILITADOS - if is_resumen and custom_line.name in [
                        # CAMPOS ESPECIALES DESHABILITADOS - 'FechaVencimientoSecuencia', 'NombreComercial', 'Sucursal', 'DireccionEmisor', 'Municipio',
                        # CAMPOS ESPECIALES DESHABILITADOS - 'Provincia', 'TablaTelefonoEmisor', 'CorreoEmisor', 'WebSite',
                        # CAMPOS ESPECIALES DESHABILITADOS - 'ActividadEconomica', 'CodigoVendedor', 'NumeroFacturaInterna',
                        # CAMPOS ESPECIALES DESHABILITADOS - 'NumeroPedidoInterno', 'ZonaVenta', 'RutaVenta', 'InformacionAdicionalEmisor'
                    # CAMPOS ESPECIALES DESHABILITADOS - ]:
                        # CAMPOS ESPECIALES DESHABILITADOS - continue

                    # CAMPOS ESPECIALES DESHABILITADOS - issuer_data[custom_line.name] = custom_line.value if custom_line.value else ''

        return self.reorder_dict(issuer_data, emisor_order)
        

    def _get_Comprador_data(self, invoice, is_resumen):
        """Buyer (invoice partner) values """

        comprador_order = [
            "RNCComprador",
            "IdentificadorExtranjero",
            "RazonSocialComprador",
            "ContactoComprador",
            "CorreoComprador",
            "DireccionComprador",
            "MunicipioComprador",
            "ProvinciaComprador",
            "PaisComprador",
            "FechaEntrega",
            "ContactoEntrega",
            "DireccionEntrega",
            "TelefonoAdicional",
            "FechaOrdenCompra",
            "NumeroOrdenCompra",
            "CodigoInternoComprador",
            "ResponsablePago",
            "InformacionAdicionalComprador",
        ]

        l10n_do_ncf_type = self.get_l10n_do_ncf_type(invoice)
        partner_vat = invoice.partner_id.vat or ""
        is_l10n_do_partner = self.is_l10n_do_partner(invoice)
        
        # VALIDACIÓN Y FORMATO CORRECTO DE RNCComprador para DGII XML
        def format_rnc_comprador(vat):
            """Formatea correctamente RNC/Cédula para XML DGII - SOLO NÚMEROS SIN GUIONES"""
            if not vat:
                return ""
            
            # Remover guiones y espacios - DGII requiere solo números
            clean_vat = vat.replace("-", "").replace(" ", "").strip()
            
            # VALIDACIÓN ESTRICTA BASADA EN EJEMPLOS DGII OFICIALES
            # RNC: exactamente 9 dígitos numéricos (TODOS los ejemplos oficiales usan 9 dígitos)
            if len(clean_vat) == 9 and clean_vat.isdigit():
                _logger.info(f"✅ RNC válido para DGII E41: '{clean_vat}' (9 dígitos)")
                return clean_vat
            
            # ADVERTENCIA: Cédula 11 dígitos - no encontrada en ejemplos oficiales E41
            elif len(clean_vat) == 11 and clean_vat.isdigit():
                # Para E41, DGII podría requerir solo RNC (9 dígitos), no cédulas (11 dígitos)
                _logger.warning(f"⚠️ CÉDULA 11 dígitos para E41: '{clean_vat}' - DGII podría rechazar")
                _logger.warning(f"⚠️ SUGERENCIA: Verificar si partner debe tener RNC de 9 dígitos para E41")
                return clean_vat
            
            # Formato inválido - reportar error detallado
            _logger.error(f"🚨 RNCComprador INVÁLIDO para DGII: '{vat}' → '{clean_vat}' (len: {len(clean_vat)}, digits: {clean_vat.isdigit()})")
            return clean_vat

        buyer_data = od({})
        if l10n_do_ncf_type not in ("43", "47"):

            if l10n_do_ncf_type in ("31", "41", "45"):
                formatted_vat = format_rnc_comprador(partner_vat)
                buyer_data["RNCComprador"] = formatted_vat
                _logger.info(f"🔧 RNCComprador E41 formateado: '{partner_vat}' → '{formatted_vat}'")

            if l10n_do_ncf_type == "32" and partner_vat:
                buyer_data["RNCComprador"] = format_rnc_comprador(partner_vat)

            if l10n_do_ncf_type in ("46"):
                if not is_l10n_do_partner:
                    buyer_data["IdentificadorExtranjero"] = partner_vat
                else:
                    buyer_data["RNCComprador"] = format_rnc_comprador(partner_vat)

            if l10n_do_ncf_type in ("33", "34"):
                if (
                    invoice.debit_origin_id
                    #and invoice.debit_origin_id.get_l10n_do_ncf_type != "32"
                    and self.get_l10n_do_ncf_type(invoice.debit_origin_id) != "32"
                    or (
                        #invoice.debit_origin_id.get_l10n_do_ncf_type == "32"
                        self.get_l10n_do_ncf_type(invoice.debit_origin_id) == "32"
                        and invoice.debit_origin_id.amount_total_signed >= RESUMEN_AMOUNT_LIMIT
                    )
                    or invoice.move_type in ("out_refund", "in_refund")
                ):
                    if is_l10n_do_partner and partner_vat:
                        buyer_data["RNCComprador"] = format_rnc_comprador(partner_vat)
                    elif partner_vat:
                        buyer_data["IdentificadorExtranjero"] = partner_vat

            if l10n_do_ncf_type == "44":
                if is_l10n_do_partner and partner_vat:
                    buyer_data["RNCComprador"] = format_rnc_comprador(partner_vat)
                elif not is_l10n_do_partner and partner_vat:
                    buyer_data["IdentificadorExtranjero"] = partner_vat

            if invoice.company_id.partner_id.l10n_do_dgii_tax_payer_type == "special":
                if is_l10n_do_partner:
                    buyer_data["RNCComprador"] = format_rnc_comprador(partner_vat)
                else:
                    buyer_data["IdentificadorExtranjero"] = partner_vat

        if l10n_do_ncf_type not in ("31", "41", "43", "45") and not is_l10n_do_partner:

            if l10n_do_ncf_type == "32" and invoice.amount_total_signed >= RESUMEN_AMOUNT_LIMIT:
                buyer_data["IdentificadorExtranjero"] = partner_vat

        if l10n_do_ncf_type not in ("43", "47"):

            # TODO: are those If really needed?
            if l10n_do_ncf_type == "32":
                if invoice.amount_total_signed >= RESUMEN_AMOUNT_LIMIT or partner_vat:
                    buyer_data["RazonSocialComprador"] = invoice.commercial_partner_id.name

            if l10n_do_ncf_type in ("33", "34"):
                buyer_data["RazonSocialComprador"] = invoice.commercial_partner_id.name

            else:  # 31, 41, 44, 45, 46
                buyer_data["RazonSocialComprador"] = invoice.commercial_partner_id.name
            
            for child_id in invoice.commercial_partner_id.child_ids:
                if child_id.type == 'contact':
                    buyer_data["ContactoComprador"] = child_id.name
                    break
            if invoice.commercial_partner_id.email:
                buyer_data["CorreoComprador"] = invoice.commercial_partner_id.email
            if invoice.commercial_partner_id.street:
                buyer_data["DireccionComprador"] = invoice.commercial_partner_id.street
            
            # Obtener códigos oficiales de DGII para ubicación del comprador
            buyer_state_code = invoice.commercial_partner_id.state_id.code if invoice.commercial_partner_id.state_id else 'DN'
            buyer_city_name = invoice.commercial_partner_id.city if invoice.commercial_partner_id.city else 'Santo Domingo'
            buyer_provincia_code, buyer_municipio_code = self._get_location_codes(buyer_state_code, buyer_city_name)
            
            buyer_data["MunicipioComprador"] = buyer_municipio_code
            buyer_data["ProvinciaComprador"] = buyer_provincia_code

        if is_resumen:
            if "ContactoComprador" in buyer_data:
                del buyer_data["ContactoComprador"]
            if "CorreoComprador" in buyer_data:
                del buyer_data["CorreoComprador"]
            if "DireccionComprador" in buyer_data:
                del buyer_data["DireccionComprador"]
            if "MunicipioComprador" in buyer_data:
                del buyer_data["MunicipioComprador"]
            if "ProvinciaComprador" in buyer_data:
                del buyer_data["ProvinciaComprador"]
            if "PaisComprador" in buyer_data:
                del buyer_data["PaisComprador"]
            if "FechaEntrega" in buyer_data:
                del buyer_data["FechaEntrega"]
            if "ContactoEntrega" in buyer_data:
                del buyer_data["ContactoEntrega"]
            if "DireccionEntrega" in buyer_data:
                del buyer_data["DireccionEntrega"]
            if "TelefonoAdicional" in buyer_data:
                del buyer_data["TelefonoAdicional"]
            if "FechaOrdenCompra" in buyer_data:
                del buyer_data["FechaOrdenCompra"]
            if "NumeroOrdenCompra" in buyer_data:
                del buyer_data["NumeroOrdenCompra"]
            if "CodigoInternoComprador" in buyer_data:
                del buyer_data["CodigoInternoComprador"]
            if "ResponsablePago" in buyer_data:
                del buyer_data["ResponsablePago"]
            if "InformacionAdicionalComprador" in buyer_data:
                del buyer_data["InformacionAdicionalComprador"]

        if invoice.company_id.l10n_do_ecf_environment in ['pre_certification', 'certification']:
            pass  # CAMPOS ESPECIALES DESHABILITADOS
            # CAMPOS ESPECIALES DESHABILITADOS - for custom_line in invoice.l10n_do_custom_fields_ids:
                # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.section == 'Comprador' and custom_line.name:
                    # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.delete:
                        # CAMPOS ESPECIALES DESHABILITADOS - buyer_data.pop(custom_line.name, None)
                        # CAMPOS ESPECIALES DESHABILITADOS - continue

                    # CAMPOS ESPECIALES DESHABILITADOS - # Para resúmenes, no permitir agregar campos que deberían estar excluidos
                    # CAMPOS ESPECIALES DESHABILITADOS - if is_resumen and custom_line.name in [
                        # CAMPOS ESPECIALES DESHABILITADOS - 'ContactoComprador', 'CorreoComprador', 'DireccionComprador',
                        # CAMPOS ESPECIALES DESHABILITADOS - 'MunicipioComprador', 'ProvinciaComprador', 'PaisComprador',
                        # CAMPOS ESPECIALES DESHABILITADOS - 'FechaEntrega', 'ContactoEntrega', 'DireccionEntrega',
                        # CAMPOS ESPECIALES DESHABILITADOS - 'TelefonoAdicional', 'FechaOrdenCompra', 'NumeroOrdenCompra',
                        # CAMPOS ESPECIALES DESHABILITADOS - 'CodigoInternoComprador', 'ResponsablePago', 'InformacionAdicionalComprador'
                    # CAMPOS ESPECIALES DESHABILITADOS - ]:
                        # CAMPOS ESPECIALES DESHABILITADOS - continue

                    # CAMPOS ESPECIALES DESHABILITADOS - buyer_data[custom_line.name] = custom_line.value if custom_line.value else ''

        return self.reorder_dict(buyer_data, comprador_order)


    def get_taxed_amount_data(self, invoice):
        """ITBIS taxed amount
        According to the DGII, there are three types of
        amounts taxed by ITBIS:

        18% -- Most common
        16% -- Used on 'healthy products' like Yogurt, coffee and so on.
        0% -- Should be used on exported products

        See Law No. 253-12, art. 343 of dominican Tributary Code for further info
        """

        itbis_data = {
            "total_taxed_amount": 0,
            "18_taxed_base": 0,
            "18_taxed_amount": 0,
            "18_taxed": False,
            "16_taxed_base": 0,
            "16_taxed_amount": 0,
            "16_taxed": False,
            "0_taxed_base": 0,
            "0_taxed_amount": 0,
            "0_taxed": False,
            "other_base": 0,
            "other_amount": 0,
            "other": False,
            "exempt_amount": 0,
            "itbis_withholding_amount": 0,
            "isr_withholding_amount": 0,
        }

        # ✅ CORRECCIÓN DEFINITIVA: Detectar precio correcto según tipo NCF
        l10n_do_ncf_type = self.get_l10n_do_ncf_type(invoice)
        
        if l10n_do_ncf_type == "41":
            # E41: Usar price_unit con quantity (impuestos NO incluidos)
            tax_data = [
                line.tax_ids.compute_all(
                    # MODIFICADO: Arturo Diaz Lora - 2026-03-10 23:00
                    # Razón: Aplicar descuento al price_unit antes de compute_all para que
                    # ITBIS se calcule sobre precio neto (Art. 343 Código Tributario RD)
                    # Código original: price_unit=line.price_unit,
                    price_unit=line.price_unit * (1 - (line.discount or 0.0) / 100.0),
                    currency=line.currency_id,
                    quantity=line.quantity,
                    product=line.product_id,
                    partner=line.move_id.partner_id,
                    handle_price_include=False,
                )
                for line in invoice.invoice_line_ids.filtered(lambda l: l.display_type == 'product' and l.quantity and l.price_unit)
            ]
        else:
            # E31-E34: Usar price_unit/quantity y dejar que compute_all maneje price_include
            # IMPORTANTE: NO usar price_subtotal, usar price_unit para impuestos incluidos
            tax_data = [
                line.tax_ids.compute_all(
                    # MODIFICADO: Arturo Diaz Lora - 2026-03-10 23:00
                    # Razón: Aplicar descuento al price_unit antes de compute_all para que
                    # ITBIS se calcule sobre precio neto (Art. 343 Código Tributario RD)
                    # Código original: price_unit=line.price_unit,
                    price_unit=line.price_unit * (1 - (line.discount or 0.0) / 100.0),
                    currency=line.currency_id,
                    quantity=line.quantity,      # Necesario para cálculo correcto
                    product=line.product_id,
                    partner=line.move_id.partner_id,
                    # NO especificar handle_price_include - dejar que use el default
                )
                for line in invoice.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
            ]

        itbis_data["total_taxed_amount"] = sum(
            line["total_excluded"] for line in tax_data
        )
        l10n_do_ncf_type = self.get_l10n_do_ncf_type(invoice)

        for line_taxes in tax_data:
            for tax in line_taxes["taxes"]:
                tax_id = self.env["account.tax"].browse(tax["id"])
                
                # ✅ CORRECCIÓN: Detectar impuestos exentos por amount=0 independiente del grupo
                if not tax["amount"]:
                    # Si el impuesto es 0%, considerarlo exento
                    itbis_data["exempt_amount"] += tax["base"]

                if tax_id.amount == 18:
                    itbis_data["18_taxed_base"] += tax["base"]
                    itbis_data["18_taxed_amount"] += tax["amount"]
                    itbis_data["18_taxed"] = True
                elif tax_id.amount == 16:
                    itbis_data["16_taxed_base"] += tax["base"]
                    itbis_data["16_taxed_amount"] += tax["amount"]
                    itbis_data["16_taxed"] = True
                elif tax_id.amount == 0 and tax_id.tax_group_id == self._get_tax_group_safe("l10n_do_edi.tax_group_itbis", "ITBIS"):
                    itbis_data["0_taxed_base"] += tax["base"]
                    itbis_data["0_taxed_amount"] += tax["amount"]
                    itbis_data["0_taxed"] = True
                elif tax_id.amount < 0 and tax_id.tax_group_id == self._get_tax_group_safe("l10n_do_edi.tax_group_itbis", "ITBIS"):
                    itbis_data["itbis_withholding_amount"] += tax["amount"]
                elif tax_id.amount < 0 and tax_id.tax_group_id == self._get_tax_group_safe("l10n_do_edi.tax_group_isr", "ISR"):
                    itbis_data["isr_withholding_amount"] += tax["amount"]       
                elif tax_id.tax_group_id == self._get_tax_group_safe("l10n_do_edi.tax_group_other_tax", "Otros Impuestos"):
                    itbis_data["other_base"] += tax["base"]
                    itbis_data["other_amount"] += tax["amount"]
                    itbis_data["other"] = True
        return itbis_data        


    def _get_Totales_data(self, invoice, is_resumen):
        """Invoice amounts related values"""
        self.ensure_one()

        totales_order = [
            "MontoGravadoTotal",
            "MontoGravadoI1",
            "MontoGravadoI2",
            "MontoGravadoI3",
            "MontoExento",
            "ITBIS1",
            "ITBIS2",
            "ITBIS3",
            "TotalITBIS",
            "TotalITBIS1",
            "TotalITBIS2",
            "TotalITBIS3",
            "MontoImpuestoAdicional",
            "ImpuestosAdicionales",
            "TipoImpuesto",
            "TasaImpuestoAdicional",
            "MontoTotal",
            "MontoPeriodo",
            "ValorPagar",
        ]

        totals_data = od({})
        tax_data = self.get_taxed_amount_data(invoice)
        l10n_do_ncf_type = self.get_l10n_do_ncf_type(invoice)
        is_company_currency = self.is_company_currency(invoice)

        total_taxed = sum(
            [
                tax_data["18_taxed_base"],
                tax_data["16_taxed_base"],
                tax_data["0_taxed_base"],
            ]
        )
        total_itbis = sum(
            [
                tax_data["18_taxed_amount"],
                tax_data["16_taxed_amount"],
                tax_data["0_taxed_amount"],
            ]
        )

        total_exent = abs(
            round(tax_data["exempt_amount"], 2)) if tax_data["exempt_amount"] else 0

        if l10n_do_ncf_type not in ("43", "44"):
            # ✅ REGLA ESPECIAL E46: Forzar MontoGravadoTotal y MontoGravadoI3 con monto total
            if l10n_do_ncf_type == "46":
                monto_total_sin_impuestos = abs(round(invoice.amount_untaxed, 2))
                totals_data["MontoGravadoTotal"] = monto_total_sin_impuestos
                totals_data["MontoGravadoI3"] = monto_total_sin_impuestos
                # ✅ E46 SIEMPRE: ITBIS3 = 0, TotalITBIS = 0, TotalITBIS3 = 0 (obligatorios según XML aceptados)
                totals_data["ITBIS3"] = 0
                totals_data["TotalITBIS"] = 0.00
                totals_data["TotalITBIS3"] = 0.00
                _logger.debug(f"E46 - Forzando MontoGravadoTotal={monto_total_sin_impuestos}, MontoGravadoI3={monto_total_sin_impuestos}, ITBIS3=0, TotalITBIS=0.00, TotalITBIS3=0.00")
            else:
                if tax_data["18_taxed"] or tax_data["16_taxed"] or tax_data["0_taxed"]:
                    totals_data["MontoGravadoTotal"] = abs(round(total_taxed, 2))
                if tax_data["18_taxed"]:
                    totals_data["MontoGravadoI1"] = abs(round(tax_data["18_taxed_base"], 2))
                if tax_data["16_taxed"]:
                    totals_data["MontoGravadoI2"] = abs(round(tax_data["16_taxed_base"], 2))
                if tax_data["0_taxed"]:
                    totals_data["MontoGravadoI3"] = abs(round(tax_data["0_taxed_base"], 2))
            # OBLIGATORIO: MontoExento siempre debe aparecer para E41 (Compras Electrónica)
            # EXCLUIR E46: Exportaciones no permite MontoExento según XSD
            if (total_exent or l10n_do_ncf_type in ("34", "41")) and l10n_do_ncf_type != "46":
                totals_data["MontoExento"] = abs(round(total_exent, 2))
            # ✅ ITBIS1/ITBIS2/ITBIS3 - Excluir E46 porque ya se fuerza arriba
            if l10n_do_ncf_type != "46":
                if tax_data["18_taxed"]:
                    totals_data["ITBIS1"] = 18
                if tax_data["16_taxed"]:
                    totals_data["ITBIS2"] = 16
                if tax_data["0_taxed"]:
                    totals_data["ITBIS3"] = 0
            # ✅ TotalITBIS - Excluir E46 porque ya se fuerza arriba
            if l10n_do_ncf_type != "46":
                if tax_data["18_taxed"] or tax_data["16_taxed"] or tax_data["0_taxed"]:
                    totals_data["TotalITBIS"] = abs(round(total_itbis, 2))
                if tax_data["18_taxed"]:
                    totals_data["TotalITBIS1"] = abs(round(tax_data["18_taxed_amount"], 2))
                if tax_data["16_taxed"]:
                    totals_data["TotalITBIS2"] = abs(round(tax_data["16_taxed_amount"], 2))
                if tax_data["0_taxed"]:
                    totals_data["TotalITBIS3"] = abs(round(tax_data["0_taxed_amount"], 2))
            if tax_data["other"]:
                totals_data["MontoImpuestoAdicional"] = abs(round(tax_data["other_amount"], 2))
        else:
            # ✅ CORRECCIÓN: Para E43/E44 siempre incluir MontoExento si hay monto exento O si no hay impuestos
            if total_exent or (l10n_do_ncf_type in ("43", "44") and not any([tax_data["18_taxed"], tax_data["16_taxed"], tax_data["0_taxed"]])):
                # Si hay monto exento O si es E43/E44 sin impuestos gravados
                # CORREGIDO: tax_data es un dict, no una lista - usar amount_untaxed de la factura
                exento_amount = total_exent if total_exent else abs(invoice.amount_untaxed)
                totals_data["MontoExento"] = abs(round(exento_amount, 2))

        if l10n_do_ncf_type not in ("43", "44") and total_taxed:
            #totals_data["MontoTotal"] = abs(round(total_taxed + total_itbis, 2)) + total_exent
            # ESPECIAL E41: MontoTotal = base gravada + ITBIS BRUTO (antes de retenciones)
            if l10n_do_ncf_type == "41":
                monto_total = total_taxed + total_itbis
                _logger.info(f"🔥 E41 MontoTotal CORREGIDO - Base: {total_taxed} + ITBIS: {total_itbis} = {monto_total}")
            else:
                monto_total = invoice.amount_total
        else:
            monto_total = invoice.amount_untaxed

        if l10n_do_ncf_type not in ("43", "44"):
            # CORRECCIÓN ESPECIAL PARA E41: Calcular retención ITBIS directamente
            if l10n_do_ncf_type == "41":
                # Para E41, calcular retención basada en la base gravable y tasa 18%
                retencion_itbis = 0
                if tax_data["18_taxed_base"]:
                    retencion_itbis = tax_data["18_taxed_base"] * 0.18
                    _logger.info(f"💰 E41 RETENCIÓN - Base gravable: {tax_data['18_taxed_base']}, Retención calculada: {retencion_itbis}")
                    totals_data["TotalITBISRetenido"] = abs(round(retencion_itbis, 2))
                elif tax_data["itbis_withholding_amount"]:
                    retencion_itbis = abs(tax_data["itbis_withholding_amount"])
                    _logger.info(f"💰 E41 RETENCIÓN - Usando withholding_amount: {retencion_itbis}")
                    totals_data["TotalITBISRetenido"] = abs(round(retencion_itbis, 2))
                    
                # CORREGIDO E41: NO sumar retención al MontoTotal
                # Para E41, MontoTotal debe ser el monto base sin retenciones
                # La retención se reporta separadamente en TotalITBISRetenido
                _logger.info(f"💰 E41 MONTO - NO sumando retención {retencion_itbis} al MontoTotal {monto_total}")
            elif tax_data["itbis_withholding_amount"] and l10n_do_ncf_type in ("41"):
                totals_data["TotalITBISRetenido"] = abs(round(tax_data["itbis_withholding_amount"], 2)) 
                # CORREGIDO E41: NO sumar retención al MontoTotal
                _logger.info(f"💰 E41 MONTO - NO sumando withholding_amount al MontoTotal")

            # ✅ CORRECCIÓN E47: TotalISRRetencion es OBLIGATORIO cuando hay Retencion en líneas
            # Para E41 y E47, siempre incluir TotalISRRetencion (puede ser 0.00)
            if l10n_do_ncf_type in ("41", "47"):
                totals_data["TotalISRRetencion"] = abs(round(tax_data["isr_withholding_amount"], 2))
                # CORREGIDO E41: NO sumar retención ISR al MontoTotal
                _logger.info(f"💰 E41/E47 - TotalISRRetencion: {totals_data['TotalISRRetencion']} - NO sumando al MontoTotal")

        totals_data["MontoTotal"] = abs(round(monto_total, 2)) 

        if not is_company_currency:
            rate = abs(
                round(1 / (invoice.amount_total / invoice.amount_total_signed), 2))

            totals_data = od(
                {
                    f: round(v * rate, 2) if not isinstance(v,
                                                            str) and f not in ('ITBIS1', 'ITBIS2', 'ITBIS3') else v
                    for f, v in totals_data.items()
                }
            )
######
        #self.l10n_ecf_total_invoice = totals_data["MontoTotal"]
        #self.l10n_ecf_total_itbis = totals_data["TotalITBIS"] if "TotalITBIS" in totals_data else 0

        if is_resumen:
            if "ITBIS1" in totals_data:
                del totals_data["ITBIS1"]
            if "ITBIS2" in totals_data:
                del totals_data["ITBIS2"]
            if "ITBIS3" in totals_data:
                del totals_data["ITBIS3"]
            if "MontoImpuestoAdicional" in totals_data:
                del totals_data["MontoImpuestoAdicional"]
            if "ImpuestosAdicionales" in totals_data:
                del totals_data["ImpuestosAdicionales"]
            if "TipoImpuesto" in totals_data:
                del totals_data["TipoImpuesto"]
            if "TasaImpuestoAdicional" in totals_data:
                del totals_data["TasaImpuestoAdicional"]
            if "ValorPagar" in totals_data:
                del totals_data["ValorPagar"]

        if invoice.company_id.l10n_do_ecf_environment in ['pre_certification', 'certification']:
            pass  # CAMPOS ESPECIALES DESHABILITADOS
            # CAMPOS ESPECIALES DESHABILITADOS - for custom_line in invoice.l10n_do_custom_fields_ids:
                # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.section == 'Totales' and custom_line.name:
                    # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.delete:
                        # CAMPOS ESPECIALES DESHABILITADOS - totals_data.pop(custom_line.name, None)
                        # CAMPOS ESPECIALES DESHABILITADOS - continue

                    # CAMPOS ESPECIALES DESHABILITADOS - # Para resúmenes, no permitir agregar campos que deberían estar excluidos
                    # CAMPOS ESPECIALES DESHABILITADOS - if is_resumen and custom_line.name in [
                        # CAMPOS ESPECIALES DESHABILITADOS - 'ITBIS1', 'ITBIS2', 'ITBIS3', 'MontoImpuestoAdicional',
                        # CAMPOS ESPECIALES DESHABILITADOS - 'ImpuestosAdicionales', 'TipoImpuesto', 'TasaImpuestoAdicional', 'ValorPagar'
                    # CAMPOS ESPECIALES DESHABILITADOS - ]:
                        # CAMPOS ESPECIALES DESHABILITADOS - continue

                    # CAMPOS ESPECIALES DESHABILITADOS - totals_data[custom_line.name] = custom_line.value if custom_line.value else ''

        #return totals_data
        return self.reorder_dict(totals_data, totales_order)


    def _get_OtraMoneda_data(self, ecf_object_data, invoice):
        """Only used if invoice currency is not company currency"""
        l10n_do_ncf_type = self.get_l10n_do_ncf_type(invoice)
        currency_data = od({})

        currency_data["TipoMoneda"] = invoice.currency_id.name
        rate = abs(round(1 / (invoice.amount_total / invoice.amount_total_signed), 2))
        currency_data["TipoCambio"] = rate
        
        # Obtener type_tag dinámicamente (ECF o RFCE)
        type_tag = list(ecf_object_data.keys())[0]
        totales_data = ecf_object_data[type_tag]["Encabezado"]["Totales"]

        if l10n_do_ncf_type not in ("43", "44", "47"):

            if "MontoGravadoTotal" in totales_data:
                currency_data["MontoGravadoTotalOtraMoneda"] = round(
                    float(totales_data["MontoGravadoTotal"]) / rate, 2
                )

            if "MontoGravadoI1" in totales_data:
                currency_data["MontoGravado1OtraMoneda"] = round(
                    float(totales_data["MontoGravadoI1"]) / rate, 2
                )

            if "MontoGravadoI2" in totales_data:
                currency_data["MontoGravado2OtraMoneda"] = round(
                    float(totales_data["MontoGravadoI2"]) / rate, 2
                )

            if "MontoGravadoI3" in totales_data:
                currency_data["MontoGravado3OtraMoneda"] = round(
                    float(totales_data["MontoGravadoI3"]) / rate, 2
                )

        if "MontoExento" in totales_data and l10n_do_ncf_type != "46":
            currency_data["MontoExentoOtraMoneda"] = round(
                float(totales_data["MontoExento"]) / rate, 2
            )

        if "TotalITBIS" in totales_data:
            currency_data["TotalITBISOtraMoneda"] = round(
                float(totales_data["TotalITBIS"]) / rate, 2
            )
        if "TotalITBIS1" in totales_data:
            currency_data["TotalITBIS1OtraMoneda"] = round(
                float(totales_data["TotalITBIS1"]) / rate, 2
            )
        if "TotalITBIS2" in totales_data:
            currency_data["TotalITBIS2OtraMoneda"] = round(
                float(totales_data["TotalITBIS2"]) / rate, 2
            )
        if "TotalITBIS3" in totales_data:
            currency_data["TotalITBIS3OtraMoneda"] = round(
                float(totales_data["TotalITBIS3"]) / rate, 2
            )

        # Autor: Arturo Diaz Lora
        # Fecha: 2025-11-25 22:45
        # Razón: Corregir compatibilidad con Odoo 18 - exclude_from_invoice_tab ya no existe
        # En Odoo 18, las líneas de balance (impuestos, receivable) no tienen display_type='product'
        # Filtramos líneas que NO son de producto (line_section, line_note tampoco)
        currency_data["MontoTotalOtraMoneda"] = abs(
            sum(
                invoice.line_ids.filtered(
                    lambda aml: aml.display_type not in ('product', 'line_section', 'line_note')
                ).mapped("amount_currency")
            )
        )

        return currency_data


    def _get_item_withholding_vals(self, invoice_line, line_withholding_vals):
        """ Returns invoice line withholding taxes values """

        # line_withholding_vals = invoice_line.tax_ids.compute_all(
        #     price_unit=invoice_line.price_unit,
        #     currency=invoice_line.currency_id,
        #     quantity=invoice_line.quantity,
        #     product=invoice_line.product_id,
        #     partner=invoice_line.move_id.partner_id,
        #     handle_price_include=False,
        #     is_refund=True if invoice_line.move_id.move_type == "in_refund" else False,
        # )
        l10n_do_ncf_type = self.get_l10n_do_ncf_type(invoice_line.move_id)
        
        _logger.info(f"📊 DEBUG WITHHOLDING - Línea {invoice_line.id}: {invoice_line.name}")
        _logger.info(f"📊 DEBUG WITHHOLDING - line_withholding_vals: {line_withholding_vals}")
        _logger.info(f"📊 DEBUG WITHHOLDING - Impuestos en line: {[(tax['id'], tax['amount']) for tax in line_withholding_vals.get('taxes', [])]}")
        
        withholding_vals = od()
        
        # Obtener grupo ITBIS
        itbis_group = self._get_tax_group_safe("l10n_do_edi.tax_group_itbis", "ITBIS")
        _logger.info(f"📊 DEBUG WITHHOLDING - Grupo ITBIS: {itbis_group}")
        
        itbis_withhold_amount = abs(
            sum(
                tax["amount"]
                for tax in line_withholding_vals["taxes"]
                if tax["amount"] < 0
                and self.env["account.tax"].browse(tax["id"]).tax_group_id == itbis_group
            )
        )
        _logger.info(f"📊 DEBUG WITHHOLDING - itbis_withhold_amount calculado: {itbis_withhold_amount}")
        # Obtener grupo ISR
        isr_group = self._get_tax_group_safe("l10n_do_edi.tax_group_isr", "ISR")
        _logger.info(f"📊 DEBUG WITHHOLDING - Grupo ISR: {isr_group}")
        
        isr_withhold_amount = abs(
            sum(
                tax["amount"]
                for tax in line_withholding_vals["taxes"]
                if tax["amount"] < 0
                and self.env["account.tax"].browse(tax["id"]).tax_group_id == isr_group
            )
        )
        _logger.info(f"📊 DEBUG WITHHOLDING - isr_withhold_amount calculado: {isr_withhold_amount}")
        
        if itbis_withhold_amount:
            withholding_vals["MontoITBISRetenido"] = itbis_withhold_amount
            _logger.info(f"📊 DEBUG WITHHOLDING - Añadido MontoITBISRetenido: {itbis_withhold_amount}")

        if isr_withhold_amount:
            withholding_vals["MontoISRRetenido"] = isr_withhold_amount
            _logger.info(f"📊 DEBUG WITHHOLDING - Añadido MontoISRRetenido: {isr_withhold_amount}")

        if l10n_do_ncf_type == "47" and itbis_withhold_amount <= 0 and "MontoITBISRetenido" in withholding_vals:
            del withholding_vals["MontoITBISRetenido"]
            _logger.info(f"📊 DEBUG WITHHOLDING - Eliminado MontoITBISRetenido para NCF 47")
            
        _logger.info(f"📊 DEBUG WITHHOLDING - withholding_vals final: {withholding_vals}")
        return withholding_vals
    

    def _get_Item_list(self, ecf_object_data, invoice):
        """Product lines related values"""
        #self.ensure_one()

        itbis_group = self._get_tax_group_safe("l10n_do_edi.tax_group_itbis", "ITBIS")
        is_company_currency = self.is_company_currency(invoice)
        l10n_do_ncf_type = self.get_l10n_do_ncf_type(invoice)

        def get_invoicing_indicator(inv_line):
            """Determina IndicadorFacturacion según reglas DGII"""
            # REGLA ESPECIAL E44: SIEMPRE EXENTO (4)
            if l10n_do_ncf_type == "44":
                return 4

            # REGLA ESPECIAL E46: SIEMPRE TASA CERO (3)
            if l10n_do_ncf_type == "46":
                return 3

            if not inv_line.tax_ids:
                return 4

            # Detectar impuestos ITBIS directamente
            itbis_amounts = []
            for tax in inv_line.tax_ids:
                is_itbis_group = tax.tax_group_id.name == "ITBIS" or "ITBIS" in str(tax.tax_group_id.name)
                if is_itbis_group and tax.amount > 0:
                    itbis_amounts.append(int(tax.amount))

            # Determinar indicador basado en impuestos ITBIS positivos
            if 18 in itbis_amounts:
                return 1
            elif 16 in itbis_amounts:
                return 2
            elif 0 in itbis_amounts:
                return 3
            else:
                # Verificar si es exento explícitamente
                for tax in inv_line.tax_ids:
                    if tax.tax_group_id == self._get_tax_group_safe("l10n_do_edi.tax_group_itbis_0", "Exento"):
                        return 4
                return 4

        # Autor: Arturo Diaz Lora
        # Fecha: 2025-11-25 23:05
        # Razón: Corregir orden de elementos según XSD de DGII
        # Agregados: TablaImpuestoAdicional y OtraMonedaDetalle en posición correcta
        item_order = [
            "NumeroLinea",
            "TablaCodigosItem",
            "IndicadorFacturacion",
            "Retencion",
            "NombreItem",
            "IndicadorBienoServicio",
            "DescripcionItem",
            "CantidadItem",
            "UnidadMedida",
            "CantidadReferencia",
            "UnidadReferencia",
            "TablaSubcantidad",
            "GradosAlcohol",
            "PrecioUnitarioReferencia",
            "FechaElaboracion",
            "FechaVencimientoItem",
            "PrecioUnitarioItem",
            "DescuentoMonto",
            "TablaSubDescuento",
            "RecargoMonto",
            "TablaSubRecargo",
            "TablaImpuestoAdicional",
            "OtraMonedaDetalle",
            "MontoItem",
        ]

        lines_data = []

        _logger.info(f"🔍 DEBUG ITEMS - Iniciando procesamiento de líneas para factura {invoice.name}")
        _logger.info(f"🔍 DEBUG ITEMS - NCF Type: '{l10n_do_ncf_type}'")
        
        j = 1
        for i, line in enumerate(
            invoice.invoice_line_ids.filtered(lambda l: l.display_type == 'product' and l.quantity and l.price_unit).sorted(
                "sequence"
            ),
            1,
        ):
            if line.product_id.default_code in ['DESC_GLOBAL', 'REC_GLOBAL']:
                continue

            rate = 1
            # Obtener type_tag dinámicamente (ECF o RFCE)
            type_tag = list(ecf_object_data.keys())[0]
            if "OtraMoneda" in ecf_object_data[type_tag]["Encabezado"]:
                rate = ecf_object_data[type_tag]["Encabezado"]["OtraMoneda"]["TipoCambio"]

            line_dict = od()
            product = line.product_id
            # ✅ CORRECCIÓN: Asegurar que product_name sea siempre string (nunca False)
            product_name = (product.name or '') if product else (line.name or '')
            if not product_name:  # Si aún está vacío, usar descripción genérica
                product_name = "Producto sin nombre"
            line_dict["NumeroLinea"] = j
            j += 1
            line_dict["IndicadorFacturacion"] = get_invoicing_indicator(line)

            # ✅ CORRECCIÓN DEFINITIVA: E41 necesita lógica especial, otros usan price_unit con quantity
            if l10n_do_ncf_type == "41":
                # E41: Usar price_unit con quantity (sin impuestos incluidos)
                data_price = line.tax_ids.compute_all(
                    # MODIFICADO: Arturo Diaz Lora - 2026-03-10 23:00
                    # Razón: Aplicar descuento al price_unit antes de compute_all para que
                    # MontoItem y cálculos de ITBIS por línea sean correctos
                    # Código original: price_unit=line.price_unit,
                    price_unit=line.price_unit * (1 - (line.discount or 0.0) / 100.0),
                    currency=line.currency_id,
                    quantity=line.quantity,
                    product=line.product_id,
                    partner=line.move_id.partner_id,
                    handle_price_include=False,
                )
            else:
                # E31-E34: Usar price_unit con quantity - compute_all maneja price_include automáticamente
                data_price = line.tax_ids.compute_all(
                    # MODIFICADO: Arturo Diaz Lora - 2026-03-10 23:00
                    # Razón: Aplicar descuento al price_unit antes de compute_all para que
                    # MontoItem y cálculos de ITBIS por línea sean correctos
                    # Código original: price_unit=line.price_unit,
                    price_unit=line.price_unit * (1 - (line.discount or 0.0) / 100.0),
                    currency=line.currency_id,
                    quantity=line.quantity,      # Necesario para cálculo correcto
                    product=line.product_id,
                    partner=line.move_id.partner_id,
                    # NO especificar handle_price_include - respeta configuración del impuesto
                )            

            _logger.info(f"🔍 DEBUG NCF TYPE - Línea {line.id}: {line.name}, NCF Type detectado: '{l10n_do_ncf_type}'")
            _logger.info(f"🔍 DEBUG NCF TYPE - Condición ('41', '47'): {l10n_do_ncf_type in ('41', '47')}")
            
            if l10n_do_ncf_type in ("41", "47"):
                _logger.info(f"📊 DEBUG E41 - Procesando retenciones para línea {line.id}: {line.name}")
                _logger.info(f"📊 DEBUG E41 - NCF Type: {l10n_do_ncf_type}")
                _logger.info(f"📊 DEBUG E41 - data_price: {data_price}")

                item_withholding = self._get_item_withholding_vals(line, data_price)
                _logger.info(f"📊 DEBUG E41 - item_withholding resultado: {item_withholding}")

                # CORRECCIÓN E41: Calcular retención ITBIS SOLO si la línea tiene ITBIS gravable
                # Error [11160] DGII: No se debe reportar TotalITBISRetenido cuando el servicio es EXENTO
                # Según Código Tributario Art. 344: Transporte terrestre es EXENTO de ITBIS
                # Corrección Error [272]: Redondear a 2 decimales
                # Autor: Arturo Diaz Lora - 2025-12-11 (CORREGIDO)
                if l10n_do_ncf_type == "41" and not item_withholding.get("MontoITBISRetenido"):
                    # Verificar si la línea tiene ITBIS gravable (tasa > 0, no exento)
                    # Si tiene "ITBIS Exempt" o tasa 0%, NO hay retención ITBIS
                    has_itbis_gravable = False
                    itbis_rate = 0
                    for tax_info in data_price.get('taxes', []):
                        tax_obj = self.env['account.tax'].browse(tax_info.get('id'))
                        if tax_obj:
                            tax_group_name = (tax_obj.tax_group_id.name or '') if tax_obj.tax_group_id else ''
                            if isinstance(tax_group_name, dict):
                                tax_group_name = tax_group_name.get('en_US', '') or tax_group_name.get('es_DO', '')
                            # Es ITBIS y tiene tasa > 0 (no exento)
                            if 'ITBIS' in str(tax_group_name).upper() and tax_obj.amount > 0:
                                has_itbis_gravable = True
                                itbis_rate = tax_obj.amount / 100  # Convertir % a decimal
                                break

                    if has_itbis_gravable:
                        # Solo calcular retención si hay ITBIS gravable
                        monto_retencion = round(line.price_unit * line.quantity * itbis_rate, 2)
                        item_withholding["MontoITBISRetenido"] = monto_retencion
                        _logger.info(f"E41 RETENCION ITBIS - Tasa: {itbis_rate*100}%, Base: {line.price_unit * line.quantity}, Retencion: {monto_retencion}")
                    else:
                        _logger.info(f"E41 SIN RETENCION ITBIS - Linea exenta de ITBIS, no se aplica retencion")

                # CORRECCIÓN E47: MontoISRRetenido es OBLIGATORIO según XSD
                if l10n_do_ncf_type == "47" and not item_withholding.get("MontoISRRetenido"):
                    # Para E47, MontoISRRetenido es obligatorio en el XSD, forzar a 0.00 si no hay retención
                    item_withholding["MontoISRRetenido"] = 0.00
                    _logger.info(f"E47 CORRECCION - MontoISRRetenido forzado a 0.00 (obligatorio segun XSD)")

                # CORRECCIÓN Error [3]: Orden de elementos según XSD e-CF 41
                # XSD requiere: 1) IndicadorAgenteRetencionoPercepcion, 2) MontoITBISRetenido, 3) MontoISRRetenido
                # Autor: Arturo Diaz Lora - 2025-12-11
                withholding_vals = od([("IndicadorAgenteRetencionoPercepcion", 1)])

                # Agregar MontoITBISRetenido PRIMERO (si existe)
                if item_withholding.get("MontoITBISRetenido"):
                    val = item_withholding["MontoITBISRetenido"]
                    withholding_vals["MontoITBISRetenido"] = round(val if is_company_currency else val * rate, 2)

                # Agregar MontoISRRetenido DESPUÉS (si existe y es > 0 o E47)
                if item_withholding.get("MontoISRRetenido"):
                    val = item_withholding["MontoISRRetenido"]
                    if val > 0 or l10n_do_ncf_type == "47":
                        withholding_vals["MontoISRRetenido"] = round(val if is_company_currency else val * rate, 2)

                if invoice.company_id.l10n_do_ecf_environment in ['pre_certification', 'certification']:
                    pass  # CAMPOS ESPECIALES DESHABILITADOS
                    # CAMPOS ESPECIALES DESHABILITADOS - for custom_line in invoice.l10n_do_custom_fields_ids:
                        # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.section == 'ItemRetencion' and custom_line.move_line_id.id == line.id and custom_line.name:
                            # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.delete:
                                # CAMPOS ESPECIALES DESHABILITADOS - withholding_vals.pop(custom_line.name, None)
                                # CAMPOS ESPECIALES DESHABILITADOS - continue
                            # CAMPOS ESPECIALES DESHABILITADOS - withholding_vals[custom_line.name] = custom_line.value if custom_line.value else ''
                
                _logger.info(f"📊 DEBUG E41 - withholding_vals final: {withholding_vals}")
                line_dict["Retencion"] = withholding_vals                
                _logger.info(f"📊 DEBUG E41 - line_dict[\"Retencion\"] asignado: {line_dict.get('Retencion')}")
                # if l10n_do_ncf_type == "47" and withholding_vals not in ("MontoITBISRetenido", "MontoISRRetenido"):
                #     del line_dict["Retencion"]

            # line_dict["NombreItem"] = product.name if product else line.name
            line_dict["NombreItem"] = (
                (product_name[:78] +
                 "..") if len(product_name) > 78 else product_name
            )
            line_dict["IndicadorBienoServicio"] = (
                2
                if (product and product.type == "service") or l10n_do_ncf_type == "47"
                else 1
            )
            line_dict["DescripcionItem"] = line.name
            #line_dict["CantidadItem"] = ("%f" % line.quantity).rstrip("0").rstrip(".")
            line_dict["CantidadItem"] = abs(line.quantity)
            # Mapeo de unidades de medida a códigos DGII
            uom_dgii_mapping = {
                'Units': '43',        # UND - Unidad (más común)
                'Unit': '43',         # UND - Unidad
                'Each': '44',         # EA - Elemento
                'kg': '21',           # KG - Kilogramo
                'Kilogram': '21',     # KG - Kilogramo
                'g': '17',            # GR - Gramo
                'Gram': '17',         # GR - Gramo
                'lb': '23',           # LB - Libra
                'L': '24',            # LITRO - Litro
                'Liter': '24',        # LITRO - Litro
                'm': '26',            # M - Metro
                'Meter': '26',        # M - Metro
                'm²': '27',           # M2 - Metro Cuadrado
                'm³': '28',           # M3 - Metro Cúbico
                'Hour': '19',         # HOR - Hora
                'Day': '12',          # DÍA - Día
                'Minute': '30',       # MIN - Minuto
                'Second': '37',       # SEG - Segundo
                'Box': '6',           # CAJ - Caja
                'Dozen': '13',        # DOC - Docena
                'Package': '31',      # PAQ - Paquete
                'Bag': '2',           # BOL - Bolsa
                'Bottle': '5',        # BOTELLA - Botella
                'Gallon': '15',       # GL - Galones
                'Ton': '39',          # TONE - Tonelada
            }

            # Verificar si el campo code existe (añadido por l10n_do_accounting)
            if hasattr(line.product_uom_id, 'code') and line.product_uom_id.code:
                line_dict["UnidadMedida"] = line.product_uom_id.code
            elif line.product_uom_id.name in uom_dgii_mapping:
                # Mapear nombre común a código DGII
                line_dict["UnidadMedida"] = uom_dgii_mapping[line.product_uom_id.name]
            else:
                # Por defecto usar "43" (UND - Unidad) como más común
                line_dict["UnidadMedida"] = "43"

            # ✅ CORRECCIÓN: Para facturas SIEMPRE usar precio SIN impuestos en el detalle
            # El detalle del ítem debe mostrar precios sin impuestos, independientemente de price_include
            price_unit = abs(round(data_price['total_excluded']/line.quantity, 2))
            price_subtotal = abs(round(data_price['total_excluded'], 2))

            if line.discount:
                price_unit = price_unit / (1 - (line.discount / 100.0))
            if hasattr(line, 'discount2') and line.discount2 < 0:
                price_unit = price_unit / (1 + (abs(line.discount2) / 100.0))

            line_dict["PrecioUnitarioItem"] = abs(round(price_unit if is_company_currency else price_unit * rate, 2))

            price_wo_discount = line.quantity * price_unit
            price_with_discount = price_wo_discount * \
                (1 - (line.discount / 100.0))
            discount_amount = (
                abs(round(price_with_discount - price_wo_discount, 2))
                if line.discount
                else 0
            )

            currency_discount_amount = discount_amount
            discount_amount = (
                discount_amount
                if is_company_currency
                else round(discount_amount * rate, 2)
            )

            if line.discount:                            
                line_dict["DescuentoMonto"] = abs(round(discount_amount, 2))
                tabla_dict = {
                    "SubDescuento": [
                        {
                            "TipoSubDescuento": "%",
                            "SubDescuentoPorcentaje": abs(round(line.discount, 2)),
                            "MontoSubDescuento": abs(round(discount_amount, 2)),
                        }
                    ]
                }
                if invoice.company_id.l10n_do_ecf_environment in ['pre_certification', 'certification']:
                    pass  # CAMPOS ESPECIALES DESHABILITADOS
                    # CAMPOS ESPECIALES DESHABILITADOS - for custom_line in invoice.l10n_do_custom_fields_ids:
                        # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.section == 'ItemDescuento' and custom_line.move_line_id.id == line.id and custom_line.name:
                            # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.delete:
                                # CAMPOS ESPECIALES DESHABILITADOS - tabla_dict["SubDescuento"][0].pop(custom_line.name, None)
                                # CAMPOS ESPECIALES DESHABILITADOS - continue
                            # CAMPOS ESPECIALES DESHABILITADOS - tabla_dict["SubDescuento"][0][custom_line.name] = custom_line.value if custom_line.value else ''
                line_dict["TablaSubDescuento"] = tabla_dict

            if hasattr(line, 'discount2') and line.discount2 < 0:
                recargo_amount = ( price_wo_discount - discount_amount ) * abs(line.discount2) / 100
                line_dict["RecargoMonto"] = abs(round(recargo_amount, 2))
                tabla_dict = {
                    "SubRecargo": [
                        {
                            "TipoSubRecargo": "%",
                            "SubRecargoPorcentaje": abs(round(line.discount2, 2)),
                            "MontoSubRecargo": abs(round(recargo_amount, 2)),
                        }
                    ]
                }
                if invoice.company_id.l10n_do_ecf_environment in ['pre_certification', 'certification']:
                    pass  # CAMPOS ESPECIALES DESHABILITADOS
                    # CAMPOS ESPECIALES DESHABILITADOS - for custom_line in invoice.l10n_do_custom_fields_ids:
                        # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.section == 'ItemRecargo' and custom_line.move_line_id.id == line.id and custom_line.name:
                            # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.delete:
                                # CAMPOS ESPECIALES DESHABILITADOS - tabla_dict["SubRecargo"][0].pop(custom_line.name, None)
                                # CAMPOS ESPECIALES DESHABILITADOS - continue
                            # CAMPOS ESPECIALES DESHABILITADOS - tabla_dict["SubRecargo"][0][custom_line.name] = custom_line.value if custom_line.value else ''
                line_dict["TablaSubRecargo"] = tabla_dict
                

            if not is_company_currency:
                line_dict["OtraMonedaDetalle"] = {
                    "PrecioOtraMoneda": abs(price_unit),
                    "DescuentoOtraMoneda": currency_discount_amount,
                    "MontoItemOtraMoneda": abs(round(price_subtotal, 2)),
                }

            line_dict["MontoItem"] = abs(round(price_subtotal if is_company_currency else price_subtotal * rate, 2))

            if invoice.company_id.l10n_do_ecf_environment in ['pre_certification', 'certification']:
                pass  # CAMPOS ESPECIALES DESHABILITADOS
                # CAMPOS ESPECIALES DESHABILITADOS - for custom_line in invoice.l10n_do_custom_fields_ids:
                    # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.section == 'Item' and custom_line.move_line_id.id == line.id and custom_line.name:
                        # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.delete:
                            # CAMPOS ESPECIALES DESHABILITADOS - line_dict.pop(custom_line.name, None)
                            # CAMPOS ESPECIALES DESHABILITADOS - continue
                        # CAMPOS ESPECIALES DESHABILITADOS - line_dict[custom_line.name] = custom_line.value if custom_line.value else ''

            line_order = self.reorder_dict(line_dict, item_order)
            lines_data.append(line_order)

        return lines_data
    

    def _get_descuento_recargo_list(self, ecf_object_data, invoice):

        itbis_group = self._get_tax_group_safe("l10n_do_edi.tax_group_itbis", "ITBIS")
        is_company_currency = self.is_company_currency(invoice)
        l10n_do_ncf_type = self.get_l10n_do_ncf_type(invoice)

        def get_discount_invoicing_indicator(inv_line):
            "IndicadorFacturacionDescuentooRecargo"
            if not inv_line.tax_ids:
                return 4
            tax_set = set(
                tax.amount
                for tax in inv_line.tax_ids
                if tax.tax_group_id.id == itbis_group.id
            )
            if len(tax_set) > 1 or 18 in tax_set:
                return 1
            elif 16 in tax_set:
                return 2
            elif l10n_do_ncf_type == "46" and 0 in tax_set:
                return 3
            else:
                return 4
            
        descuento_recargo_order = [
            "NumeroLinea",
            "TipoAjuste",
            "IndicadorNorma1007",
            "DescripcionDescuentooRecargo",
            "TipoValor",
            "ValorDescuentooRecargo",
            "MontoDescuentooRecargo",
            "MontoDescuentooRecargoOtraMoneda",
            "IndicadorFacturacionDescuentooRecargo",
        ]

        lines_data = []

        j = 1
        for i, line in enumerate(
            invoice.invoice_line_ids.filtered(lambda l: not l.display_type).sorted(
                "sequence"
            ),
            1,
        ):
            if line.product_id.default_code not in ['DESC_GLOBAL', 'REC_GLOBAL']:
                continue
            
            rate = 1
            # Obtener type_tag dinámicamente (ECF o RFCE)
            type_tag = list(ecf_object_data.keys())[0]
            if "OtraMoneda" in ecf_object_data[type_tag]["Encabezado"]:
                rate = ecf_object_data[type_tag]["Encabezado"]["OtraMoneda"]["TipoCambio"]

            line_dict = od()

            line_dict["NumeroLinea"] = j
            j += 1
            line_dict["TipoAjuste"] = 'D' if line.product_id.default_code == 'DESC_GLOBAL' else 'R'
            line_dict["DescripcionDescuentooRecargo"] = line.name
            line_dict["TipoValor"] = "$"

            data_price = line.tax_ids.compute_all(
                price_unit=line.price_subtotal,
                currency=line.currency_id,
                product=line.product_id,
                partner=line.move_id.partner_id,
                handle_price_include=False,
            )
            price_unit = abs(round(data_price['total_excluded']/line.quantity, 2))
            price_unit = price_unit / (1 - (line.discount / 100.0))
            line_dict["MontoDescuentooRecargo"] = f"{abs(round(price_unit if is_company_currency else price_unit * rate, 2)):.2f}"

            line_dict["IndicadorFacturacionDescuentooRecargo"] = get_discount_invoicing_indicator(line)

            if invoice.company_id.l10n_do_ecf_environment in ['pre_certification', 'certification']:
                pass  # CAMPOS ESPECIALES DESHABILITADOS
                # CAMPOS ESPECIALES DESHABILITADOS - for custom_line in invoice.l10n_do_custom_fields_ids:
                    # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.section == 'DescuentoORecargo' and custom_line.move_line_id.id == line.id and custom_line.name:
                        # CAMPOS ESPECIALES DESHABILITADOS - if custom_line.delete:
                            # CAMPOS ESPECIALES DESHABILITADOS - line_dict.pop(custom_line.name, None)
                            # CAMPOS ESPECIALES DESHABILITADOS - continue
                        # CAMPOS ESPECIALES DESHABILITADOS - line_dict[custom_line.name] = custom_line.value if custom_line.value else ''

            line_order = self.reorder_dict(line_dict, descuento_recargo_order)
            lines_data.append(line_order)

        return lines_data
    

    def _get_InformacionReferencia_data(self, ecf_object_data, invoice):
        """Data included Debit/Credit Note"""
        #self.ensure_one()
        reference_info_data = od({})

        origin_id = (
            self.env['account.move'].search([("l10n_latam_document_number", "=",
                        invoice.l10n_do_origin_ncf)], limit=1)
            if self.get_l10n_do_ncf_type(invoice) == "34"
            else invoice.debit_origin_id
        )

        if not origin_id:
            raise ValidationError(_("Could not found origin document."))

        if "InformacionReferencia" not in ecf_object_data["ECF"]:
            ecf_object_data["ECF"]["InformacionReferencia"] = od({})
        reference_info_data["NCFModificado"] = origin_id.l10n_latam_document_number
        reference_info_data["FechaNCFModificado"] = dt.strftime(
            origin_id.invoice_date, "%d-%m-%Y"
        )
        reference_info_data["CodigoModificacion"] = int(invoice.l10n_do_ecf_modification_code)
        if invoice.ref and "," in invoice.ref:
            reference_info_data["RazonModificacion"] = invoice.ref.split(",", 1)[1].strip()[:90] if "," in invoice.ref else ""

        return reference_info_data


    def _generate_xml(self, invoice, is_resumen, security_code=None):
        l10n_do_ncf_type = self.get_l10n_do_ncf_type(invoice)
        
        _logger.info(f"🎯 DEBUG _generate_xml - Factura: {invoice.name} (ID: {invoice.id})")
        _logger.info(f"🎯 DEBUG _generate_xml - NCF Type obtenido: '{l10n_do_ncf_type}'")
        _logger.info(f"🎯 DEBUG _generate_xml - Tipo de factura: {invoice.move_type}")
        _logger.info(f"🎯 DEBUG _generate_xml - is_resumen: {is_resumen}")
        
        is_company_currency = self.is_company_currency(invoice)

        if is_resumen:
            type_tag = 'RFCE'
        else:
            type_tag = 'ECF'
        
        # Estructura correcta según XSD oficial de DGII
        ecf_object_data = od({
            type_tag: od({
                "Encabezado": od({
                    "Version": "1.0",
                    "IdDoc": self._get_IdDoc_data(invoice, is_resumen, security_code),
                    "Emisor": self._get_Emisor_data(invoice, is_resumen),
                    "Comprador": self._get_Comprador_data(invoice, is_resumen),
                    "Totales": self._get_Totales_data(invoice, is_resumen),
                }),
            })
        })
        
        # Agregar elementos opcionales según el tipo de documento
        if not is_resumen:
            ecf_object_data[type_tag]["DetallesItems"] = od({})
            ecf_object_data[type_tag]["DescuentosORecargos"] = od({})
            ecf_object_data[type_tag]["InformacionReferencia"] = od({})
            
        # FechaHoraFirma va al nivel del ECF/RFCE según XSD
        ecf_object_data[type_tag]["FechaHoraFirma"] = fields.Datetime.context_timestamp(
            self.with_context(tz="America/Santo_Domingo"),
            fields.Datetime.now(),
        ).strftime("%d-%m-%Y %H:%M:%S")
        
        if is_resumen:
            # Para resúmenes (RFCE) no se incluye FechaHoraFirma según XSD
            del ecf_object_data[type_tag]["FechaHoraFirma"]
            # Agregar código de seguridad para resúmenes
            ecf_object_data[type_tag]["Encabezado"]["CodigoSeguridadeCF"] = security_code

        # Para tipo 43 (Gastos Menores) y 47 (Pagos al Exterior) no se incluye Comprador
        if l10n_do_ncf_type in ("43", "47"):
            if "Comprador" in ecf_object_data[type_tag]["Encabezado"]:
                del ecf_object_data[type_tag]["Encabezado"]["Comprador"]

        if not is_company_currency:
            if "OtraMoneda" not in ecf_object_data[type_tag]["Encabezado"]:
                ecf_object_data[type_tag]["Encabezado"]["OtraMoneda"] = od({})
            ecf_object_data[type_tag]["Encabezado"][
                "OtraMoneda"
            ] = self._get_OtraMoneda_data(ecf_object_data, invoice)

        # Invoice lines
        if not is_resumen:
            items_list = self._get_Item_list(ecf_object_data, invoice)
            if items_list:
                ecf_object_data[type_tag]["DetallesItems"]["Item"] = items_list
            else:
                # Si no hay ítems válidos, crear uno mínimo para cumplir XSD
                default_item = {
                    "NumeroLinea": 1,
                    "IndicadorFacturacion": 1,
                    "NombreItem": "Producto/Servicio",
                    "IndicadorBienoServicio": 1,
                    "CantidadItem": 1.0,
                    "PrecioUnitarioItem": invoice.amount_untaxed,
                    "MontoItem": invoice.amount_untaxed
                }
                ecf_object_data[type_tag]["DetallesItems"]["Item"] = [default_item]

            # Descuentos recargos
            j = 0
            for i, line in enumerate(
                invoice.invoice_line_ids.filtered(lambda l: not l.display_type).sorted(
                    "sequence"
                ),
                1,
            ):
                if line.product_id.default_code in ['DESC_GLOBAL', 'REC_GLOBAL']:
                    j += 1
            if j > 0:
                ecf_object_data[type_tag]["DescuentosORecargos"]["DescuentoORecargo"] = self._get_descuento_recargo_list(
                    ecf_object_data, invoice
                )
            else:
                del ecf_object_data[type_tag]["DescuentosORecargos"]

            if l10n_do_ncf_type in ("33", "34"):
                ecf_object_data[type_tag][
                    "InformacionReferencia"
                ] = self._get_InformacionReferencia_data(ecf_object_data, invoice)
            else:
                del ecf_object_data[type_tag]["InformacionReferencia"]
        

        # Convertir valores numéricos a strings con formato correcto
        ecf_object_data = self._format_numeric_values(ecf_object_data)
        
        # Generar XML con formato correcto
        xml_string = xmltodict.unparse(ecf_object_data)
        
        # Asegurar que el XML tiene la declaración correcta
        if not xml_string.startswith('<?xml'):
            xml_string = '<?xml version="1.0" encoding="utf-8"?>' + xml_string
        
        return xml_string

    def _format_numeric_values(self, data, parent_key=""):
        """Convierte valores numéricos a strings con formato correcto según XSD"""
        # Campos que deben ser enteros según el XSD oficial
        integer_fields = {
            'TipoeCF', 'IndicadorMontoGravado', 'TipoPago', 'IndicadorEnvioDiferido',
            'IndicadorServicioTodoIncluido', 'TipoIngresos', 'TotalPaginas',
            'ITBIS1', 'ITBIS2', 'ITBIS3', 'NumeroPedidoInterno', 'NumeroReferencia',
            'DocumentoTransporte', 'FormaPago', 'TipoCuentaPago', 'BancoPago',
            'CodigoModificacion', 'NumeroLinea', 'UnidadMedida',
            'TipoItem', 'CodigoItem', 'IndicadorFacturacion', 'IndicadorBienesUsados',
            'IndicadorAgenteRetencionoPercepcion', 'RetencionRenta', 'TasaITBIS',
            'TerminoPago', 'Cantidad', 'IndicadorNotaCredito', 'TipoDescuentooRecargo',
            'TipoValor', 'IndicadorFacturacionDescuentooRecargo', 'IndicadorBienoServicio',
            'Municipio', 'Provincia', 'MunicipioComprador', 'ProvinciaComprador'
        }
        
        if isinstance(data, dict):
            result = {}
            for k, v in data.items():
                # Pasar la clave actual como contexto para elementos anidados
                result[k] = self._format_numeric_values(v, k)
            return result
        elif isinstance(data, list):
            return [self._format_numeric_values(item, parent_key) for item in data]
        elif isinstance(data, (int, float)):
            # Verificar si este campo debe ser entero
            if parent_key in integer_fields:
                return str(int(float(data)))  # Convertir a entero
            else:
                return f"{float(data):.2f}"   # Mantener como decimal
        else:
            return data

    def _calculate_digest_with_ns(self, xml_path):
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.parse(xml_path, parser)
        root = tree.getroot()
        xml_c14n = etree.tostring(root, method="c14n", exclusive=False, with_comments=False).decode()
        digest = hashlib.sha256(xml_c14n.encode()).digest()
        return base64.b64encode(digest).decode()
    
    def _sign_data(self, data, private_key):
        signer = private_key.sign(
            data,
            padding.PKCS1v15(),
            SHA256()
        )
        return base64.b64encode(signer).decode()
    
    def _sign_xml(self, xml_path, output_path, company):
        if not company.l10n_do_pkcs12_file or not company.l10n_do_pkcs12_password:
            raise ValueError("No se encontró el certificado en la empresa o la contraseña está vacía")
        p12_content = base64.b64decode(company.l10n_do_pkcs12_file)
        key, cert, _ = pkcs12.load_key_and_certificates(p12_content, company.l10n_do_pkcs12_password.encode())
        cert_b64 = base64.b64encode(cert.public_bytes(encoding=serialization.Encoding.DER)).decode()
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.parse(xml_path, parser)
        root = tree.getroot()
        digest_value = self._calculate_digest_with_ns(xml_path)
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
        signed_info_str = etree.tostring(signed_info, method="c14n", exclusive=False, with_comments=False)
        signature_value = self._sign_data(signed_info_str, key)
        etree.SubElement(signature, "SignatureValue").text = signature_value
        key_info = etree.SubElement(signature, "KeyInfo")
        x509_data = etree.SubElement(key_info, "X509Data")
        etree.SubElement(x509_data, "X509Certificate").text = cert_b64
        root.append(signature)
        tree.write(output_path, encoding="utf-8", xml_declaration=True, pretty_print=True)


    def _get_token(self, company_id):
        #self.sign_xml_ant('/tmp/tmpltewi8bh.xml', '/tmp/13052712_identity.p12', 'p4331q1q**', '/tmp/tmpltewi8bh_signed.xml', )

        _logger.info("Validar en la DGII...")
        if company_id.l10n_do_ecf_environment == 'pre_certification':
            url_semilla = PRE_CERTIFICATION_URL.get('semilla')
            url_validar_semilla = PRE_CERTIFICATION_URL.get('validar_semilla')
        elif company_id.l10n_do_ecf_environment == 'certification':
            url_semilla = CERTIFICATION_URL.get('semilla')
            url_validar_semilla = CERTIFICATION_URL.get('validar_semilla')
        elif company_id.l10n_do_ecf_environment == 'production':
            url_semilla = PRODUCTION_URL.get('semilla')
            url_validar_semilla = PRODUCTION_URL.get('validar_semilla')
        else:
            raise ValidationError("Debe seleccionar un ambiente válido en la Compañia")

        # Obtener semilla
        headers = {
            "Accept": "application/xml"
        }
        response = requests.get(url_semilla, headers=headers, timeout=20)
        response.raise_for_status()
        if response.status_code == 200:
            xml_data = response.content.decode("utf-8")
            
            # Grabar semilla en archivo temporal
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as temp_xml_file:
                temp_xml_file.write(xml_data.encode("utf-8"))  
                temp_xml_file_path = temp_xml_file.name
            _logger.info(temp_xml_file_path)

            # Firmar archivo
            base, ext = os.path.splitext(temp_xml_file_path)
            signed_filename = base + '_signed' + ext
            self._sign_xml(temp_xml_file_path, signed_filename, company_id)

            # Validar semilla
            headers = {
                "Accept": "application/json",
            }
            files = {
                "xml": (signed_filename, open(signed_filename, "rb"), "text/xml")
            }
            response = requests.post(url_validar_semilla, headers=headers, files=files, timeout=20)
            response.raise_for_status()
            return response.json().get('token')


    def _check_state_dgii(self, company_id, token):
        _logger.info("Consultando XML firmado a la DGII...")
        if company_id.l10n_do_ecf_environment == 'pre_certification':
            url_dgii = PRE_CERTIFICATION_URL.get('verificar_estado')
            ambiente = 1 #1-Pre-certificacion 2-Produccion 3-Certificacion
        elif company_id.l10n_do_ecf_environment == 'certification':
            url_dgii = CERTIFICATION_URL.get('verificar_estado')
            ambiente = 3 #1-Pre-certificacion 2-Produccion 3-Certificacion
        elif company_id.l10n_do_ecf_environment == 'production':
            url_dgii = PRODUCTION_URL.get('verificar_estado')
            ambiente = 2 #1-Pre-certificacion 2-Produccion 3-Certificacion
        else:
            raise ValidationError("Debe seleccionar un ambiente válido en la Compañia")

        headers = {
            "accept": "application/json",
            "Authorization": "bearer " + str(token)
        }
        params = {
            "ambiente": ambiente
        }
        response = requests.get(url_dgii, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        return response.json()


    def _send_xml_to_dgii(self, signed_filename, company_id, token, is_resumen):
        _logger.info("=== ENVIANDO XML FIRMADO A LA DGII ===")
        _logger.info(f"Archivo: {signed_filename}")
        _logger.info(f"Ambiente: {company_id.l10n_do_ecf_environment}")
        _logger.info(f"Es resumen: {is_resumen}")
        
        if company_id.l10n_do_ecf_environment == 'pre_certification':
            if not is_resumen:
                url_recepcion = PRE_CERTIFICATION_URL.get('recepcion')
            else:
                url_recepcion = PRE_CERTIFICATION_URL.get('recepcion_fc')
        elif company_id.l10n_do_ecf_environment == 'certification':
            if not is_resumen:
                url_recepcion = CERTIFICATION_URL.get('recepcion')
            else:
                url_recepcion = CERTIFICATION_URL.get('recepcion_fc')
        elif company_id.l10n_do_ecf_environment == 'production':
            if not is_resumen:
                url_recepcion = PRODUCTION_URL.get('recepcion')
            else:
                url_recepcion = PRODUCTION_URL.get('recepcion_fc')
        else:
            raise ValidationError("Debe seleccionar un ambiente válido en la Compañia")
            
        _logger.info(f"URL de recepción: {url_recepcion}")

        headers = {
            "accept": "application/json",
            "Authorization": "bearer " + str(token)
        }
        files = {
            "xml": (os.path.basename(signed_filename), open(signed_filename, "rb"), "text/xml")
        }
        
        _logger.info(f"Headers preparados: {{'accept': 'application/json', 'Authorization': 'bearer [TOKEN_OCULTO]'}}")
        _logger.info("Iniciando POST request...")

        try:
            response = requests.post(url_recepcion, headers=headers, files=files, timeout=20)            
            
            _logger.info(f"✅ Respuesta recibida - Status Code: {response.status_code}")
            _logger.info(f"📄 Respuesta JSON: {response.text}")
            
            response.raise_for_status()
            response_json = response.json()
            _logger.info(f"🎯 Respuesta parseada: {response_json}")
            
            return response_json
        
        # Manejo de errores HTTP
        except requests.exceptions.HTTPError as errh:
            _logger.error(f"❌ Error HTTP: {errh} - Código: {response.status_code}")
            _logger.error(f"🔍 Detalle: {response.text}")
            try:
                return response.json()
            except:
                return {"error": f"Error HTTP {response.status_code}", "mensaje": response.text}

        # Error de conexión
        except requests.exceptions.ConnectionError as errc:
            _logger.error(f"❌ Error de Conexión: {errc}")
            return {"error": "Error de conexión", "mensaje": str(errc)}

        # Timeout
        except requests.exceptions.Timeout as errt:
            _logger.error(f"⏳ Timeout: {errt}")
            return {"error": "Timeout", "mensaje": str(errt)}

        # Otros errores
        except requests.exceptions.RequestException as err:
            _logger.error(f"❌ Error inesperado en la solicitud: {err}")
            return {"error": "Error de solicitud", "mensaje": str(err)}
        except Exception as e:
            _logger.error(f"❌ Error crítico: {str(e)}")
            return {"error": "Error crítico", "mensaje": str(e)}

    def _check_dgii(self, company_id, token, trackId):  
        _logger.info("Consultando XML firmado a la DGII...")
        if company_id.l10n_do_ecf_environment == 'pre_certification':
            url_consulta = PRE_CERTIFICATION_URL.get('consulta')
        elif company_id.l10n_do_ecf_environment == 'certification':
            url_consulta = CERTIFICATION_URL.get('consulta')
        elif company_id.l10n_do_ecf_environment == 'production':
            url_consulta = PRODUCTION_URL.get('consulta')
        else:
            raise ValidationError("Debe seleccionar un ambiente válido en la Compañia")
        headers = {
            "accept": "application/json",
            "Authorization": "bearer " + str(token)
        }
        params = {
            "trackId": trackId
        }

        try:
            response = requests.get(url_consulta, headers=headers, params=params, timeout=20)
            if response.status_code == 204:
                _logger.warning("La DGII devolvió 204 No Content: no hay datos para estos parámetros.")
                return {}
            response.raise_for_status()
            return response.json()

        # Manejo de errores HTTP
        except requests.exceptions.HTTPError as errh:
            _logger.error(f"❌ Error HTTP: {errh} - Código: {response.status_code}")
            #_logger.error("🔍 Detalle:", response.text)
            return json.loads(response.text)

        # Error de conexión
        except requests.exceptions.ConnectionError as errc:
            _logger.error(f"❌ Error de Conexión: {errc}")
            return json.loads(response.text)

        # Timeout
        except requests.exceptions.Timeout as errt:
            _logger.error(f"⏳ Timeout: {errt}")
            return json.loads(response.text)

        # Otros errores
        except requests.exceptions.RequestException as err:
            _logger.error(f"❌ Error inesperado en la solicitud: {err}")
            return json.loads(response.text)


    def _generate_qr_code(self, invoice):
        """Genera el código QR para validación de la DGII con formato correcto"""
        try:
            # Obtener datos necesarios para el QR
            company = invoice.company_id
            ncf = invoice.l10n_latam_document_number or ""
            rnc_emisor = company.vat or ""
            security_code = invoice.l10n_do_ecf_security_code
            fecha_firma = invoice.l10n_do_ecf_sign_date
            l10n_do_ncf_type = self.get_l10n_do_ncf_type(invoice)

            if not security_code:
                _logger.warning(f"No hay código de seguridad para generar QR en factura {invoice.name}")
                return None

            # URL encoding para código de seguridad
            security_code_encoded = quote(security_code) if security_code else ""

            # Construir URL del QR según el ambiente (URLs corregidas)
            environment = company.l10n_do_ecf_environment or 'pre_certification'

            _logger.info(f"🔍 DEBUG QR - Factura: {invoice.name}, NCF: {ncf}, Tipo: {l10n_do_ncf_type}, Monto: {invoice.amount_total}")

            # ========================================================================
            # CAMBIO CRÍTICO: E32 < 250K usa servicio diferente (consultatimbrefc)
            # ========================================================================
            # Según documentación DGII (páginas 42-44):
            # - E32 < 250K: usa fc.dgii.gov.do/consultatimbrefc con solo 4 parámetros
            # - E32 >= 250K: usa ecf.dgii.gov.do/consultatimbre con 7 parámetros
            # - Otros tipos: usa ecf.dgii.gov.do/consultatimbre con 7 parámetros

            if l10n_do_ncf_type == '32' and invoice.amount_total < 250000.00:
                # E32 < 250K: Usa servicio ConsultaTimbreFC con formato simplificado
                _logger.info(f"🔍 QR E32 < 250K: Usando servicio ConsultaTimbreFC (servicio para resúmenes)")

                # URLs según ambiente - Formato REAL de DGII (verificado en producción)
                if environment == 'production':
                    base_url = "https://fc.dgii.gov.do/eCF/ConsultaTimbreFC"
                elif environment == 'certification':
                    base_url = "https://fc.dgii.gov.do/CerteCF/ConsultaTimbreFC"
                else:
                    # Pre-certificación (por defecto)
                    base_url = "https://fc.dgii.gov.do/TesteCF/ConsultaTimbreFC"

                # Calcular monto total con formato correcto (decimales incluidos)
                monto_total = ("%.2f" % abs(invoice.amount_total))

                # Para E32 < 250K solo se usan 4 parámetros en PascalCase
                # NCF debe estar en MAYÚSCULAS (formato real de DGII)
                api_url = f'{base_url}?RncEmisor={rnc_emisor}&ENCF={ncf}&MontoTotal={monto_total}&CodigoSeguridad={security_code}'

                _logger.info(f"✅ QR E32 < 250K - URL simplificada: {api_url}")

            else:
                # Para E32 >= 250K y otros tipos: usa servicio consultatimbre con todos los parámetros
                if environment == 'production':
                    base_url = "https://ecf.dgii.gov.do/ecf/consultatimbre"
                elif environment == 'certification':
                    base_url = "https://ecf.dgii.gov.do/certecf/consultatimbre"
                else:
                    base_url = "https://ecf.dgii.gov.do/testecf/consultatimbre"

                # Construir parámetros base
                api_url = f'{base_url}?rncemisor={rnc_emisor}'

                # Manejar RncComprador según el tipo de documento
                if l10n_do_ncf_type in ('43', '47'):
                    # Tipo 43 (Gastos Menores) y 47 (Pagos al Exterior): NO incluir parámetro rnccomprador
                    _logger.info(f"🔍 DEBUG QR - Tipo {l10n_do_ncf_type}: RncComprador NO incluido en URL")
                elif l10n_do_ncf_type == '32':
                    # E32 >= 250,000: RncComprador obligatorio
                    rnc_comprador = invoice.partner_id.vat or ""
                    api_url += f'&rnccomprador={rnc_comprador}'
                    _logger.info(f"🔍 DEBUG QR - E32 >= 250K: RncComprador incluido: {rnc_comprador}")
                else:
                    # Otros tipos (E31, E33-E47): RncComprador obligatorio
                    rnc_comprador = invoice.partner_id.vat or ""
                    api_url += f'&rnccomprador={rnc_comprador}'
                    _logger.info(f"🔍 DEBUG QR - Tipo {l10n_do_ncf_type}: RncComprador incluido: {rnc_comprador}")

                # Formatear fechas según requerimientos DGII
                fecha_emision = invoice.invoice_date.strftime("%d-%m-%Y") if invoice.invoice_date else ""
                fecha_firma_str = fecha_firma.strftime("%d-%m-%Y %H:%M:%S") if fecha_firma else ""
                fecha_firma_encoded = quote(fecha_firma_str) if fecha_firma_str else ""

                # Calcular monto según tipo de documento
                if l10n_do_ncf_type == '43':
                    # Tipo 43 usa amount_untaxed
                    monto_total = ("%f" % abs(invoice.amount_untaxed)).rstrip("0").rstrip(".")
                elif l10n_do_ncf_type == '41':
                    # Tipo 41 (Compras): Calcular monto ANTES de retenciones
                    tax_data = self.get_taxed_amount_data(invoice)

                    # Calcular total base gravada
                    total_base = abs(sum([
                        tax_data["18_taxed_base"],
                        tax_data["16_taxed_base"],
                        tax_data["0_taxed_base"],
                    ]))

                    # Calcular total ITBIS
                    total_itbis = abs(sum([
                        tax_data["18_taxed_amount"],
                        tax_data["16_taxed_amount"],
                        tax_data["other_amount"],
                    ]))

                    monto_qr = abs(total_base + total_itbis)
                    monto_total = ("%f" % monto_qr).rstrip("0").rstrip(".")
                    _logger.info(f"💰 QR E41 - Base: {total_base}, ITBIS: {total_itbis}, Total QR: {monto_qr}")
                else:
                    # Otros tipos usan amount_total
                    monto_total = ("%f" % abs(invoice.amount_total)).rstrip("0").rstrip(".")

                # Parámetros completos con fechas para consultatimbre
                api_url += f'&encf={ncf}&fechaemision={fecha_emision}&montototal={monto_total}&fechafirma={fecha_firma_encoded}&codigoseguridad={security_code_encoded}'

                _logger.info(f"✅ QR generado con URL completa: {api_url}")

            # Generar código QR con mejor calidad
            qr_code = pyqrcode.create(api_url)
            qr_image_data = qr_code.png_as_base64_str(scale=8)  # Mayor resolución para evitar borrosidad

            _logger.info(f"✅ QR generado para factura {invoice.name}")
            _logger.info(f"📊 URL QR generada: {api_url}")

            return {
                'qr_image': qr_image_data,
                'qr_url': api_url
            }

        except Exception as e:
            _logger.error(f"Error generando código QR para factura {invoice.name}: {str(e)}")
            return None
