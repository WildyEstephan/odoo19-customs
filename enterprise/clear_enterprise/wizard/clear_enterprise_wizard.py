# -*- coding: utf-8 -*-
import logging

from odoo import _, fields, models

from ..enterprise_license import BLOCK_REMOTE_SYNC_KEY, ENTERPRISE_PARAM_KEYS

_logger = logging.getLogger(__name__)


class ClearEnterpriseWizard(models.TransientModel):
    _name = 'clear.enterprise.wizard'
    _description = 'Clear Enterprise License Wizard'

    current_code = fields.Char(
        string='Código actual',
        readonly=True,
        default=lambda self: self.env['ir.config_parameter'].sudo().get_param(
            'database.enterprise_code', 'Sin licencia registrada'
        ),
    )
    current_expiration = fields.Char(
        string='Fecha de expiración',
        readonly=True,
        default=lambda self: self.env['ir.config_parameter'].sudo().get_param(
            'database.expiration_date', 'N/A'
        ),
    )
    confirm = fields.Boolean(
        string='Confirmo que deseo eliminar la licencia actual',
        default=False,
    )

    def action_clear_license(self):
        self.ensure_one()
        if not self.confirm:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Acción requerida'),
                    'message': _('Debe confirmar la eliminación marcando la casilla.'),
                    'type': 'warning',
                    'sticky': False,
                },
            }

        ICP = self.env['ir.config_parameter'].sudo()
        removed = []
        for key in ENTERPRISE_PARAM_KEYS:
            params = ICP.search([('key', '=', key)])
            if params:
                params.unlink()
                removed.append(key)

        # web_enterprise: si no hay database.expiration_date, el cliente asume +30 días y la
        # base sigue viéndose «activa». Forzamos trial vencido para que pida registro/código.
        expired = fields.Datetime.subtract(fields.Datetime.now(), days=1)
        ICP.set_param('database.expiration_date', fields.Datetime.to_string(expired))
        ICP.set_param('database.expiration_reason', 'trial')
        # Mientras la BD siga registrada en odoo.com, update_notification repone la fecha (p. ej. 2027).
        ICP.set_param(BLOCK_REMOTE_SYNC_KEY, '1')

        _logger.info(
            "Enterprise license cleared by user %s (uid=%s). Params removed: %s; "
            "local trial expired (expiration_date=%s); %s=1 (sync publisher bloqueada hasta nuevo código).",
            self.env.user.name,
            self.env.uid,
            ', '.join(removed) or 'none',
            fields.Datetime.to_string(expired),
            BLOCK_REMOTE_SYNC_KEY,
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
