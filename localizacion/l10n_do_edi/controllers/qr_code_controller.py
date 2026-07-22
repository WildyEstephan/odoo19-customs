# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request, Response
import base64
import logging

_logger = logging.getLogger(__name__)


class QRCodeController(http.Controller):

    @http.route('/l10n_do/qr/<int:invoice_id>', type='http', auth='public', website=True)
    def get_qr_code(self, invoice_id, **kwargs):
        """Sirve el código QR de una factura como imagen PNG"""
        try:
            # Buscar la factura
            invoice = request.env['account.move'].sudo().browse(invoice_id)

            if not invoice.exists() or not invoice.qr_code:
                # Devolver imagen vacía 1x1 PNG transparente
                empty_png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
                return Response(empty_png, content_type='image/png')

            # Decodificar el QR code de base64
            qr_image = base64.b64decode(invoice.qr_code)

            # Devolver como PNG
            return Response(qr_image, content_type='image/png', headers=[
                ('Cache-Control', 'public, max-age=3600'),  # Cache por 1 hora
            ])

        except Exception as e:
            _logger.error(f"Error sirviendo QR code para factura {invoice_id}: {str(e)}")
            # Devolver imagen vacía en caso de error
            empty_png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
            return Response(empty_png, content_type='image/png')
