#  Copyright (c) 2018 - Indexa SRL. (<https://www.indexa.do/>)
#  See LICENSE file for full copyright and licensing details.

import datetime
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_do_currency_interval_unit = fields.Selection(related="company_id.l10n_do_currency_interval_unit", readonly=False)
    l10n_do_currency_provider = fields.Selection(related="company_id.l10n_do_currency_provider", readonly=False)
    l10n_do_currency_next_execution_date = fields.Date(related="company_id.l10n_do_currency_next_execution_date", readonly=False)
    currency_base = fields.Selection(related="company_id.currency_base", readonly=False)
    rate_offset = fields.Float(related="company_id.rate_offset", readonly=False)
    last_currency_sync_date = fields.Date(related="company_id.last_currency_sync_date", readonly=False)

    @api.onchange('l10n_do_currency_interval_unit')
    def onchange_l10n_do_currency_interval_unit(self):
        # as the onchange is called upon each opening of the settings, we avoid overwriting
        # the next execution date if it has been already set
        if self.company_id.l10n_do_currency_next_execution_date:
            return
        if self.l10n_do_currency_interval_unit == 'daily':
            next_update = relativedelta(days=+1)
        elif self.l10n_do_currency_interval_unit == 'weekly':
            next_update = relativedelta(weeks=+1)
        elif self.l10n_do_currency_interval_unit == 'monthly':
            next_update = relativedelta(months=+1)
        else:
            self.l10n_do_currency_next_execution_date = False
            return
        self.l10n_do_currency_next_execution_date = fields.Date.to_string(datetime.datetime.now() + next_update)

    def l10n_do_update_currency_rates(self):
        # Arturo Diaz Lora - 2025-12-07 16:30 - Mejorado para mostrar mensajes de error específicos
        companies = self.env['res.company'].browse([record.company_id.id for record in self])
        result = companies.l10n_do_update_currency_rates()

        # Manejar el nuevo formato de retorno (tupla) y el antiguo (bool) para compatibilidad
        if isinstance(result, tuple):
            success, error_message = result
            if not success:
                raise UserError(error_message or _('Error desconocido al actualizar tasas de cambio.'))
        elif not result:
            raise UserError(_('No se pudieron obtener las tasas de cambio. Verifique la configuración de la API.'))
