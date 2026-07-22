# -*- coding: utf-8 -*-
# MODIFICADO: Arturo Diaz Lora - 2026-04-22 04:25
# Razón: Agregado @api.model a set_param - sin él, _api_model=False rompe
# llamadas <function> en XML data files (TypeError: missing 'value' arg)
from odoo import api, models

from ..enterprise_license import BLOCK_REMOTE_SYNC_KEY


class IrConfigParameter(models.Model):
    _inherit = 'ir.config_parameter'

    @api.model
    def set_param(self, key, value):
        res = super().set_param(key, value)
        # Al registrar un código nuevo, el flujo web vuelve a necesitar update_notification.
        if key == 'database.enterprise_code' and value not in (False, None, ''):
            super().set_param(BLOCK_REMOTE_SYNC_KEY, '0')
        return res
