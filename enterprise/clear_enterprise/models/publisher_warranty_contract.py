# -*- coding: utf-8 -*-
import logging

from odoo import models

from ..enterprise_license import BLOCK_REMOTE_SYNC_KEY

_logger = logging.getLogger(__name__)


class PublisherWarrantyContract(models.AbstractModel):
    _inherit = 'publisher_warranty.contract'

    def update_notification(self, cron_mode=True):
        """Evita que odoo.com reponga database.expiration_* tras limpiar licencia localmente."""
        icp = self.env['ir.config_parameter'].sudo()
        if icp.get_param(BLOCK_REMOTE_SYNC_KEY) == '1':
            _logger.info(
                'publisher_warranty.update_notification omitido: %s=1 (clear_enterprise)',
                BLOCK_REMOTE_SYNC_KEY,
            )
            return True
        return super().update_notification(cron_mode=cron_mode)
