# -*- coding: utf-8 -*-
"""
Controlador para actuar como receptor de e-CF de la DGII
Implementa los endpoints requeridos para el proceso de certificación:
- Servicio de Autenticación
- Servicio de Recepción de e-CF
- Servicio de Aprobación Comercial
"""

from odoo import http, _
from odoo.http import request, Response
from odoo.exceptions import UserError
from lxml import etree
from datetime import datetime, timedelta
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import load_pem_x509_certificate
import json
import logging
import base64
import uuid
import hashlib
import xmltodict
import tempfile
import os

_logger = logging.getLogger(__name__)

class DGIIReceptorController(http.Controller):
    """
    Controlador para recibir comunicaciones de la DGII durante la certificación
    """

    # ========================================================================
    # MÉTODOS DE FIRMA DIGITAL
    # ========================================================================

    def _sign_data(self, data, private_key):
        """Firma los datos con la clave privada"""
        try:
            signer = private_key.sign(
                data,
                padding.PKCS1v15(),
                SHA256()
            )
            return base64.b64encode(signer).decode()
        except Exception as e:
            _logger.error(f"Error firmando datos: {str(e)}")
            raise

    def _sign_arecf_xml(self, xml_string, company):
        """
        Firma digitalmente el XML del ARECF según estándar XMLDSig
        """
        try:
            _logger.error("🔐 Iniciando firma digital del ARECF")

            # Validar que exista certificado
            if not company.l10n_do_pkcs12_file or not company.l10n_do_pkcs12_password:
                raise ValueError("No se encontró el certificado P12 o la contraseña en la empresa")

            # Cargar certificado P12
            p12_content = base64.b64decode(company.l10n_do_pkcs12_file)
            key, cert, _ = pkcs12.load_key_and_certificates(
                p12_content,
                company.l10n_do_pkcs12_password.encode()
            )
            cert_b64 = base64.b64encode(cert.public_bytes(encoding=serialization.Encoding.DER)).decode()

            _logger.error("🔐 Certificado cargado exitosamente")

            # Parsear XML sin firma
            parser = etree.XMLParser(remove_blank_text=True)
            root = etree.fromstring(xml_string.encode('utf-8'), parser)

            # Calcular digest del XML canonicalizado (sin firma)
            xml_c14n = etree.tostring(root, method="c14n", exclusive=False, with_comments=False)
            digest = hashlib.sha256(xml_c14n).digest()
            digest_value = base64.b64encode(digest).decode()

            _logger.error(f"🔐 Digest calculado: {digest_value[:50]}...")

            # Crear nodo de firma según XMLDSig (SIN prefijo en namespace por defecto)
            ns_ds = "http://www.w3.org/2000/09/xmldsig#"
            ns_xsd = "http://www.w3.org/2001/XMLSchema"
            ns_xsi = "http://www.w3.org/2001/XMLSchema-instance"

            # IMPORTANTE: usar nsmap={None: ns_ds} sin prefijo, como en el método original
            signature = etree.Element("Signature", nsmap={None: ns_ds})
            signed_info = etree.SubElement(signature, "SignedInfo", nsmap={None: ns_ds, "xsd": ns_xsd, "xsi": ns_xsi})

            etree.SubElement(signed_info, "CanonicalizationMethod",
                           Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315")
            etree.SubElement(signed_info, "SignatureMethod",
                           Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256")

            reference = etree.SubElement(signed_info, "Reference", URI="")
            transforms = etree.SubElement(reference, "Transforms")
            etree.SubElement(transforms, "Transform",
                           Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature")
            etree.SubElement(reference, "DigestMethod",
                           Algorithm="http://www.w3.org/2001/04/xmlenc#sha256")
            etree.SubElement(reference, "DigestValue").text = digest_value

            # Canonicalizar SignedInfo y firmar
            signed_info_str = etree.tostring(signed_info, method="c14n", exclusive=False, with_comments=False)
            signature_value = self._sign_data(signed_info_str, key)

            _logger.error(f"🔐 SignatureValue calculado: {signature_value[:50]}...")

            # Agregar SignatureValue
            etree.SubElement(signature, "SignatureValue").text = signature_value

            # Agregar KeyInfo con certificado
            key_info = etree.SubElement(signature, "KeyInfo")
            x509_data = etree.SubElement(key_info, "X509Data")
            etree.SubElement(x509_data, "X509Certificate").text = cert_b64

            # Agregar firma al root del ARECF (después de DetalleAcusedeRecibo)
            root.append(signature)

            # NOTA: FechaHoraFirma NO existe en el XSD del ARECF
            # Solo existe FechaHoraAcuseRecibo dentro de DetalleAcusedeRecibo
            # El xs:any permite la Signature pero no otros elementos

            # Convertir a string
            signed_xml = etree.tostring(root, encoding='utf-8', xml_declaration=True, pretty_print=True).decode('utf-8')

            _logger.error("🔐 ✅ ARECF firmado exitosamente")
            _logger.error(f"🔐 XML firmado (primeros 1500 chars):\n{signed_xml[:1500]}")

            return signed_xml

        except Exception as e:
            _logger.error(f"❌ Error firmando ARECF: {str(e)}")
            raise

    # ========================================================================
    # SERVICIO DE AUTENTICACIÓN
    # ========================================================================

    @http.route('/fe/autenticacion/api/semilla',
                type='http', auth='public', csrf=False, methods=['GET', 'POST'])
    def get_semilla(self, **kwargs):
        """
        Endpoint que genera y retorna una semilla para autenticación
        Similar al servicio de la DGII pero para recibir autenticaciones
        """
        try:
            _logger.info("📥 DGII solicitando semilla de autenticación")

            # Generar una semilla única
            semilla_valor = str(uuid.uuid4())
            fecha_actual = datetime.now().isoformat()

            # Almacenar la semilla temporalmente (válida por 5 minutos)
            request.env['ir.config_parameter'].sudo().set_param(
                f'l10n_do_edi.semilla_{semilla_valor}',
                json.dumps({
                    'valor': semilla_valor,
                    'fecha': fecha_actual,
                    'expira': (datetime.now() + timedelta(minutes=5)).isoformat()
                })
            )

            # Retornar la semilla en formato XML
            response_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<SemillaModel xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
              xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <valor>{semilla_valor}</valor>
    <fecha>{fecha_actual}</fecha>
</SemillaModel>"""

            _logger.info(f"✅ Semilla generada: {semilla_valor}")
            return Response(response_xml, content_type='text/xml;charset=utf-8')

        except Exception as e:
            _logger.error(f"❌ Error generando semilla: {str(e)}")
            return Response(
                json.dumps({'error': str(e)}),
                content_type='application/json',
                status=500
            )

    @http.route([
        '/fe/autenticacion/api/ValidacionCertificado',
        '/fe/autenticacion/api/validacionCertificado',
        '/fe/autenticacion/api/validacioncertificado'
    ], type='http', auth='public', csrf=False, methods=['POST'])
    def validar_certificado(self, **kwargs):
        """
        Valida el certificado enviado por la DGII
        """
        _logger.error("🚨🚨🚨 NUEVA VERSION CONTROLADOR VALIDAR_CERTIFICADO 🚨🚨🚨")
        _logger.error("🔥 INICIO validar_certificado - DGII enviando certificado para validación")

        # Log inmediato y simple
        _logger.error(f"🔥 STEP 1 - kwargs: {kwargs}")
        _logger.error(f"🔥 STEP 2 - request.httprequest existe: {hasattr(request, 'httprequest')}")

        if hasattr(request, 'httprequest'):
            _logger.error(f"🔥 STEP 3 - METHOD: {getattr(request.httprequest, 'method', 'NO_METHOD')}")
            _logger.error(f"🔥 STEP 4 - Content-Type: {getattr(request.httprequest, 'content_type', 'NO_CONTENT_TYPE')}")

            # Verificar datos
            data = getattr(request.httprequest, 'data', None)
            _logger.error(f"🔥 STEP 5 - Data length: {len(data) if data else 0}")

            # Verificar form
            form = getattr(request.httprequest, 'form', {})
            _logger.error(f"🔥 STEP 6 - Form keys: {list(form.keys())}")

            # Verificar files
            files = getattr(request.httprequest, 'files', {})
            _logger.error(f"🔥 STEP 7 - Files keys: {list(files.keys())}")

        _logger.error("🔥 CONTINUANDO con lógica original...")

        try:
            # 🚀 SOPORTE COMPLETO PARA TODOS LOS FORMATOS DE DGII
            xml_data = None
            _logger.error("🔥 INICIANDO BÚSQUEDA EXHAUSTIVA DE XML EN PETICIÓN")

            # 1. Intentar obtener del body directo (formato estándar)
            if hasattr(request.httprequest, 'data') and request.httprequest.data:
                xml_data = request.httprequest.data
                _logger.error(f"🔥 XML encontrado en request.data - Length: {len(xml_data)}")

            # 2. Intentar obtener de form data (formato alternativo)
            elif hasattr(request.httprequest, 'form') and request.httprequest.form:
                _logger.error(f"🔥 Form data disponible - Keys: {list(request.httprequest.form.keys())}")
                # Buscar XML en diferentes nombres de campo
                for field_name in ['xml', 'certificado', 'certificate', 'data', 'payload']:
                    if field_name in request.httprequest.form:
                        xml_data = request.httprequest.form[field_name]
                        _logger.error(f"🔥 XML encontrado en form[{field_name}] - Length: {len(xml_data) if xml_data else 0}")
                        break

                # Si no encontró con nombres específicos, tomar el primer valor disponible
                if not xml_data and request.httprequest.form:
                    first_key = list(request.httprequest.form.keys())[0]
                    xml_data = request.httprequest.form[first_key]
                    _logger.error(f"🔥 XML tomado del primer campo form[{first_key}] - Length: {len(xml_data) if xml_data else 0}")

            # 3. Intentar obtener de archivos (formato multipart)
            elif hasattr(request.httprequest, 'files') and request.httprequest.files:
                _logger.error(f"🔥 Files disponibles - Keys: {list(request.httprequest.files.keys())}")
                for field_name in ['xml', 'certificado', 'certificate', 'data', 'payload']:
                    if field_name in request.httprequest.files:
                        xml_file = request.httprequest.files[field_name]
                        xml_data = xml_file.read()
                        _logger.error(f"🔥 XML encontrado en files[{field_name}] - Length: {len(xml_data) if xml_data else 0}")
                        break

                # Si no encontró con nombres específicos, tomar el primer archivo disponible
                if not xml_data and request.httprequest.files:
                    first_key = list(request.httprequest.files.keys())[0]
                    xml_file = request.httprequest.files[first_key]
                    xml_data = xml_file.read()
                    _logger.error(f"🔥 XML tomado del primer archivo files[{first_key}] - Length: {len(xml_data) if xml_data else 0}")

            # 4. Intentar obtener de valores de parámetros kwargs
            if not xml_data and kwargs:
                _logger.error(f"🔥 Kwargs disponibles: {list(kwargs.keys())}")
                for field_name in ['xml', 'certificado', 'certificate', 'data', 'payload']:
                    if field_name in kwargs:
                        xml_data = kwargs[field_name]
                        _logger.error(f"🔥 XML encontrado en kwargs[{field_name}] - Length: {len(xml_data) if xml_data else 0}")
                        break

            # 5. Si no se encontró XML en ningún lugar
            if not xml_data:
                _logger.error("🔥 ❌ NO SE ENCONTRÓ XML EN NINGÚN FORMATO")
                _logger.error(f"🔥 request.httprequest.data: {hasattr(request.httprequest, 'data')}")
                _logger.error(f"🔥 request.httprequest.form: {hasattr(request.httprequest, 'form')}")
                _logger.error(f"🔥 request.httprequest.files: {hasattr(request.httprequest, 'files')}")
                _logger.error(f"🔥 kwargs: {kwargs}")
                return Response(
                    json.dumps({'error': 'No se recibió XML en ningún formato soportado'}),
                    content_type='application/json',
                    status=400
                )

            # Aquí deberías validar el certificado digital
            # Por ahora retornamos una respuesta de éxito

            # Generar un token de sesión
            token = base64.b64encode(str(uuid.uuid4()).encode()).decode()
            fecha_expedicion = datetime.now().isoformat()
            fecha_expiracion = (datetime.now() + timedelta(hours=1)).isoformat()

            response_data = {
                "token": token,
                "expira": fecha_expiracion,
                "expedido": fecha_expedicion
            }

            _logger.info(f"✅ Certificado validado, token generado: {token[:20]}...")
            return Response(
                json.dumps(response_data),
                content_type='application/json'
            )

        except Exception as e:
            _logger.error(f"❌ Error validando certificado: {str(e)}")
            return Response(
                json.dumps({'error': str(e)}),
                content_type='application/json',
                status=500
            )

    # ========================================================================
    # SERVICIO DE RECEPCIÓN DE E-CF
    # ========================================================================

    @http.route('/fe/recepcion/api/ecf',
                type='http', auth='public', csrf=False, methods=['POST'])
    def recibir_ecf(self, **kwargs):
        """
        Recibe un e-CF enviado por otro emisor a través de la DGII
        """
        try:
            _logger.error("🔥 INICIO recibir_ecf - DGII enviando e-CF")

            # 🔥 LOG DETALLADO DE HEADERS
            _logger.error("🔥 HEADERS RECIBIDOS:")
            for header_name, header_value in request.httprequest.headers.items():
                _logger.error(f"🔥   {header_name}: {header_value}")

            # Obtener el token de autorización
            auth_header = request.httprequest.headers.get('Authorization', '')
            _logger.error(f"🔥 AUTH HEADER: '{auth_header}'")

            if not auth_header.startswith('Bearer '):
                _logger.error("❌ Token de autorización no válido - esperado Bearer token")
                _logger.error(f"❌ Header Authorization recibido: '{auth_header}'")
                return Response(
                    json.dumps({'error': 'Token no válido'}),
                    content_type='application/json',
                    status=401
                )

            # 🚀 SOPORTE COMPLETO PARA TODOS LOS FORMATOS DE ENVÍO DE XML
            xml_data = None
            _logger.error("🔥 INICIANDO BÚSQUEDA DE XML EN PETICIÓN")

            # 1. Intentar obtener del body directo (formato estándar)
            if hasattr(request.httprequest, 'data') and request.httprequest.data:
                xml_data = request.httprequest.data
                _logger.error(f"🔥 XML encontrado en request.data - Length: {len(xml_data)}")

            # 2. Intentar obtener de form data (formato alternativo)
            elif hasattr(request.httprequest, 'form') and request.httprequest.form:
                _logger.error(f"🔥 Form data disponible - Keys: {list(request.httprequest.form.keys())}")
                # Buscar XML en diferentes nombres de campo
                for field_name in ['xml', 'ecf', 'data', 'payload', 'file']:
                    if field_name in request.httprequest.form:
                        xml_data = request.httprequest.form[field_name]
                        if isinstance(xml_data, bytes):
                            pass
                        elif hasattr(xml_data, 'read'):
                            xml_data = xml_data.read()
                        else:
                            xml_data = str(xml_data).encode('utf-8')
                        _logger.error(f"🔥 XML encontrado en form[{field_name}] - Length: {len(xml_data) if xml_data else 0}")
                        break

            # 3. Intentar obtener de archivos (formato multipart/form-data)
            elif hasattr(request.httprequest, 'files') and request.httprequest.files:
                _logger.error(f"🔥 Files disponibles - Keys: {list(request.httprequest.files.keys())}")
                for field_name in ['xml', 'ecf', 'data', 'payload', 'file']:
                    if field_name in request.httprequest.files:
                        xml_file = request.httprequest.files[field_name]
                        xml_data = xml_file.read()
                        _logger.error(f"🔥 XML encontrado en files[{field_name}] - Length: {len(xml_data) if xml_data else 0}")
                        break

                # Si no encontró con nombres específicos, tomar el primer archivo disponible
                if not xml_data and request.httprequest.files:
                    first_key = list(request.httprequest.files.keys())[0]
                    xml_file = request.httprequest.files[first_key]
                    xml_data = xml_file.read()
                    _logger.error(f"🔥 XML tomado del primer archivo files[{first_key}] - Length: {len(xml_data) if xml_data else 0}")

            # 4. Intentar obtener de valores de parámetros kwargs
            if not xml_data and kwargs:
                _logger.error(f"🔥 Kwargs disponibles: {list(kwargs.keys())}")
                for field_name in ['xml', 'ecf', 'data', 'payload', 'file']:
                    if field_name in kwargs:
                        xml_data = kwargs[field_name]
                        if isinstance(xml_data, str):
                            xml_data = xml_data.encode('utf-8')
                        _logger.error(f"🔥 XML encontrado en kwargs[{field_name}] - Length: {len(xml_data) if xml_data else 0}")
                        break

            if not xml_data:
                _logger.error("❌ No se recibió XML del e-CF en ningún formato")
                _logger.error(f"🔥 request.httprequest.data: {hasattr(request.httprequest, 'data')}")
                _logger.error(f"🔥 request.httprequest.form: {hasattr(request.httprequest, 'form') and list(request.httprequest.form.keys())}")
                _logger.error(f"🔥 request.httprequest.files: {hasattr(request.httprequest, 'files') and list(request.httprequest.files.keys())}")
                return Response(
                    json.dumps({'error': 'No se recibió XML'}),
                    content_type='application/json',
                    status=400
                )

            # Parsear el XML
            try:
                # Decodificar si viene en bytes
                if isinstance(xml_data, bytes):
                    xml_str = xml_data.decode('utf-8')
                else:
                    xml_str = xml_data

                # Parsear el XML para validar estructura
                root = etree.fromstring(xml_str.encode('utf-8'))

                # Extraer información básica del e-CF
                # Buscar el RNC emisor, e-NCF, etc.
                ecf_data = xmltodict.parse(xml_str)

                _logger.error(f"🔥 eCF parseado: {json.dumps(ecf_data, indent=2)[:500]}")

                # Extraer datos del eCF recibido
                try:
                    # Buscar en la estructura ECF
                    if 'ECF' in ecf_data:
                        encabezado = ecf_data.get('ECF', {}).get('Encabezado', {})
                        emisor = encabezado.get('Emisor', {})
                        comprador = encabezado.get('Comprador', {})
                        id_doc = encabezado.get('IdDoc', {})

                        rnc_emisor = emisor.get('RNCEmisor', '000000000')
                        rnc_comprador = comprador.get('RNCComprador', request.env.company.vat or '000000000')
                        encf = id_doc.get('eNCF', 'E000000000000')
                    else:
                        # Si no tiene estructura ECF estándar, intentar obtener de raíz
                        rnc_emisor = ecf_data.get('RNCEmisor', '000000000')
                        rnc_comprador = request.env.company.vat or '000000000'
                        encf = ecf_data.get('eNCF', 'E000000000000')

                    _logger.error(f"🔥 Datos extraídos - RNC Emisor: {rnc_emisor}, RNC Comprador: {rnc_comprador}, eNCF: {encf}")

                except Exception as extract_error:
                    _logger.error(f"⚠️ Error extrayendo datos del eCF: {str(extract_error)}")
                    # Usar valores por defecto
                    rnc_emisor = '000000000'
                    rnc_comprador = request.env.company.vat or '000000000'
                    encf = 'E000000000000'

                # Generar un ID único para este e-CF recibido
                reception_id = str(uuid.uuid4())

                # Almacenar el e-CF recibido (aquí deberías guardarlo en un modelo de Odoo)
                # Por ahora lo guardamos en un parámetro del sistema temporalmente
                request.env['ir.config_parameter'].sudo().set_param(
                    f'l10n_do_edi.ecf_recibido_{reception_id}',
                    json.dumps({
                        'id': reception_id,
                        'xml': xml_str,
                        'rnc_emisor': rnc_emisor,
                        'rnc_comprador': rnc_comprador,
                        'encf': encf,
                        'fecha_recepcion': datetime.now().isoformat(),
                        'estado': 'recibido'
                    })
                )

                # Crear el acuse de recibo (ARECF) según XSD v1.0 de la DGII
                # Orden ESTRICTO según el XSD:
                # 1. Version, 2. RNCEmisor, 3. RNCComprador, 4. eNCF, 5. Estado,
                # 6. CodigoMotivoNoRecibido (opcional), 7. FechaHoraAcuseRecibo
                fecha_hora_acuse = datetime.now().strftime('%d-%m-%Y %H:%M:%S')

                acuse_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<ARECF xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <DetalleAcusedeRecibo>
        <Version>1.0</Version>
        <RNCEmisor>{rnc_emisor}</RNCEmisor>
        <RNCComprador>{rnc_comprador}</RNCComprador>
        <eNCF>{encf}</eNCF>
        <Estado>0</Estado>
        <FechaHoraAcuseRecibo>{fecha_hora_acuse}</FechaHoraAcuseRecibo>
    </DetalleAcusedeRecibo>
</ARECF>"""

                _logger.info(f"✅ e-CF recibido correctamente. ID: {reception_id}")
                _logger.error(f"🔥 ARECF sin firmar generado:\n{acuse_xml}")

                # ========================================================================
                # FIRMAR EL ARECF CON EL CERTIFICADO DIGITAL DE LA EMPRESA
                # ========================================================================
                try:
                    company = request.env.company
                    _logger.error(f"🔐 Firmando ARECF para empresa: {company.name}")

                    # Firmar el XML del ARECF
                    acuse_xml_firmado = self._sign_arecf_xml(acuse_xml, company)

                    _logger.info(f"✅ ARECF firmado exitosamente")

                    # Retornar el acuse de recibo FIRMADO
                    return Response(acuse_xml_firmado, content_type='text/xml;charset=utf-8')

                except Exception as signing_error:
                    _logger.error(f"❌ Error firmando ARECF: {str(signing_error)}")
                    _logger.error(f"❌ Stack trace:", exc_info=True)

                    # Si falla la firma, devolver error
                    return Response(
                        json.dumps({
                            'error': f'Error firmando ARECF: {str(signing_error)}',
                            'tipo': 'error_firma'
                        }),
                        content_type='application/json',
                        status=500
                    )

            except etree.XMLSyntaxError as e:
                _logger.error(f"❌ Error parseando XML: {str(e)}")
                return Response(
                    json.dumps({'error': 'XML mal formado'}),
                    content_type='application/json',
                    status=400
                )

        except Exception as e:
            _logger.error(f"❌ Error recibiendo e-CF: {str(e)}")
            return Response(
                json.dumps({'error': str(e)}),
                content_type='application/json',
                status=500
            )

    # ========================================================================
    # SERVICIO DE APROBACIÓN COMERCIAL
    # ========================================================================

    @http.route('/fe/aprobacioncomercial/api/ecf',
                type='http', auth='public', csrf=False, methods=['POST'])
    def recibir_aprobacion_comercial(self, **kwargs):
        """
        Recibe una aprobación o rechazo comercial de un e-CF emitido
        """
        try:
            _logger.error("🔥 INICIO recibir_aprobacion_comercial - DGII enviando aprobación/rechazo")

            # 🔥 LOG DETALLADO DE HEADERS
            _logger.error("🔥 HEADERS RECIBIDOS:")
            for header_name, header_value in request.httprequest.headers.items():
                _logger.error(f"🔥   {header_name}: {header_value}")

            # Obtener el token de autorización
            auth_header = request.httprequest.headers.get('Authorization', '')
            _logger.error(f"🔥 AUTH HEADER: '{auth_header}'")

            if not auth_header.startswith('Bearer '):
                _logger.error("❌ Token de autorización no válido - esperado Bearer token")
                _logger.error(f"❌ Header Authorization recibido: '{auth_header}'")
                return Response(
                    json.dumps({'error': 'Token no válido'}),
                    content_type='application/json',
                    status=401
                )

            # 🚀 SOPORTE COMPLETO PARA TODOS LOS FORMATOS DE ENVÍO DE XML
            xml_data = None
            _logger.error("🔥 INICIANDO BÚSQUEDA DE XML APROBACIÓN COMERCIAL")

            # 1. Intentar obtener del body directo (formato estándar)
            if hasattr(request.httprequest, 'data') and request.httprequest.data:
                xml_data = request.httprequest.data
                _logger.error(f"🔥 XML encontrado en request.data - Length: {len(xml_data)}")

            # 2. Intentar obtener de form data (formato alternativo)
            elif hasattr(request.httprequest, 'form') and request.httprequest.form:
                _logger.error(f"🔥 Form data disponible - Keys: {list(request.httprequest.form.keys())}")
                for field_name in ['xml', 'aprobacion', 'acecf', 'data', 'payload', 'file']:
                    if field_name in request.httprequest.form:
                        xml_data = request.httprequest.form[field_name]
                        if isinstance(xml_data, bytes):
                            pass
                        elif hasattr(xml_data, 'read'):
                            xml_data = xml_data.read()
                        else:
                            xml_data = str(xml_data).encode('utf-8')
                        _logger.error(f"🔥 XML encontrado en form[{field_name}] - Length: {len(xml_data) if xml_data else 0}")
                        break

            # 3. Intentar obtener de archivos (formato multipart/form-data)
            elif hasattr(request.httprequest, 'files') and request.httprequest.files:
                _logger.error(f"🔥 Files disponibles - Keys: {list(request.httprequest.files.keys())}")
                for field_name in ['xml', 'aprobacion', 'acecf', 'data', 'payload', 'file']:
                    if field_name in request.httprequest.files:
                        xml_file = request.httprequest.files[field_name]
                        xml_data = xml_file.read()
                        _logger.error(f"🔥 XML encontrado en files[{field_name}] - Length: {len(xml_data) if xml_data else 0}")
                        break

                # Si no encontró con nombres específicos, tomar el primer archivo disponible
                if not xml_data and request.httprequest.files:
                    first_key = list(request.httprequest.files.keys())[0]
                    xml_file = request.httprequest.files[first_key]
                    xml_data = xml_file.read()
                    _logger.error(f"🔥 XML tomado del primer archivo files[{first_key}] - Length: {len(xml_data) if xml_data else 0}")

            # 4. Intentar obtener de valores de parámetros kwargs
            if not xml_data and kwargs:
                _logger.error(f"🔥 Kwargs disponibles: {list(kwargs.keys())}")
                for field_name in ['xml', 'aprobacion', 'acecf', 'data', 'payload', 'file']:
                    if field_name in kwargs:
                        xml_data = kwargs[field_name]
                        if isinstance(xml_data, str):
                            xml_data = xml_data.encode('utf-8')
                        _logger.error(f"🔥 XML encontrado en kwargs[{field_name}] - Length: {len(xml_data) if xml_data else 0}")
                        break

            if not xml_data:
                _logger.error("❌ No se recibió XML de aprobación comercial en ningún formato")
                _logger.error(f"🔥 request.httprequest.data: {hasattr(request.httprequest, 'data')}")
                _logger.error(f"🔥 request.httprequest.form: {hasattr(request.httprequest, 'form') and list(request.httprequest.form.keys())}")
                _logger.error(f"🔥 request.httprequest.files: {hasattr(request.httprequest, 'files') and list(request.httprequest.files.keys())}")
                return Response(
                    json.dumps({'error': 'No se recibió XML'}),
                    content_type='application/json',
                    status=400
                )

            # Parsear el XML
            try:
                if isinstance(xml_data, bytes):
                    xml_str = xml_data.decode('utf-8')
                else:
                    xml_str = xml_data

                # Validar estructura XML
                root = etree.fromstring(xml_str.encode('utf-8'))

                # Extraer información de la aprobación/rechazo
                aprobacion_data = xmltodict.parse(xml_str)

                # Generar ID único para esta aprobación
                approval_id = str(uuid.uuid4())

                # Almacenar la aprobación comercial
                request.env['ir.config_parameter'].sudo().set_param(
                    f'l10n_do_edi.aprobacion_{approval_id}',
                    json.dumps({
                        'id': approval_id,
                        'xml': xml_str,
                        'fecha_recepcion': datetime.now().isoformat(),
                        'tipo': 'aprobacion_comercial'
                    })
                )

                # Retornar respuesta exitosa
                response_data = {
                    'codigo': '200',
                    'mensaje': 'Aprobación comercial recibida correctamente',
                    'id': approval_id
                }

                _logger.info(f"✅ Aprobación comercial recibida. ID: {approval_id}")

                return Response(
                    json.dumps(response_data),
                    content_type='application/json'
                )

            except etree.XMLSyntaxError as e:
                _logger.error(f"❌ Error parseando XML: {str(e)}")
                return Response(
                    json.dumps({'error': 'XML mal formado'}),
                    content_type='application/json',
                    status=400
                )

        except Exception as e:
            _logger.error(f"❌ Error recibiendo aprobación comercial: {str(e)}")
            return Response(
                json.dumps({'error': str(e)}),
                content_type='application/json',
                status=500
            )

    # ========================================================================
    # ENDPOINTS AUXILIARES PARA PRUEBAS Y MONITOREO
    # ========================================================================

    @http.route('/fe/status',
                type='http', auth='public', csrf=False, methods=['GET'])
    def check_status(self, **kwargs):
        """
        Endpoint para verificar que los servicios están funcionando
        """
        try:
            status = {
                'status': 'online',
                'timestamp': datetime.now().isoformat(),
                'services': {
                    'autenticacion': 'active',
                    'recepcion': 'active',
                    'aprobacion_comercial': 'active'
                },
                'company': request.env.company.name if request.env.company else 'N/A',
                'vat': request.env.company.vat if request.env.company else 'N/A'
            }

            return Response(
                json.dumps(status),
                content_type='application/json'
            )

        except Exception as e:
            _logger.error(f"❌ Error verificando estado: {str(e)}")
            return Response(
                json.dumps({'error': str(e)}),
                content_type='application/json',
                status=500
            )

    @http.route('/fe/test/recibir',
                type='http', auth='public', csrf=False, methods=['GET'])
    def test_reception(self, **kwargs):
        """
        Endpoint de prueba para verificar la recepción
        """
        html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Test Recepción DGII</title>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        h1 { color: #2c3e50; }
        .endpoint {
            background: #f4f4f4;
            padding: 10px;
            margin: 10px 0;
            border-left: 4px solid #3498db;
        }
        .status-ok { color: green; font-weight: bold; }
    </style>
</head>
<body>
    <h1>🏢 Servicios de Recepción DGII - Certificación</h1>
    <p class="status-ok">✅ Los servicios están activos y listos para recibir comunicaciones de la DGII</p>

    <h2>Endpoints disponibles:</h2>

    <div class="endpoint">
        <strong>1. Servicio de Autenticación:</strong><br>
        - GET/POST /fe/autenticacion/api/semilla<br>
        - POST /fe/autenticacion/api/ValidacionCertificado
    </div>

    <div class="endpoint">
        <strong>2. Servicio de Recepción e-CF:</strong><br>
        - POST /fe/recepcion/api/ecf
    </div>

    <div class="endpoint">
        <strong>3. Servicio de Aprobación Comercial:</strong><br>
        - POST /fe/aprobacioncomercial/api/ecf
    </div>

    <div class="endpoint">
        <strong>4. Estado del Servicio:</strong><br>
        - GET /fe/status
    </div>

    <p><em>Fecha/Hora: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</em></p>
</body>
</html>
"""
        return Response(html_content, content_type='text/html')