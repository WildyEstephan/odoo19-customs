# -*- coding: utf-8 -*-
"""
Controlador completo para certificación DGII - Puntos 7-12
Implementa todos los servicios requeridos para el proceso de certificación directa
"""

from odoo import http, fields, _
from odoo.http import request, Response
from odoo.exceptions import UserError
from lxml import etree
from datetime import datetime, timedelta
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import load_pem_x509_certificate
import json
import logging
import base64
import uuid
import hashlib
import xmltodict
import os
import tempfile

_logger = logging.getLogger(__name__)

class DGIICertificationController(http.Controller):
    """
    Controlador completo para puntos 7-12 de certificación DGII
    """

    # ========================================================================
    # PUNTO 7 - URL SERVICIOS PRUEBA
    # ========================================================================

    @http.route('/fe/certification/urls/update',
                type='jsonrpc', auth='user', csrf=False, methods=['POST'])
    def update_service_urls(self, **kwargs):
        """
        Punto 7: Actualizar URLs de servicios de prueba
        """
        try:
            _logger.info("📝 PUNTO 7: Actualizando URLs de servicios de prueba")

            company = request.env.company

            # URLs que se deben configurar para pruebas
            service_urls = {
                'url_recepcion': kwargs.get('url_recepcion', '/fe/recepcion/api/ecf'),
                'url_aprobacion': kwargs.get('url_aprobacion', '/fe/aprobacioncomercial/api/ecf'),
                'url_autenticacion': kwargs.get('url_autenticacion', '/fe/autenticacion/api/semilla'),
                'ambiente': 'certificacion'
            }

            # Guardar URLs en configuración de la compañía
            for key, value in service_urls.items():
                request.env['ir.config_parameter'].sudo().set_param(
                    f'l10n_do_edi.{key}_{company.id}',
                    value
                )

            response = {
                'status': 'success',
                'message': 'URLs de servicios actualizadas correctamente',
                'urls': service_urls,
                'punto_certificacion': 7,
                'descripcion': 'URL Servicios Prueba configurados'
            }

            _logger.info(f"✅ PUNTO 7 completado: {service_urls}")
            return response

        except Exception as e:
            _logger.error(f"❌ Error en punto 7: {str(e)}")
            return {'status': 'error', 'message': str(e)}

    # ========================================================================
    # PUNTO 8 - INICIO PRUEBA RECEPCIÓN E-CF
    # ========================================================================

    @http.route('/fe/certification/ready/reception',
                type='jsonrpc', auth='user', csrf=False, methods=['POST'])
    def start_reception_test(self, **kwargs):
        """
        Punto 8: Indicar que está listo para recibir e-CF de prueba
        """
        try:
            _logger.info("🚀 PUNTO 8: Iniciando prueba de recepción e-CF")

            # Validar que los servicios estén configurados
            company = request.env.company
            url_recepcion = request.env['ir.config_parameter'].sudo().get_param(
                f'l10n_do_edi.url_recepcion_{company.id}'
            )

            if not url_recepcion:
                raise UserError("Debe configurar primero las URLs de servicio (Punto 7)")

            # Marcar como listo para recepción
            request.env['ir.config_parameter'].sudo().set_param(
                f'l10n_do_edi.ready_reception_{company.id}',
                json.dumps({
                    'status': 'ready',
                    'timestamp': datetime.now().isoformat(),
                    'url': url_recepcion
                })
            )

            response = {
                'status': 'success',
                'message': 'Sistema listo para recibir e-CF de prueba',
                'punto_certificacion': 8,
                'descripcion': 'Inicio Prueba Recepción e-CF',
                'url_recepcion': url_recepcion,
                'timestamp': datetime.now().isoformat()
            }

            _logger.info("✅ PUNTO 8: Sistema preparado para recepción")
            return response

        except Exception as e:
            _logger.error(f"❌ Error en punto 8: {str(e)}")
            return {'status': 'error', 'message': str(e)}

    # ========================================================================
    # PUNTO 9 - RECEPCIÓN E-CF (MEJORADO)
    # ========================================================================

    @http.route('/fe/recepcion/api/ecf',
                type='http', auth='public', csrf=False, methods=['POST'])
    def receive_ecf_certification(self, **kwargs):
        """
        Punto 9: Recepción de e-CF con formato ARECF correcto
        """
        try:
            _logger.info("📥 PUNTO 9: Recibiendo e-CF de certificación DGII")

            # Obtener el XML del e-CF
            xml_data = request.httprequest.data

            if not xml_data:
                _logger.error("❌ No se recibió XML del e-CF")
                return Response(
                    json.dumps({'error': 'No se recibió XML'}),
                    content_type='application/json',
                    status=400
                )

            # Decodificar y parsear XML
            if isinstance(xml_data, bytes):
                xml_str = xml_data.decode('utf-8')
            else:
                xml_str = xml_data

            try:
                # Parsear el XML para extraer datos
                root = etree.fromstring(xml_str.encode('utf-8'))
                ecf_dict = xmltodict.parse(xml_str)

                # Extraer información del e-CF
                ecf_info = self._extract_ecf_info(ecf_dict)

                # Generar Acuse de Recibo según formato DGII
                arecf_xml = self._generate_arecf(ecf_info)

                # Guardar e-CF recibido
                reception_id = str(uuid.uuid4())
                request.env['ir.config_parameter'].sudo().set_param(
                    f'l10n_do_edi.ecf_received_{reception_id}',
                    json.dumps({
                        'id': reception_id,
                        'xml': xml_str,
                        'arecf': arecf_xml,
                        'fecha_recepcion': datetime.now().isoformat(),
                        'punto_certificacion': 9,
                        'ecf_info': ecf_info
                    })
                )

                _logger.info(f"✅ PUNTO 9: e-CF recibido y ARECF generado. ID: {reception_id}")

                # Retornar el ARECF
                return Response(arecf_xml, content_type='text/xml;charset=utf-8')

            except etree.XMLSyntaxError as e:
                _logger.error(f"❌ Error parseando XML: {str(e)}")
                # Generar ARECF de rechazo
                arecf_error = self._generate_arecf_error('1')  # Código 1: Error especificación
                return Response(arecf_error, content_type='text/xml;charset=utf-8')

        except Exception as e:
            _logger.error(f"❌ Error en punto 9: {str(e)}")
            return Response(
                json.dumps({'error': str(e)}),
                content_type='application/json',
                status=500
            )

    # ========================================================================
    # PUNTO 10 - INICIO PRUEBA RECEPCIÓN APROBACIÓN COMERCIAL
    # ========================================================================

    @http.route('/fe/certification/ready/approval',
                type='jsonrpc', auth='user', csrf=False, methods=['POST'])
    def start_approval_test(self, **kwargs):
        """
        Punto 10: Indicar que está listo para recibir aprobaciones comerciales
        """
        try:
            _logger.info("🚀 PUNTO 10: Iniciando prueba de recepción de aprobación comercial")

            company = request.env.company
            url_aprobacion = request.env['ir.config_parameter'].sudo().get_param(
                f'l10n_do_edi.url_aprobacion_{company.id}'
            )

            if not url_aprobacion:
                raise UserError("Debe configurar primero las URLs de servicio (Punto 7)")

            # Marcar como listo para aprobaciones
            request.env['ir.config_parameter'].sudo().set_param(
                f'l10n_do_edi.ready_approval_{company.id}',
                json.dumps({
                    'status': 'ready',
                    'timestamp': datetime.now().isoformat(),
                    'url': url_aprobacion
                })
            )

            response = {
                'status': 'success',
                'message': 'Sistema listo para recibir aprobaciones comerciales',
                'punto_certificacion': 10,
                'descripcion': 'Inicio Prueba Recepción Aprobación Comercial',
                'url_aprobacion': url_aprobacion,
                'timestamp': datetime.now().isoformat()
            }

            _logger.info("✅ PUNTO 10: Sistema preparado para aprobaciones")
            return response

        except Exception as e:
            _logger.error(f"❌ Error en punto 10: {str(e)}")
            return {'status': 'error', 'message': str(e)}

    # ========================================================================
    # PUNTO 11 - RECEPCIÓN APROBACIÓN COMERCIAL (MEJORADO)
    # ========================================================================

    @http.route('/fe/aprobacioncomercial/api/ecf',
                type='http', auth='public', csrf=False, methods=['POST'])
    def receive_commercial_approval(self, **kwargs):
        """
        Punto 11: Recepción de Aprobación/Rechazo Comercial formato ACECF
        """
        try:
            _logger.info("📥 PUNTO 11: Recibiendo aprobación comercial de DGII")

            # Obtener XML de aprobación comercial
            xml_data = request.httprequest.data

            if not xml_data:
                _logger.error("❌ No se recibió XML de aprobación comercial")
                return Response(
                    json.dumps({'error': 'No se recibió XML', 'status': 'Error'}),
                    content_type='application/json',
                    status=400
                )

            if isinstance(xml_data, bytes):
                xml_str = xml_data.decode('utf-8')
            else:
                xml_str = xml_data

            try:
                # Parsear ACECF
                root = etree.fromstring(xml_str.encode('utf-8'))
                acecf_dict = xmltodict.parse(xml_str)

                # Extraer información de la aprobación
                acecf_info = self._extract_acecf_info(acecf_dict)

                # Validar coherencia con e-CF original
                validation_result = self._validate_acecf(acecf_info)

                # Guardar aprobación comercial
                approval_id = str(uuid.uuid4())
                request.env['ir.config_parameter'].sudo().set_param(
                    f'l10n_do_edi.approval_received_{approval_id}',
                    json.dumps({
                        'id': approval_id,
                        'xml': xml_str,
                        'fecha_recepcion': datetime.now().isoformat(),
                        'punto_certificacion': 11,
                        'acecf_info': acecf_info,
                        'validation': validation_result
                    })
                )

                # Respuesta según formato DGII
                if validation_result['valid']:
                    response_status = "OK"
                    _logger.info(f"✅ PUNTO 11: Aprobación comercial procesada. ID: {approval_id}")
                else:
                    response_status = "Error"
                    _logger.error(f"❌ PUNTO 11: Error en aprobación: {validation_result['message']}")

                response = {
                    'status': response_status,
                    'id': approval_id,
                    'punto_certificacion': 11,
                    'timestamp': datetime.now().isoformat()
                }

                return Response(
                    json.dumps(response),
                    content_type='application/json'
                )

            except etree.XMLSyntaxError as e:
                _logger.error(f"❌ Error parseando XML ACECF: {str(e)}")
                return Response(
                    json.dumps({'status': 'Error', 'message': 'XML mal formado'}),
                    content_type='application/json',
                    status=400
                )

        except Exception as e:
            _logger.error(f"❌ Error en punto 11: {str(e)}")
            return Response(
                json.dumps({'status': 'Error', 'message': str(e)}),
                content_type='application/json',
                status=500
            )

    # ========================================================================
    # PUNTO 12 - URL SERVICIOS PRODUCCIÓN
    # ========================================================================

    @http.route('/fe/certification/urls/production',
                type='jsonrpc', auth='user', csrf=False, methods=['POST'])
    def update_production_urls(self, **kwargs):
        """
        Punto 12: Configurar URLs de servicios de producción
        """
        try:
            _logger.info("📝 PUNTO 12: Configurando URLs de servicios de producción")

            company = request.env.company

            # URLs de producción
            production_urls = {
                'url_recepcion_prod': kwargs.get('url_recepcion', '/fe/recepcion/api/ecf'),
                'url_aprobacion_prod': kwargs.get('url_aprobacion', '/fe/aprobacioncomercial/api/ecf'),
                'url_autenticacion_prod': kwargs.get('url_autenticacion', '/fe/autenticacion/api/semilla'),
                'ambiente': 'produccion',
                'fecha_configuracion': datetime.now().isoformat()
            }

            # Guardar URLs de producción
            for key, value in production_urls.items():
                request.env['ir.config_parameter'].sudo().set_param(
                    f'l10n_do_edi.{key}_{company.id}',
                    value
                )

            # Marcar certificación como completada
            request.env['ir.config_parameter'].sudo().set_param(
                f'l10n_do_edi.certification_completed_{company.id}',
                json.dumps({
                    'completed': True,
                    'fecha': datetime.now().isoformat(),
                    'urls_produccion': production_urls
                })
            )

            response = {
                'status': 'success',
                'message': 'URLs de producción configuradas. Certificación completada.',
                'punto_certificacion': 12,
                'descripcion': 'URL Servicios Producción',
                'urls': production_urls,
                'certificacion_completada': True
            }

            _logger.info(f"✅ PUNTO 12 completado: Certificación finalizada")
            return response

        except Exception as e:
            _logger.error(f"❌ Error en punto 12: {str(e)}")
            return {'status': 'error', 'message': str(e)}

    # ========================================================================
    # MÉTODOS AUXILIARES
    # ========================================================================

    def _extract_ecf_info(self, ecf_dict):
        """Extrae información relevante del e-CF"""
        try:
            # Buscar el nodo ECF principal
            ecf = ecf_dict.get('ECF', {})
            encabezado = ecf.get('Encabezado', {})
            emisor = encabezado.get('Emisor', {})
            comprador = encabezado.get('Comprador', {})

            return {
                'rnc_emisor': emisor.get('RNCEmisor', ''),
                'rnc_comprador': comprador.get('RNCComprador', ''),
                'encf': encabezado.get('IndicadorEnvioDGII', {}).get('eNCF', ''),
                'fecha_emision': encabezado.get('FechaEmision', ''),
                'monto_total': encabezado.get('TotalFactura', {}).get('MontoGravadoTotal', 0)
            }
        except:
            return {}

    def _extract_acecf_info(self, acecf_dict):
        """Extrae información del ACECF"""
        try:
            acecf = acecf_dict.get('ACECF', {})
            detalle = acecf.get('DetalleAprobacionComercial', {})

            return {
                'rnc_emisor': detalle.get('RNCEmisor', ''),
                'encf': detalle.get('eNCF', ''),
                'fecha_emision': detalle.get('FechaEmision', ''),
                'monto_total': detalle.get('MontoTotal', 0),
                'rnc_comprador': detalle.get('RNCComprador', ''),
                'estado': detalle.get('Estado', ''),
                'motivo_rechazo': detalle.get('DetalleMotivoRechazo', '')
            }
        except:
            return {}

    def _generate_arecf(self, ecf_info, estado='0', codigo_motivo=''):
        """Genera el XML de Acuse de Recibo (ARECF) según formato DGII"""

        # Obtener datos de la compañía
        company = request.env.company if request.env else None
        rnc_receptor = company.vat if company else '000000000'

        fecha_actual = datetime.now()

        arecf_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<ARECF xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <DetalleAcusedeRecibo>
        <Version>1.0</Version>
        <RNCEmisor>{ecf_info.get('rnc_emisor', '000000000')}</RNCEmisor>
        <RNCComprador>{rnc_receptor}</RNCComprador>
        <eNCF>{ecf_info.get('encf', 'E000000000000000000')}</eNCF>
        <Estado>{estado}</Estado>
        <CodigoMotivoNoRecibido>{codigo_motivo}</CodigoMotivoNoRecibido>
        <FechaHoraAcuseRecibo>{fecha_actual.strftime('%d-%m-%Y %H:%M:%S')}</FechaHoraAcuseRecibo>
    </DetalleAcusedeRecibo>
</ARECF>"""

        return arecf_xml

    def _generate_arecf_error(self, codigo_error='1'):
        """Genera ARECF de error/rechazo"""
        fecha_actual = datetime.now()

        # Códigos de error:
        # 1: Error en especificación
        # 2: Error en firma digital
        # 3: Documento duplicado
        # 4: RNC no corresponde

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<ARECF xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <DetalleAcusedeRecibo>
        <Version>1.0</Version>
        <RNCEmisor>000000000</RNCEmisor>
        <RNCComprador>000000000</RNCComprador>
        <eNCF>E000000000000000000</eNCF>
        <Estado>1</Estado>
        <CodigoMotivoNoRecibido>{codigo_error}</CodigoMotivoNoRecibido>
        <FechaHoraAcuseRecibo>{fecha_actual.strftime('%d-%m-%Y %H:%M:%S')}</FechaHoraAcuseRecibo>
    </DetalleAcusedeRecibo>
</ARECF>"""

    def _validate_acecf(self, acecf_info):
        """Valida la coherencia del ACECF con el e-CF original"""
        try:
            # Aquí deberías buscar el e-CF original y validar
            # Por ahora retornamos validación básica

            if not acecf_info.get('rnc_emisor'):
                return {'valid': False, 'message': 'RNC emisor faltante'}

            if not acecf_info.get('encf'):
                return {'valid': False, 'message': 'e-NCF faltante'}

            if not acecf_info.get('monto_total'):
                return {'valid': False, 'message': 'Monto total faltante'}

            return {'valid': True, 'message': 'Validación exitosa'}

        except Exception as e:
            return {'valid': False, 'message': str(e)}

    # ========================================================================
    # ENDPOINT DE MONITOREO Y ESTADO
    # ========================================================================

    @http.route('/fe/certification/status',
                type='http', auth='public', csrf=False, methods=['GET'])
    def certification_status(self, **kwargs):
        """
        Muestra el estado actual del proceso de certificación
        """
        try:
            company_id = request.env.company.id if request.env.company else 1

            # Verificar estado de cada punto
            puntos_status = {}

            # Punto 7
            url_recepcion = request.env['ir.config_parameter'].sudo().get_param(
                f'l10n_do_edi.url_recepcion_{company_id}'
            )
            puntos_status['punto_7'] = 'completado' if url_recepcion else 'pendiente'

            # Punto 8
            ready_reception = request.env['ir.config_parameter'].sudo().get_param(
                f'l10n_do_edi.ready_reception_{company_id}'
            )
            puntos_status['punto_8'] = 'completado' if ready_reception else 'pendiente'

            # Punto 10
            ready_approval = request.env['ir.config_parameter'].sudo().get_param(
                f'l10n_do_edi.ready_approval_{company_id}'
            )
            puntos_status['punto_10'] = 'completado' if ready_approval else 'pendiente'

            # Punto 12
            certification = request.env['ir.config_parameter'].sudo().get_param(
                f'l10n_do_edi.certification_completed_{company_id}'
            )
            puntos_status['punto_12'] = 'completado' if certification else 'pendiente'

            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Estado Certificación DGII</title>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        .punto {{ margin: 20px 0; padding: 15px; border-left: 4px solid #3498db; background: #ecf0f1; }}
        .completado {{ border-left-color: #27ae60; background: #d4edda; }}
        .pendiente {{ border-left-color: #e74c3c; background: #f8d7da; }}
        .titulo {{ font-weight: bold; font-size: 16px; color: #2c3e50; }}
        .descripcion {{ color: #7f8c8d; margin-top: 5px; }}
        .endpoint {{ font-family: monospace; background: #34495e; color: #ecf0f1; padding: 5px 10px; border-radius: 3px; }}
        .status {{ float: right; padding: 5px 10px; border-radius: 3px; color: white; font-weight: bold; }}
        .status.completado {{ background: #27ae60; }}
        .status.pendiente {{ background: #e74c3c; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🏢 Estado de Certificación DGII - Puntos 7-12</h1>

        <div class="punto {puntos_status['punto_7']}">
            <span class="status {puntos_status['punto_7']}">{puntos_status['punto_7'].upper()}</span>
            <div class="titulo">Punto 7: URL Servicios Prueba</div>
            <div class="descripcion">Configuración de URLs de servicios para certificación</div>
            <div>Endpoint: <span class="endpoint">POST /fe/certification/urls/update</span></div>
        </div>

        <div class="punto {puntos_status['punto_8']}">
            <span class="status {puntos_status['punto_8']}">{puntos_status['punto_8'].upper()}</span>
            <div class="titulo">Punto 8: Inicio Prueba Recepción e-CF</div>
            <div class="descripcion">Indicar disponibilidad para recibir e-CF de prueba</div>
            <div>Endpoint: <span class="endpoint">POST /fe/certification/ready/reception</span></div>
        </div>

        <div class="punto">
            <div class="titulo">Punto 9: Recepción e-CF</div>
            <div class="descripcion">Recibir y procesar e-CF con generación de ARECF</div>
            <div>Endpoint: <span class="endpoint">POST /fe/recepcion/api/ecf</span></div>
        </div>

        <div class="punto {puntos_status['punto_10']}">
            <span class="status {puntos_status['punto_10']}">{puntos_status['punto_10'].upper()}</span>
            <div class="titulo">Punto 10: Inicio Prueba Recepción Aprobación Comercial</div>
            <div class="descripcion">Indicar disponibilidad para recibir aprobaciones comerciales</div>
            <div>Endpoint: <span class="endpoint">POST /fe/certification/ready/approval</span></div>
        </div>

        <div class="punto">
            <div class="titulo">Punto 11: Recepción Aprobación Comercial</div>
            <div class="descripcion">Recibir y procesar ACECF (aprobaciones/rechazos)</div>
            <div>Endpoint: <span class="endpoint">POST /fe/aprobacioncomercial/api/ecf</span></div>
        </div>

        <div class="punto {puntos_status['punto_12']}">
            <span class="status {puntos_status['punto_12']}">{puntos_status['punto_12'].upper()}</span>
            <div class="titulo">Punto 12: URL Servicios Producción</div>
            <div class="descripcion">Configuración de URLs para ambiente de producción</div>
            <div>Endpoint: <span class="endpoint">POST /fe/certification/urls/production</span></div>
        </div>

        <hr style="margin: 30px 0; border: none; border-top: 1px solid #ecf0f1;">

        <h2>📊 Endpoints Disponibles</h2>
        <ul>
            <li><strong>Autenticación:</strong> /fe/autenticacion/api/semilla</li>
            <li><strong>Validación:</strong> /fe/autenticacion/api/ValidacionCertificado</li>
            <li><strong>Recepción e-CF:</strong> /fe/recepcion/api/ecf</li>
            <li><strong>Aprobación Comercial:</strong> /fe/aprobacioncomercial/api/ecf</li>
            <li><strong>Estado:</strong> /fe/status</li>
        </ul>

        <p style="text-align: center; color: #7f8c8d; margin-top: 30px;">
            <em>Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</em>
        </p>
    </div>
</body>
</html>
"""
            return Response(html_content, content_type='text/html')

        except Exception as e:
            _logger.error(f"❌ Error mostrando estado: {str(e)}")
            return Response(
                json.dumps({'error': str(e)}),
                content_type='application/json',
                status=500
            )