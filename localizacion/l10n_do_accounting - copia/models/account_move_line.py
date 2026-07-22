
from odoo import models, fields, api, _


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    l10n_do_itbis_amount = fields.Monetary(
        string="ITBIS Amount",
        store=True,
        readonly=True,
        currency_field="currency_id",
    )
    l10n_latam_document_type_id = fields.Many2one(
        related='move_id.l10n_latam_document_type_id', store=True, index=True)
    l10n_latam_price_unit = fields.Monetary(compute='compute_l10n_latam_prices_and_taxes')
    l10n_latam_price_subtotal = fields.Monetary(compute='compute_l10n_latam_prices_and_taxes')
    l10n_latam_price_net = fields.Monetary(compute='compute_l10n_latam_prices_and_taxes')
    l10n_latam_tax_ids = fields.One2many(compute="compute_l10n_latam_prices_and_taxes", comodel_name='account.tax')

    def _get_price_total_and_subtotal(
        self,
        price_unit=None,
        quantity=None,
        discount=None,
        currency=None,
        product=None,
        partner=None,
        taxes=None,
        move_type=None,
    ):
        self.ensure_one()
        res = super(AccountMoveLine, self)._get_price_total_and_subtotal(
            price_unit=price_unit,
            quantity=quantity,
            discount=discount,
            currency=currency,
            product=product,
            partner=partner,
            taxes=taxes,
            move_type=move_type,
        )

        if self.move_id.is_ecf_invoice:

            line_itbis_taxes = self.tax_ids.filtered(
                lambda t: t.tax_group_id == self.env.ref("l10n_do.group_itbis")
            )
            itbis_taxes_data = line_itbis_taxes.compute_all(
                price_unit=self.price_unit,
                quantity=self.quantity,
            )
            res["l10n_do_itbis_amount"] = sum(
                [t["amount"] for t in itbis_taxes_data["taxes"]]
            )
        return res

    @api.depends('price_unit', 'price_subtotal', 'move_id.l10n_latam_document_type_id')
    def compute_l10n_latam_prices_and_taxes(self):
        for line in self:
            invoice = line.move_id
            included_taxes = \
                invoice.l10n_latam_document_type_id and invoice.l10n_latam_document_type_id._filter_taxes_included(
                    line.tax_ids)
            if not included_taxes:
                price_unit = line.tax_ids.with_context(round=False,
                                                       force_sign=invoice._get_tax_force_sign()).compute_all(
                    line.price_unit, invoice.currency_id, 1.0, line.product_id, invoice.partner_id)
                l10n_latam_price_unit = price_unit['total_excluded']
                l10n_latam_price_subtotal = line.price_subtotal
                not_included_taxes = line.tax_ids
                l10n_latam_price_net = l10n_latam_price_unit * (1 - (line.discount or 0.0) / 100.0)
            else:
                not_included_taxes = line.tax_ids - included_taxes
                l10n_latam_price_unit = \
                included_taxes.with_context(force_sign=invoice._get_tax_force_sign()).compute_all(
                    line.price_unit, invoice.currency_id, 1.0, line.product_id, invoice.partner_id)['total_included']
                l10n_latam_price_net = l10n_latam_price_unit * (1 - (line.discount or 0.0) / 100.0)
                price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                l10n_latam_price_subtotal = \
                included_taxes.with_context(force_sign=invoice._get_tax_force_sign()).compute_all(
                    price, invoice.currency_id, line.quantity, line.product_id,
                    invoice.partner_id)['total_included']

            line.l10n_latam_price_subtotal = l10n_latam_price_subtotal
            line.l10n_latam_price_unit = l10n_latam_price_unit
            line.l10n_latam_price_net = l10n_latam_price_net
            line.l10n_latam_tax_ids = not_included_taxes

    def _get_tax_display_name(self, tax):
        """Obtener el nombre traducido del impuesto para República Dominicana"""
        if self.company_id.country_id.code == 'DO':
            # Usar el campo traducido si existe
            if hasattr(tax, 'l10n_do_invoice_label') and tax.l10n_do_invoice_label:
                return tax.l10n_do_invoice_label
            # Si no, traducir basado en el nombre
            tax_name = tax.name or ''
            if 'ITBIS' in tax_name and 'Sales' in tax_name:
                if '18%' in tax_name:
                    return _('18% ITBIS Ventas')
                elif 'Exempt' in tax_name:
                    return _('Exento ITBIS Ventas')
            elif 'ITBIS' in tax_name and 'Purchases' in tax_name:
                if '18%' in tax_name:
                    return _('18% ITBIS Compras')
                elif '16%' in tax_name:
                    return _('16% ITBIS Compras')
            elif 'Propina' in tax_name or 'Tip' in tax_name:
                return _('10% Propina Legal')
        # Para otros países o si no hay traducción específica
        return tax.invoice_label or tax.name