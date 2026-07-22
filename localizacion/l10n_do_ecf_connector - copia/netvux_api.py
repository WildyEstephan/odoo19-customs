import logging

_logger = logging.getLogger(__name__)

import requests
import json


class NETVUXApi:

    def __init__(self, ecf_config):
        self.ecf_config = ecf_config
        self.user = ecf_config.user
        self.key = ecf_config.key
        self.subdomain = 'sandbox' if self.ecf_config.environment == 'TesteCF' else 'ecf'

    def authentication(self):
        subdomain = self.subdomain
        env = self.ecf_config.environment
        url_val_semilla = "https://{}.netvux.com/{}/api/Autenticacion".format(subdomain, env)
        headers_semilla = {
            'Authorization': 'Bearer {}'.format(self.key),
        }

        data = {
            'user': self.user,
        }

        response = requests.post(url_val_semilla, headers=headers_semilla, data=data)

        if response.status_code == 200:
            return json.loads(response.text)
        elif response.status_code == 404:
            response_text = response.text
            return response_text
        elif response.status_code == 500:
            response_text = response.text
            return response_text

    def receipt_xml_ecf(self, signed_file, xmlname, kernel):
        headers_semilla = {
            "accept": 'application/json',
            'Authorization': 'Bearer {}'.format(kernel.get('token', '')),
        }
        subdomain = self.subdomain
        env = self.ecf_config.environment
        api_url = 'https://{}.netvux.com/{}/api/ecf'.format(subdomain, env)
        # _logger.info("##### ENVIANDO A RECEPCION ECF: " + api_url)
        # _logger.info("##### ARCHIVO : " + xmlname)
        files = {
            'xml': (xmlname, signed_file.decode(), 'text/xml')
        }
        response = requests.post(api_url, headers=headers_semilla, files=files)
        # _logger.info(response.status_code)
        try:
            vals = response.text
        except (
                ValueError,
                TypeError,
                SyntaxError,
        ):  # could not parse a dict from response text
            vals = {}

        return response, vals, kernel.get('token', '')

    def send_ecf_status_request(self, rncemisor, ncfelectronico, kernel):
        subdomain = self.subdomain
        env = self.ecf_config.environment

        headers_semilla = {
            "accept": 'application/json',
            'Authorization': 'Bearer {}'.format(kernel.get('token', '')),
        }
        data = {
            'rncemisor': rncemisor,
            'ncfelectronico': ncfelectronico,
        }

        api_url = 'https://{}.netvux.com/{}/api/consultaestado'.format(subdomain, env)
        response = requests.post(api_url, headers=headers_semilla, data=data)

        return response

    def send_ecf_request_xml(self, token, trackId):
        """Consulta XML."""

        subdomain = self.subdomain
        env = self.ecf_config.environment
        headers_semilla = {
            "accept": 'application/xml',
            'Authorization': 'Bearer {}'.format(token),
        }
        api_url = 'https://{}.netvux.com/{}/api/TrackId?TrackId={}'.format(subdomain, env, trackId)
        response = requests.post(api_url, headers=headers_semilla)
        # _logger.info(response.status_code)
        # _logger.info(response.text)

        try:
            vals = response.text
            # _logger.debug(vals)
        except (
                ValueError,
                TypeError,
                SyntaxError,
        ):  # could not parse a dict from response text
            vals = {}

        return response, vals
