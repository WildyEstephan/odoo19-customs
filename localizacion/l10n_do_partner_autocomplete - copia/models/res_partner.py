import re
import logging
import urllib3

import lxml.html
import requests

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Deshabilitar warnings de SSL para entornos de desarrollo
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# URL de consulta de RNC de la DGII
DGII_RNC_URL = 'https://dgii.gov.do/app/WebApps/ConsultasWeb2/ConsultasWeb/consultas/rnc.aspx'

# MODIFICADO: Arturo Diaz Lora - 2026-04-09
# Razón: Agregar API de indexa.do como fuente principal (más rápida y confiable)
# La DGII frecuentemente devuelve 504 Gateway Timeout
INDEXA_API_URL = 'https://api.indexa.do/api/rnc'

# Headers para simular navegador real
# NOTA: No usar Accept-Encoding con br (brotli) para evitar problemas de descompresión
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',  # Sin brotli (br) para evitar problemas
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
}


class Partner(models.Model):
    _inherit = "res.partner"

    @api.model
    def default_get(self, fields_list):
        """
        Intercepta la creación de un nuevo contacto para detectar si se está
        creando con un RNC/Cédula y consultar la DGII automáticamente.
        """
        res = super().default_get(fields_list)

        # Verificar si hay un RNC en el contexto (desde el campo partner_id)
        default_name = self.env.context.get('default_name', '')

        if default_name:
            # Verificar si el nombre parece ser un RNC/Cédula
            clean_vat = self._clean_vat(default_name)
            validated_vat, vat_type = self._validate_rnc_format(clean_vat)

            if validated_vat:
                _logger.debug(f"Detectado RNC en default_name: {validated_vat}")

                # Buscar si ya existe un contacto con este RNC
                do_country = self.env.ref("base.do", raise_if_not_found=False)
                if do_country:
                    existing = self.search([
                        ('vat', '=', validated_vat),
                        ('country_id', '=', do_country.id)
                    ], limit=1)

                    if existing:
                        _logger.debug(f"Contacto existente encontrado: {existing.name}")
                        # No modificar, dejar que el usuario vea el formulario vacío
                    else:
                        # Consultar la DGII
                        dgii_data = self._query_dgii_rnc(validated_vat)

                        if dgii_data and dgii_data.get('name'):
                            _logger.debug(f"Datos DGII obtenidos: {dgii_data}")

                            # Actualizar los valores por defecto
                            res['name'] = dgii_data.get('name', default_name)
                            res['vat'] = validated_vat
                            res['country_id'] = do_country.id

                            # Determinar tipo de empresa
                            if vat_type == 'cedula':
                                res['company_type'] = 'person'
                                res['is_company'] = False
                                res['l10n_do_dgii_tax_payer_type'] = 'non_payer'
                            else:
                                res['company_type'] = 'company'
                                res['is_company'] = True
                                res['l10n_do_dgii_tax_payer_type'] = 'taxpayer'

                            # Campos DGII
                            res['l10n_do_dgii_name'] = dgii_data.get('name', '')
                            res['l10n_do_dgii_commercial_name'] = dgii_data.get('l10n_do_dgii_commercial_name', '')
                            res['l10n_do_dgii_status'] = dgii_data.get('l10n_do_dgii_status', '')
                            res['l10n_do_dgii_payment_regime'] = dgii_data.get('l10n_do_dgii_payment_regime', '')
                            res['l10n_do_dgii_activity'] = dgii_data.get('l10n_do_dgii_activity', '')
                            res['l10n_do_dgii_category'] = dgii_data.get('l10n_do_dgii_category', '')
                            res['l10n_do_dgii_local_admin'] = dgii_data.get('l10n_do_dgii_local_admin', '')
                            res['l10n_do_dgii_last_update'] = fields.Datetime.now()

        return res

    @api.onchange('name')
    def _onchange_name_check_rnc(self):
        """
        Cuando el usuario escribe en el campo nombre, verifica si es un RNC/Cédula
        y consulta la DGII para autocompletar los datos.
        """
        if not self.name:
            return

        # Verificar si el nombre parece ser un RNC/Cédula (solo dígitos o con guiones)
        clean_vat = self._clean_vat(self.name)
        validated_vat, vat_type = self._validate_rnc_format(clean_vat)

        if not validated_vat:
            return

        # Si ya tiene VAT y es diferente, no hacer nada
        if self.vat and self._clean_vat(self.vat) != validated_vat:
            return

        _logger.debug(f"Detectado RNC en campo nombre: {validated_vat}")

        # Buscar si ya existe
        do_country = self.env.ref("base.do", raise_if_not_found=False)
        if do_country:
            existing = self.env['res.partner'].search([
                ('vat', '=', validated_vat),
                ('country_id', '=', do_country.id),
                ('id', '!=', self._origin.id if self._origin else 0)
            ], limit=1)

            if existing:
                return {
                    'warning': {
                        'title': _('Contacto Existente'),
                        'message': _(
                            'Ya existe un contacto con este RNC/Cédula: %s'
                        ) % existing.name
                    }
                }

        # Consultar la DGII
        dgii_data = self._query_dgii_rnc(validated_vat)

        if dgii_data and dgii_data.get('name'):
            # Actualizar campos
            self.name = dgii_data.get('name')
            self.vat = validated_vat
            self.country_id = do_country

            # Determinar tipo de empresa
            if vat_type == 'cedula':
                self.company_type = 'person'
                self.is_company = False
                if hasattr(self, 'l10n_do_dgii_tax_payer_type'):
                    self.l10n_do_dgii_tax_payer_type = 'non_payer'
            else:
                self.company_type = 'company'
                self.is_company = True
                if hasattr(self, 'l10n_do_dgii_tax_payer_type'):
                    self.l10n_do_dgii_tax_payer_type = 'taxpayer'

            # Campos DGII
            self.l10n_do_dgii_name = dgii_data.get('name', '')
            self.l10n_do_dgii_commercial_name = dgii_data.get('l10n_do_dgii_commercial_name', '')
            self.l10n_do_dgii_status = dgii_data.get('l10n_do_dgii_status', '')
            self.l10n_do_dgii_payment_regime = dgii_data.get('l10n_do_dgii_payment_regime', '')
            self.l10n_do_dgii_activity = dgii_data.get('l10n_do_dgii_activity', '')
            self.l10n_do_dgii_category = dgii_data.get('l10n_do_dgii_category', '')
            self.l10n_do_dgii_local_admin = dgii_data.get('l10n_do_dgii_local_admin', '')
            self.l10n_do_dgii_last_update = fields.Datetime.now()

            return {
                'warning': {
                    'title': _('Datos DGII Cargados'),
                    'message': _(
                        'Se encontró el contribuyente: %s\n'
                        'Estado: %s\n'
                        'Actividad: %s'
                    ) % (
                        dgii_data.get('name', 'N/A'),
                        dgii_data.get('l10n_do_dgii_status', 'N/A'),
                        dgii_data.get('l10n_do_dgii_activity', 'N/A')
                    ),
                    'type': 'notification',
                }
            }

    @api.model_create_multi
    def create(self, vals_list):
        """
        Intercepta la creación de contactos para detectar si se está creando
        con un RNC/Cédula en el nombre y consultar la DGII.
        """
        do_country = self.env.ref("base.do", raise_if_not_found=False)

        for vals in vals_list:
            name = vals.get('name', '')

            # Si ya tiene todos los datos DGII, no hacer nada
            if vals.get('l10n_do_dgii_name'):
                continue

            # Verificar si el nombre parece ser un RNC/Cédula
            clean_vat = self._clean_vat(name)
            validated_vat, vat_type = self._validate_rnc_format(clean_vat)

            if validated_vat and do_country:
                _logger.debug(f"Creando contacto con RNC detectado: {validated_vat}")

                # Verificar si ya existe
                existing = self.search([
                    ('vat', '=', validated_vat),
                    ('country_id', '=', do_country.id)
                ], limit=1)

                if not existing:
                    # Consultar la DGII
                    dgii_data = self._query_dgii_rnc(validated_vat)

                    if dgii_data and dgii_data.get('name'):
                        _logger.debug(f"Actualizando vals con datos DGII: {dgii_data}")

                        vals['name'] = dgii_data.get('name', name)
                        vals['vat'] = validated_vat
                        vals['country_id'] = do_country.id

                        # Determinar tipo de empresa
                        if vat_type == 'cedula':
                            vals['company_type'] = 'person'
                            vals['is_company'] = False
                            vals['l10n_do_dgii_tax_payer_type'] = 'non_payer'
                        else:
                            vals['company_type'] = 'company'
                            vals['is_company'] = True
                            vals['l10n_do_dgii_tax_payer_type'] = 'taxpayer'

                        # Campos DGII
                        vals['l10n_do_dgii_name'] = dgii_data.get('name', '')
                        vals['l10n_do_dgii_commercial_name'] = dgii_data.get('l10n_do_dgii_commercial_name', '')
                        vals['l10n_do_dgii_status'] = dgii_data.get('l10n_do_dgii_status', '')
                        vals['l10n_do_dgii_payment_regime'] = dgii_data.get('l10n_do_dgii_payment_regime', '')
                        vals['l10n_do_dgii_activity'] = dgii_data.get('l10n_do_dgii_activity', '')
                        vals['l10n_do_dgii_category'] = dgii_data.get('l10n_do_dgii_category', '')
                        vals['l10n_do_dgii_local_admin'] = dgii_data.get('l10n_do_dgii_local_admin', '')
                        vals['l10n_do_dgii_last_update'] = fields.Datetime.now()

        return super().create(vals_list)

    # Campos adicionales para datos de la DGII
    l10n_do_dgii_name = fields.Char(
        string="Nombre/Razón Social (DGII)",
        readonly=True,
        help="Nombre o Razón Social según registros de la DGII"
    )
    l10n_do_dgii_commercial_name = fields.Char(
        string="Nombre Comercial (DGII)",
        readonly=True,
        help="Nombre comercial registrado en la DGII"
    )
    l10n_do_dgii_status = fields.Char(
        string="Estado (DGII)",
        readonly=True,
        help="Estado del contribuyente en la DGII"
    )
    l10n_do_dgii_payment_regime = fields.Char(
        string="Régimen de Pagos",
        readonly=True,
        help="Régimen de pagos según la DGII"
    )
    l10n_do_dgii_activity = fields.Char(
        string="Actividad Económica",
        readonly=True,
        help="Actividad económica registrada en la DGII"
    )
    l10n_do_dgii_category = fields.Char(
        string="Categoría (DGII)",
        readonly=True,
        help="Categoría del contribuyente en la DGII"
    )
    l10n_do_dgii_local_admin = fields.Char(
        string="Administración Local",
        readonly=True,
        help="Administración local de la DGII"
    )
    l10n_do_dgii_last_update = fields.Datetime(
        string="Última Consulta DGII",
        readonly=True,
        help="Fecha y hora de la última consulta a la DGII"
    )

    def _clean_vat(self, vat):
        """Limpia el RNC/Cédula removiendo caracteres no numéricos."""
        if not vat:
            return ""
        return re.sub(r'[^0-9]', '', str(vat))

    def _validate_rnc_format(self, vat):
        """
        Valida el formato del RNC/Cédula dominicano.
        - RNC: 9 dígitos
        - Cédula: 11 dígitos
        """
        clean_vat = self._clean_vat(vat)
        if len(clean_vat) == 9:
            return clean_vat, 'rnc'
        elif len(clean_vat) == 11:
            return clean_vat, 'cedula'
        return None, None

    def _get_dgii_session(self):
        """Obtiene una sesión configurada para consultas a la DGII."""
        session = requests.Session()
        session.headers.update(REQUEST_HEADERS)
        # Deshabilitar verificación SSL para evitar problemas de certificados
        session.verify = False
        return session

    def _extract_form_tokens(self, document):
        """Extrae los tokens de validación del formulario ASP.NET."""
        tokens = {}

        try:
            # Método 1: Buscar con xpath estándar
            # Buscar __EVENTVALIDATION
            event_validation = document.find('.//input[@name="__EVENTVALIDATION"]')
            if event_validation is not None:
                tokens['__EVENTVALIDATION'] = event_validation.get('value', '')

            # Buscar __VIEWSTATE
            viewstate = document.find('.//input[@name="__VIEWSTATE"]')
            if viewstate is not None:
                tokens['__VIEWSTATE'] = viewstate.get('value', '')

            # Buscar __VIEWSTATEGENERATOR
            viewstate_gen = document.find('.//input[@name="__VIEWSTATEGENERATOR"]')
            if viewstate_gen is not None:
                tokens['__VIEWSTATEGENERATOR'] = viewstate_gen.get('value', '')

            # Método 2: Buscar por ID si no se encontraron por nombre
            if not tokens.get('__VIEWSTATE'):
                viewstate = document.find('.//input[@id="__VIEWSTATE"]')
                if viewstate is not None:
                    tokens['__VIEWSTATE'] = viewstate.get('value', '')

            if not tokens.get('__EVENTVALIDATION'):
                event_validation = document.find('.//input[@id="__EVENTVALIDATION"]')
                if event_validation is not None:
                    tokens['__EVENTVALIDATION'] = event_validation.get('value', '')

            # Método 3: Buscar todos los inputs hidden y filtrar
            if not tokens.get('__VIEWSTATE') or not tokens.get('__EVENTVALIDATION'):
                for hidden in document.findall('.//input[@type="hidden"]'):
                    name = hidden.get('name', '') or hidden.get('id', '')
                    value = hidden.get('value', '')
                    if name == '__VIEWSTATE' and value:
                        tokens['__VIEWSTATE'] = value
                    elif name == '__EVENTVALIDATION' and value:
                        tokens['__EVENTVALIDATION'] = value
                    elif name == '__VIEWSTATEGENERATOR' and value:
                        tokens['__VIEWSTATEGENERATOR'] = value

        except Exception as e:
            _logger.error(f"[DGII] Error extrayendo tokens: {e}")

        return tokens

    def _parse_dgii_response(self, document):
        """
        Parsea la respuesta de la DGII y extrae los datos del contribuyente.
        Retorna un diccionario con los datos encontrados.
        """
        result = {}

        # Buscar mensaje de información/error
        info_message = document.findtext('.//*[@id="cphMain_lblInformacion"]')
        if info_message:
            result['message'] = info_message.strip()

        # Buscar la tabla de resultados
        result_div = document.find('.//div[@id="cphMain_divBusqueda"]')
        if result_div is None:
            _logger.warning("No se encontró div de resultados en respuesta DGII")
            return result

        # Buscar todas las filas de la tabla
        rows = result_div.findall('.//tr')

        for row in rows:
            cells = row.findall('.//td')
            if len(cells) >= 2:
                # Primera celda es el label, segunda es el valor
                label_cell = cells[0]
                value_cell = cells[1]

                label = label_cell.text_content().strip() if hasattr(label_cell, 'text_content') else (label_cell.text or '').strip()
                value = value_cell.text_content().strip() if hasattr(value_cell, 'text_content') else (value_cell.text or '').strip()

                # Limpiar el label de caracteres especiales
                label = label.rstrip(':').strip()

                if label and value:
                    result[label] = value

        # También intentar el método original por si la estructura es diferente
        if not result.get('Nombre/Razón Social'):
            headers = []
            values = []
            for td in result_div.findall('.//tr/td'):
                text = td.text.strip() if td.text else ''
                if td.attrib:  # Es un header
                    headers.append(text)
                else:  # Es un valor
                    values.append(text)

            if headers and values and len(headers) == len(values):
                for h, v in zip(headers, values):
                    if h and v:
                        result[h] = v

        return result

    def _convert_dgii_result(self, dgii_data):
        """
        Convierte los datos de la DGII al formato de campos de Odoo.
        """
        field_mapping = {
            'Cédula/RNC': 'vat',
            'RNC': 'vat',
            'Cédula': 'vat',
            'Nombre/Razón Social': 'name',
            'Nombre Comercial': 'l10n_do_dgii_commercial_name',
            'Régimen de pagos': 'l10n_do_dgii_payment_regime',
            'Régimen de Pagos': 'l10n_do_dgii_payment_regime',
            'Categoría': 'l10n_do_dgii_category',
            'Estado': 'l10n_do_dgii_status',
            'Actividad Economica': 'l10n_do_dgii_activity',
            'Actividad Económica': 'l10n_do_dgii_activity',
            'Administracion Local': 'l10n_do_dgii_local_admin',
            'Administración Local': 'l10n_do_dgii_local_admin',
        }

        converted = {}
        for dgii_key, value in dgii_data.items():
            odoo_field = field_mapping.get(dgii_key)
            if odoo_field and value:
                # Limpiar espacios múltiples
                clean_value = ' '.join(value.split())
                converted[odoo_field] = clean_value

        return converted

    # MODIFICADO: Arturo Diaz Lora - 2026-04-09
    # Razón: Agregar método para consultar API de indexa.do (más rápida y confiable)
    def _query_indexa_rnc(self, clean_vat):
        """
        Consulta el RNC/Cédula en la API de indexa.do.
        Retorna un diccionario con los datos o None si hay error.
        """
        try:
            _logger.debug(f"[INDEXA] Consultando RNC: {clean_vat}")
            response = requests.get(
                INDEXA_API_URL,
                params={'rnc': clean_vat},
                timeout=10,
                verify=False
            )

            _logger.debug(f"[INDEXA] Respuesta - Status: {response.status_code}")

            if response.status_code != 200:
                _logger.warning(f"[INDEXA] Error HTTP: {response.status_code}")
                return None

            data = response.json()

            if data.get('status') != 'success' or not data.get('data'):
                _logger.warning(f"[INDEXA] No se encontraron datos para RNC: {clean_vat}")
                return None

            # Tomar el primer resultado
            result = data['data'][0]

            # Convertir al formato esperado por Odoo
            converted = {
                'name': result.get('business_name', ''),
                'l10n_do_dgii_commercial_name': result.get('tradename', '').strip(),
                'l10n_do_dgii_status': result.get('state', ''),
                'l10n_do_dgii_payment_regime': result.get('payment_regime', ''),
                'l10n_do_dgii_activity': result.get('economic_activity', ''),
            }

            _logger.debug(f"[INDEXA] Datos obtenidos: {converted}")
            return converted

        except requests.exceptions.Timeout:
            _logger.warning(f"[INDEXA] Timeout consultando RNC: {clean_vat}")
            return None
        except requests.exceptions.RequestException as e:
            _logger.warning(f"[INDEXA] Error de conexión: {e}")
            return None
        except Exception as e:
            _logger.error(f"[INDEXA] Error inesperado: {e}")
            return None

    def _query_dgii_rnc(self, vat, max_retries=2):
        """
        Consulta el RNC/Cédula.
        MODIFICADO: Arturo Diaz Lora - 2026-04-09
        Razón: DGII como fuente principal (oficial), indexa.do como fallback.
        Retorna un diccionario con los datos o None si hay error.
        """
        clean_vat, vat_type = self._validate_rnc_format(vat)
        if not clean_vat:
            _logger.warning(f"Formato de RNC/Cédula inválido: {vat}")
            return None

        # PASO 1: Intentar primero con DGII (fuente oficial)
        for attempt in range(max_retries):
            result = self._do_dgii_query(clean_vat, attempt + 1)
            if result:
                _logger.info(f"[RNC] Datos obtenidos de DGII para: {clean_vat}")
                return result

            if attempt < max_retries - 1:
                import time
                time.sleep(0.5)  # Esperar 0.5 segundos entre reintentos

        # PASO 2: Fallback a indexa.do si DGII falla
        _logger.debug(f"[RNC] DGII falló, intentando indexa.do para: {clean_vat}")
        result = self._query_indexa_rnc(clean_vat)
        if result:
            _logger.info(f"[RNC] Datos obtenidos de indexa.do (fallback) para: {clean_vat}")
            return result

        _logger.warning(f"[RNC] No se pudieron obtener datos para RNC: {clean_vat}")
        return None

    def _do_dgii_query(self, clean_vat, attempt=1):
        """
        Realiza la consulta real a la DGII.
        Retorna un diccionario con los datos o None si hay error.
        MODIFICADO: Arturo Diaz Lora - 2026-04-09
        Razón: Reducir timeout de 30s a 10s para evitar bloqueos largos
        """
        try:
            session = self._get_dgii_session()

            # Primera petición para obtener los tokens del formulario
            _logger.debug(f"[DGII] Intento {attempt} - Consultando página inicial para RNC: {clean_vat}")
            response = session.get(DGII_RNC_URL, timeout=10, verify=False)

            _logger.debug(f"[DGII] Intento {attempt} - Respuesta GET - Status: {response.status_code}, Length: {len(response.text)}")

            if response.status_code != 200:
                _logger.error(f"[DGII] Error HTTP en GET: {response.status_code}")
                return None

            # Verificar que la respuesta contenga HTML válido
            html_content = response.text
            if not html_content or len(html_content) < 1000:
                _logger.error(f"[DGII] Respuesta HTML muy corta o vacía: {len(html_content)} bytes")
                _logger.debug(f"[DGII] Contenido: {html_content[:500]}")
                return None

            # Parsear HTML
            try:
                document = lxml.html.fromstring(html_content)
            except Exception as parse_error:
                _logger.error(f"[DGII] Error parseando HTML: {parse_error}")
                _logger.debug(f"[DGII] HTML recibido: {html_content[:1000]}")
                return None

            tokens = self._extract_form_tokens(document)

            _logger.debug(f"[DGII] Tokens extraídos - VIEWSTATE: {len(tokens.get('__VIEWSTATE', '')) > 0}, "
                        f"EVENTVALIDATION: {len(tokens.get('__EVENTVALIDATION', '')) > 0}")

            if not tokens.get('__VIEWSTATE') or not tokens.get('__EVENTVALIDATION'):
                _logger.error("[DGII] No se pudieron obtener los tokens de validación")
                # Buscar tokens con método alternativo usando regex
                viewstate_match = re.search(r'__VIEWSTATE["\s]+value="([^"]+)"', html_content)
                eventval_match = re.search(r'__EVENTVALIDATION["\s]+value="([^"]+)"', html_content)

                if viewstate_match and eventval_match:
                    tokens['__VIEWSTATE'] = viewstate_match.group(1)
                    tokens['__EVENTVALIDATION'] = eventval_match.group(1)
                    _logger.debug("[DGII] Tokens recuperados con regex")
                else:
                    _logger.error("[DGII] No se encontraron tokens ni con xpath ni con regex")
                    return None

            # Preparar datos del POST
            post_data = {
                '__EVENTTARGET': '',
                '__EVENTARGUMENT': '',
                '__VIEWSTATE': tokens.get('__VIEWSTATE', ''),
                '__VIEWSTATEGENERATOR': tokens.get('__VIEWSTATEGENERATOR', ''),
                '__EVENTVALIDATION': tokens.get('__EVENTVALIDATION', ''),
                'ctl00$cphMain$txtRNCCedula': clean_vat,
                'ctl00$cphMain$txtRazonSocial': '',
                'ctl00$cphMain$btnBuscarPorRNC': 'Buscar',
            }

            # Headers adicionales para el POST
            post_headers = REQUEST_HEADERS.copy()
            post_headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://dgii.gov.do',
                'Referer': DGII_RNC_URL,
            })

            # Segunda petición con la búsqueda
            # MODIFICADO: Arturo Diaz Lora - 2026-04-09 - Reducir timeout de 30s a 10s
            _logger.debug(f"[DGII] Enviando POST para RNC: {clean_vat}")
            response = session.post(DGII_RNC_URL, data=post_data, headers=post_headers, timeout=10, verify=False)

            _logger.debug(f"[DGII] Respuesta POST - Status: {response.status_code}, Length: {len(response.text)}")

            if response.status_code != 200:
                _logger.error(f"[DGII] Error HTTP en POST: {response.status_code}")
                return None

            try:
                document = lxml.html.fromstring(response.text)
            except Exception as parse_error:
                _logger.error(f"[DGII] Error parseando respuesta POST: {parse_error}")
                return None

            dgii_data = self._parse_dgii_response(document)

            if not dgii_data:
                _logger.warning(f"[DGII] No se encontraron datos para RNC: {clean_vat}")
                # Verificar si hay mensaje de error
                error_msg = document.findtext('.//*[@id="cphMain_lblInformacion"]')
                if error_msg:
                    _logger.debug(f"[DGII] Mensaje de DGII: {error_msg}")
                return None

            _logger.debug(f"[DGII] Datos obtenidos para RNC {clean_vat}: {list(dgii_data.keys())}")
            return self._convert_dgii_result(dgii_data)

        except requests.exceptions.Timeout:
            _logger.error(f"[DGII] Timeout consultando RNC: {clean_vat}")
            return None
        except requests.exceptions.SSLError as e:
            _logger.error(f"[DGII] Error SSL consultando RNC {clean_vat}: {str(e)}")
            return None
        except requests.exceptions.ConnectionError as e:
            _logger.error(f"[DGII] Error de conexión consultando RNC {clean_vat}: {str(e)}")
            return None
        except requests.exceptions.RequestException as e:
            _logger.error(f"[DGII] Error de requests consultando RNC {clean_vat}: {str(e)}")
            return None
        except Exception as e:
            _logger.exception(f"[DGII] Error inesperado consultando RNC {clean_vat}: {str(e)}")
            return None

    @api.onchange("vat", "country_id")
    def _check_rnc(self):
        """
        Onchange que autocompleta los datos del partner consultando la DGII
        cuando se ingresa un RNC/Cédula dominicano.
        """
        # Verificar si el autocompletado está habilitado
        dgii_autocomplete = self.env['ir.config_parameter'].sudo().get_param(
            'l10n_do_partner_autocomplete.dgii_autocomplete', 'False'
        )

        # Convertir a booleano (puede venir como string)
        if isinstance(dgii_autocomplete, str):
            dgii_autocomplete = dgii_autocomplete.lower() in ('true', '1', 'yes')

        if not dgii_autocomplete:
            return

        # Verificar que sea un partner dominicano
        if not self.country_id or self.country_id != self.env.ref("base.do", raise_if_not_found=False):
            return

        if not self.vat:
            return

        # Validar formato del RNC/Cédula
        clean_vat, vat_type = self._validate_rnc_format(self.vat)
        if not clean_vat:
            raise UserError(_(
                "El formato del RNC/Cédula no es válido. "
                "Debe ser un RNC de 9 dígitos o una Cédula de 11 dígitos. "
                "No debe contener guiones ni otros caracteres especiales."
            ))

        # Consultar la DGII
        _logger.debug(f"Consultando DGII para RNC/Cédula: {clean_vat}")
        dgii_data = self._query_dgii_rnc(clean_vat)

        if dgii_data:
            # Actualizar el nombre si se obtuvo
            if dgii_data.get('name'):
                self.name = dgii_data['name']
                _logger.debug(f"Nombre actualizado a: {dgii_data['name']}")

            # Guardar el nombre de la DGII
            if dgii_data.get('name'):
                self.l10n_do_dgii_name = dgii_data['name']

            # Actualizar campos adicionales de la DGII
            if dgii_data.get('l10n_do_dgii_commercial_name'):
                self.l10n_do_dgii_commercial_name = dgii_data['l10n_do_dgii_commercial_name']

            if dgii_data.get('l10n_do_dgii_status'):
                self.l10n_do_dgii_status = dgii_data['l10n_do_dgii_status']

            if dgii_data.get('l10n_do_dgii_payment_regime'):
                self.l10n_do_dgii_payment_regime = dgii_data['l10n_do_dgii_payment_regime']

            if dgii_data.get('l10n_do_dgii_activity'):
                self.l10n_do_dgii_activity = dgii_data['l10n_do_dgii_activity']

            if dgii_data.get('l10n_do_dgii_category'):
                self.l10n_do_dgii_category = dgii_data['l10n_do_dgii_category']

            if dgii_data.get('l10n_do_dgii_local_admin'):
                self.l10n_do_dgii_local_admin = dgii_data['l10n_do_dgii_local_admin']

            # Actualizar fecha de última consulta
            self.l10n_do_dgii_last_update = fields.Datetime.now()
        else:
            _logger.warning(f"No se obtuvieron datos de DGII para: {clean_vat}")

    def action_update_dgii_data(self):
        """
        Acción para actualizar manualmente los datos de la DGII.
        """
        self.ensure_one()

        if not self.vat:
            raise UserError(_("El contacto no tiene RNC/Cédula configurado."))

        if self.country_id != self.env.ref("base.do", raise_if_not_found=False):
            raise UserError(_("Esta acción solo está disponible para contactos dominicanos."))

        dgii_data = self._query_dgii_rnc(self.vat)

        if dgii_data:
            update_vals = {
                'l10n_do_dgii_last_update': fields.Datetime.now(),
            }

            if dgii_data.get('name'):
                update_vals['l10n_do_dgii_name'] = dgii_data['name']

            if dgii_data.get('l10n_do_dgii_commercial_name'):
                update_vals['l10n_do_dgii_commercial_name'] = dgii_data['l10n_do_dgii_commercial_name']

            if dgii_data.get('l10n_do_dgii_status'):
                update_vals['l10n_do_dgii_status'] = dgii_data['l10n_do_dgii_status']

            if dgii_data.get('l10n_do_dgii_payment_regime'):
                update_vals['l10n_do_dgii_payment_regime'] = dgii_data['l10n_do_dgii_payment_regime']

            if dgii_data.get('l10n_do_dgii_activity'):
                update_vals['l10n_do_dgii_activity'] = dgii_data['l10n_do_dgii_activity']

            if dgii_data.get('l10n_do_dgii_category'):
                update_vals['l10n_do_dgii_category'] = dgii_data['l10n_do_dgii_category']

            if dgii_data.get('l10n_do_dgii_local_admin'):
                update_vals['l10n_do_dgii_local_admin'] = dgii_data['l10n_do_dgii_local_admin']

            self.write(update_vals)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Datos actualizados'),
                    'message': _('Los datos de la DGII han sido actualizados correctamente.'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            raise UserError(_(
                "No se pudieron obtener datos de la DGII para el RNC/Cédula: %s. "
                "Por favor, verifique que el número sea correcto e intente nuevamente."
            ) % self.vat)
