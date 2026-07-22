
from odoo import api, fields, models, _


class ResConfigSettings(models.TransientModel):

    _inherit = 'res.config.settings'

    module_l10n_do_partner_autocomplete = fields.Boolean("DGII Partner Autocomplete", config_parameter='l10n_do_partner_autocomplete.dgii_autocomplete')

    # MODIFICADO: Arturo Diaz Lora - 2026-02-22
    # Razón: Campo para ocultar información de la compañía en el encabezado de facturas
    l10n_do_hide_company_header = fields.Boolean(
        related='company_id.l10n_do_hide_company_header',
        readonly=False,
        string="Ocultar Info Compañía en Encabezado",
    )
