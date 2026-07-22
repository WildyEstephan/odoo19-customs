# -*- coding: utf-8 -*-
# MODIFICADO: Arturo Diaz Lora - 2026-04-21
# Razón: Mensajes de log alineados a Odoo 19.
"""Parámetros enterprise en ir.config_parameter que elimina el asistente."""
import logging

_logger = logging.getLogger(__name__)

# Si vale «1», no se llama al servidor de garantía (evita que Odoo.com reponga la fecha 2027…).
BLOCK_REMOTE_SYNC_KEY = 'clear_enterprise.block_remote_license_sync'

# Incluye claves que mail/update.py escribe junto a la suscripción (publisher warranty).
ENTERPRISE_PARAM_SPEC = [
    ('database.enterprise_code', 'Código de suscripción / licencia enterprise'),
    ('database.expiration_date', 'Fecha de expiración de la suscripción'),
    ('database.expiration_reason', 'Motivo o detalle asociado a la expiración'),
    ('database.already_linked_subscription_url', 'URL si la BD ya estaba vinculada a otra suscripción'),
    ('database.already_linked_email', 'Correo vinculado a suscripción existente'),
    ('database.already_linked_send_mail_url', 'URL para reenvío de correo de vinculación'),
]

ENTERPRISE_PARAM_KEYS = [key for key, _desc in ENTERPRISE_PARAM_SPEC]


def post_init_hook(_env):
    """Log al instalar: la instalación no borra datos; lista lo que borraría el asistente."""
    detail_lines = '\n'.join(
        '  • %s — %s' % (key, desc)
        for key, desc in ENTERPRISE_PARAM_SPEC
    )
    _logger.warning(
        '[clear_enterprise] Odoo 19 — instalación sin borrado de licencia. '
        'El asistente borra claves, fija trial vencido y puede activar %s para no repoblar desde odoo.com. '
        'Claves borradas por el asistente:\n%s',
        BLOCK_REMOTE_SYNC_KEY,
        detail_lines,
    )
