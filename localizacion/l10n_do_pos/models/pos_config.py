# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class PosConfig(models.Model):
    _inherit = "pos.config"

    default_partner_id = fields.Many2one("res.partner",
                                         string="Default Customer",
                                         help=u"Este cliente se usará por defecto como cliente de consumo"
                                              " para las facturas de consumo o final en el POS")
    only_invoice = fields.Boolean(string="Only Invoice", default=False)
    show_receipt_logo = fields.Boolean(
        string="Show Logo in Receipt",
        default=True,
        help="Display company logo in POS receipts. Uncheck to hide the logo from printed and preview receipts."
    )
    l10n_do_disable_auto_print_invoice = fields.Boolean(
        string="Disable Auto-Print Invoice (A4)",
        default=False,
        help="Disable automatic printing of invoice in A4 format from POS. "
             "When enabled, only the POS receipt will be printed, not the full invoice report."
    )

    @api.onchange("only_invoice")
    def onchange_only_invoice(self):
        self._set_default_partner_for_only_invoice()

    @api.model_create_multi
    def create(self, vals_list):
        res = super(PosConfig, self).create(vals_list)
        for record in res:
            record._set_default_partner_for_only_invoice()
        return res

    def write(self, vals):
        res = super(PosConfig, self).write(vals)
        if 'only_invoice' in vals:
            self._set_default_partner_for_only_invoice()
        return res

    def _set_default_partner_for_only_invoice(self):
        """Configura automáticamente el cliente de consumo cuando only_invoice está activado"""
        default_partner = self.env.ref("l10n_do_pos.default_partner_on_pos", raise_if_not_found=False)
        
        for config in self:
            if config.only_invoice and default_partner:
                if not config.default_partner_id:
                    config.default_partner_id = default_partner.id
                    print(f"[L10N_DO_POS] Auto-configured default partner for POS config {config.name}")
            # No remover el cliente por defecto si only_invoice se desactiva
            # para mantener la configuración existente

    @api.model
    def _ensure_default_partner_configuration(self):
        """Método para asegurar que todas las configuraciones existentes tengan el partner correcto"""
        default_partner = self.env.ref("l10n_do_pos.default_partner_on_pos", raise_if_not_found=False)
        if not default_partner:
            return
            
        configs_with_only_invoice = self.search([('only_invoice', '=', True), ('default_partner_id', '=', False)])
        for config in configs_with_only_invoice:
            config.default_partner_id = default_partner.id
            print(f"[L10N_DO_POS] Updated default partner for existing POS config {config.name}")
