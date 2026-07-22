# -*- coding: utf-8 -*-
# MODIFICADO: Arturo Diaz Lora - 2026-04-21
# Razón: Migración a Odoo 19 — versión 19.0.x y textos de documentación alineados a v19.
{
    'name': 'Clear Enterprise License',
    'version': '19.0.1.0.0',
    'category': 'Administration',
    'summary': 'Permite limpiar la licencia enterprise para registrar una nueva',
    'description': """
        Módulo para limpiar los parámetros de suscripción enterprise (Odoo 19).
        Útil cuando el cliente compra una nueva licencia y necesita reemplazar la anterior.

        La instalación del módulo no borra datos. El asistente elimina registros de
        ir.config_parameter con claves:
        database.enterprise_code, database.expiration_date, database.expiration_reason
        y los parámetros database.already_linked_* de vinculación de suscripción.

        Tras usar el asistente, además de borrar claves, se fija una fecha de expiración en el pasado
        y motivo «trial» para que web_enterprise muestre el registro (sin esto, Odoo 19 asume +30 días).

        Mientras la base siga vinculada en odoo.com, el cron «Publisher: Update Notification» volvería a
        escribir la fecha de suscripción (p. ej. abril 2027). El asistente activa un bloqueo temporal
        (parámetro clear_enterprise.block_remote_license_sync) que omite esa sincronización hasta que
        se guarde un nuevo database.enterprise_code desde el formulario de registro.

        Tras instalar o actualizar el módulo, el servidor registra un WARNING en el log con el detalle.
    """,
    'author': 'ADL Academy',
    # display_notification (ir.actions.client) está registrado en el addon web
    'depends': ['base', 'web', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/clear_enterprise_wizard_views.xml',
        'views/menu_views.xml',
    ],
    'license': 'LGPL-3',
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
