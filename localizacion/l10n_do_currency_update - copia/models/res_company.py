#  Copyright (c) 2018 - Indexa SRL. (https://www.indexa.do) <info@indexa.do>
#  See LICENSE file for full licensing details.

import json
import logging
import requests
import datetime
import pytz
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

CURRENCY_MAPPING = {
    'euro': 'EUR',
    'cdol': 'CAD',
    'doll': 'USD',
    'poun': 'GBP',
    'swis': 'CHF',
}


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_do_currency_interval_unit = fields.Selection([
        ('manually', 'Manually'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly')],
        default='daily', string='Currency Interval')
    l10n_do_currency_provider = fields.Selection([
        ('10', 'Banco Central'),
        ('11', 'Agente de Cambio La Nacional'),
        ('12', 'Asociación Maguana de Ahorros y Préstamos'),
        ('13', 'Asociación Peravia de Ahorros y Préstamos'),
        ('14', 'Alaver'),
        ('15', 'Banreservas'),
        ('16', 'Banco Caribe'),
        ('17', 'Banco Atlántico'),
        ('18', 'Motor Crédito'),
        ('19', 'Banco Empire'),
        ('20', 'Banco Activo Dominicana'),
        ('21', 'Moneycorps'),
        ('22', 'Scotiabank'),
        ('23', 'ScotiabankCambio online'),
        ('24', 'Banco Vimenca'),
        ('25', 'Banco Promerica'),
        ('26', 'Banesco'),
        ('27', 'Banco Popular'),
        ('28', 'Banco BDI'),
        ('29', 'Banco Ademi'),
        ('30', 'Banco BHD León'),
        ('31', 'Banco López de Haro'),
        ('32', 'Banco Lafise'),
        ('33', 'Asociación Popular de Ahorros y Préstamos'),
        ('34', 'Bonanza Banco'),
        ('35', 'Capla'),
        ('36', 'JMMB Bank'),
        ('37', 'Asociación La Nacional de Ahorros y Préstamos'),
        ('38', 'Quezada'),
        ('39', 'Asociación Cibao de Ahorros y Préstamos'),
        ('40', 'Banco Santa Cruz'),        
    ], default='10', string='Bank')
    currency_base = fields.Selection([('buyrate', 'Buy rate'), ('sellrate', 'Sell rate')], default='sellrate')
    rate_offset = fields.Float('Offset', default=0)
    l10n_do_currency_next_execution_date = fields.Date(string="Following Execution Date")
    last_currency_sync_date = fields.Date(string="Last Sync Date", readonly=True)

    def get_currency_rates(self, params):
        # Arturo Diaz Lora - 2025-12-07 16:35 - Mejorado para mostrar errores de la API
        api_url = self.env['ir.config_parameter'].sudo().get_param('os.api.url')
        if not api_url:
            error_msg = _('El parámetro "os.api.url" no está configurado.\n\nVaya a: Ajustes → Técnico → Parámetros del Sistema')
            _logger.warning(error_msg)
            return {'error': error_msg}
        try:
            response = requests.get(api_url, params=params, timeout=30)

            # Si no es 200, intentar obtener el mensaje de error de la API
            if response.status_code != 200:
                error_detail = ''
                try:
                    error_json = response.json()
                    if 'Error' in error_json:
                        error_detail = error_json['Error']
                    elif 'error' in error_json:
                        error_detail = error_json['error']
                    elif 'message' in error_json:
                        error_detail = error_json['message']
                except:
                    error_detail = response.text[:200] if response.text else ''

                if response.status_code == 400:
                    if 'usuario' in error_detail.lower():
                        error_msg = _('Usuario API incorrecto: %s\n\nVerifique el parámetro "os.api.user" en:\nAjustes → Técnico → Parámetros del Sistema') % error_detail
                    else:
                        error_msg = _('Solicitud inválida: %s') % error_detail
                elif response.status_code == 404:
                    error_msg = _('URL no encontrada: %s\n\nVerifique el parámetro "os.api.url" en:\nAjustes → Técnico → Parámetros del Sistema') % api_url
                elif response.status_code == 401 or response.status_code == 403:
                    error_msg = _('No autorizado: %s\n\nVerifique el parámetro "os.api.user"') % error_detail
                elif response.status_code >= 500:
                    error_msg = _('Error del servidor API (código %s): %s') % (response.status_code, error_detail)
                else:
                    error_msg = _('Error de API (código %s): %s') % (response.status_code, error_detail)

                _logger.warning(error_msg)
                return {'error': error_msg}

        except requests.exceptions.ConnectionError as e:
            error_msg = _('No se puede conectar al servidor: %s\n\nVerifique que la URL sea correcta.') % api_url
            _logger.warning('%s - %s' % (error_msg, e))
            return {'error': error_msg}
        except requests.exceptions.Timeout:
            error_msg = _('El servidor no respondió en 30 segundos.\n\nIntente nuevamente más tarde.')
            _logger.warning(error_msg)
            return {'error': error_msg}
        except requests.exceptions.RequestException as e:
            error_msg = _('Error de conexión: %s') % str(e)
            _logger.warning(error_msg)
            return {'error': error_msg}
        return response.text

    def l10n_do_update_currency_rates(self):
        # Arturo Diaz Lora - 2025-12-07 16:30 - Refactorizado para retornar errores específicos al usuario
        all_good = True
        error_message = None

        for company in self:
            if company.l10n_do_currency_provider:
                _logger.info("Calling API rates resource.")

                tz = pytz.timezone('America/Santo_Domingo')
                today = datetime.datetime.now(tz)
                user = self.env['ir.config_parameter'].sudo().get_param('os.api.user')
                params = {'banco_id': company.l10n_do_currency_provider,
                          'fecha': datetime.datetime.strftime(today, '%Y-%m-%d'),
                          'user': user}

                rates_dict = self.get_currency_rates(params)

                # Verificar si es un diccionario con error
                if isinstance(rates_dict, dict) and 'error' in rates_dict:
                    error_message = rates_dict['error']
                    all_good = False
                    continue

                d = {}
                try:
                    if rates_dict and isinstance(rates_dict, str):
                        content = rates_dict.strip()
                        if content.startswith('['):
                            d = json.loads(rates_dict)
                        elif content.startswith('<!DOCTYPE') or content.startswith('<html'):
                            # Respuesta HTML indica error del servidor
                            if 'TypeError' in content:
                                error_message = _('Error de autenticación: El usuario API no es válido. Verifique el parámetro "os.api.user" en Parámetros del Sistema.')
                            elif '404' in content or 'Page not found' in content:
                                error_message = _('Error de URL: La ruta de la API no existe. Verifique el parámetro "os.api.url" en Parámetros del Sistema.')
                            else:
                                error_message = _('Error del servidor API: La respuesta no es válida. Contacte al administrador del sistema.')
                            _logger.warning('API returned HTML instead of JSON: %s' % content[:500])
                            all_good = False
                            continue
                        else:
                            error_message = _('Error de API: Respuesta no reconocida del servidor.')
                            _logger.warning('API response is not valid JSON: %s' % content[:200])
                            all_good = False
                            continue
                except (TypeError, json.JSONDecodeError) as e:
                    error_message = _('Error al procesar respuesta: %s') % str(e)
                    _logger.warning('Error parsing API response: %s' % str(e))
                    all_good = False
                    continue

                Rate = self.env['res.currency.rate']

                if d:
                    for currency in d:
                        if company.currency_base == 'buyrate':
                            if float(currency['venta']) > 0:
                                inverse_rate = 1 / (float(currency['venta']) + company.rate_offset)
                            else:
                                inverse_rate = 1
                        elif company.currency_base == 'sellrate':
                            if float(currency['compra']) > 0:
                                inverse_rate = 1 / (float(currency['compra']) + company.rate_offset)
                            else:
                                inverse_rate = 1
                        else:
                            inverse_rate = 1

                        currency_id = self.env.ref('base.USD')
                        if currency_id and currency_id.active:
                            rate_id = Rate.search([('name', '=', fields.Date.today()),
                                                    ('currency_id', '=', currency_id.id),
                                                    ('company_id', '=', company.id)])
                            if rate_id:
                                rate_id.write({'rate': inverse_rate})
                            else:
                                Rate.create({'currency_id': currency_id.id,
                                                'rate': inverse_rate,
                                                'company_id': company.id})
                    company.last_currency_sync_date = fields.Date.today()
                else:
                    error_message = _('Error de API: No se recibieron datos de tasas.')
                    all_good = False
            else:
                error_message = _('Error de configuración: No se ha seleccionado un banco proveedor de tasas.')
                all_good = False

            if not all_good:
                _logger.warning(_('Unable to fetch new rates records from API'))

        # Retornar tupla (éxito, mensaje_error) para que el llamador pueda mostrar el mensaje
        if error_message:
            return (False, error_message)
        return (True, None)

    def l10n_do_run_update_currency(self):
        records = self.search([])
        if records:
            to_update = self.env['res.company']
            for record in records:
                if record.l10n_do_currency_interval_unit == 'daily':
                    next_update = relativedelta(days=+1)
                elif record.l10n_do_currency_interval_unit == 'weekly':
                    next_update = relativedelta(weeks=+1)
                elif record.l10n_do_currency_interval_unit == 'monthly':
                    next_update = relativedelta(months=+1)
                else:
                    record.l10n_do_currency_interval_unit = False
                    continue
                record.l10n_do_currency_next_execution_date = datetime.date.today() + next_update
                to_update += record
            to_update.l10n_do_update_currency_rates()
