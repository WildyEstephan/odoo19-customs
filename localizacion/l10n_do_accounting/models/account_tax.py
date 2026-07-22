
from odoo import models, fields, api, _


class AccountTax(models.Model):
    _inherit = "account.tax"

    def _get_isr_retention_type(self):
        return [
            ("01", "Alquileres"),
            ("02", "Honorarios por Servicios"),
            ("03", "Otras Rentas"),
            ("04", "Rentas Presuntas"),
            ("05", u"Intereses Pagados a Personas Jurídicas"),
            ("06", u"Intereses Pagados a Personas Físicas"),
            ("07", u"Retención por Proveedores del Estado"),
            ("08", u"Juegos Telefónicos"),
        ]

    purchase_tax_type = fields.Selection(
        [
            ("itbis", "ITBIS Pagado"),
            ("ritbis", "ITBIS Retenido"),
            ("isr", "ISR Retenido"),
            ("rext", "Pagos al Exterior (Ley 253-12)"),
            ("none", "No Deducible"),
        ],
        default="none",
        string="Tipo de Impuesto en Compra",
    )
    isr_retention_type = fields.Selection(
        [
            ("01", "Alquileres"),
            ("02", "Honorarios por Servicios"),
            ("03", "Otras Rentas"),
            ("04", "Rentas Presuntas"),
            ("05", u"Intereses Pagados a Personas Jurídicas"),
            ("06", u"Intereses Pagados a Personas Físicas"),
            ("07", u"Retención por Proveedores del Estado"),
            ("08", u"Juegos Telefónicos"),
        ],
        string="Tipo de Retención en ISR",
    )

    # Campo computado para etiquetas traducidas
    l10n_do_invoice_label = fields.Char(
        string="Etiqueta en Facturas (DO)",
        compute="_compute_invoice_label",
        store=True,
        help="Etiqueta traducida al español para impuestos de República Dominicana"
    )

    @api.depends('name', 'amount', 'type_tax_use', 'company_id.country_id')
    def _compute_invoice_label(self):
        """Traducir las etiquetas de impuestos para República Dominicana"""
        for tax in self:
            if tax.company_id.country_id.code == 'DO':
                tax_name = (tax.name or '').lower()
                tax_amount = tax.amount
                tax_type = tax.type_tax_use
                
                # Traducciones basadas en el nombre y tipo de impuesto
                if 'itbis' in tax_name:
                    if tax_type == 'sale':
                        if tax_amount == 18.0:
                            tax.l10n_do_invoice_label = _('18% ITBIS Ventas')
                        elif tax_amount == 0.0:
                            tax.l10n_do_invoice_label = _('Exento ITBIS Ventas')
                        else:
                            tax.l10n_do_invoice_label = _('{}% ITBIS Ventas').format(int(tax_amount))
                    elif tax_type == 'purchase':
                        if tax_amount == 18.0:
                            tax.l10n_do_invoice_label = _('18% ITBIS Compras')
                        elif tax_amount == 16.0:
                            tax.l10n_do_invoice_label = _('16% ITBIS Compras')
                        elif tax_amount == 9.0:
                            tax.l10n_do_invoice_label = _('9% ITBIS Compras')
                        elif tax_amount == 8.0:
                            tax.l10n_do_invoice_label = _('8% ITBIS Compras')
                        elif tax_amount == 0.0:
                            tax.l10n_do_invoice_label = _('Exento ITBIS Compras')
                        else:
                            tax.l10n_do_invoice_label = _('{}% ITBIS Compras').format(int(tax_amount))
                
                elif 'propina' in tax_name or 'tip' in tax_name:
                    tax.l10n_do_invoice_label = _('10% Propina Legal')
                
                elif 'isc' in tax_name and ('telecom' in tax_name or 'telecommunications' in tax_name):
                    tax.l10n_do_invoice_label = _('10% ISC Telecomunicaciones')
                
                elif 'cdt' in tax_name and ('telecom' in tax_name or 'telecommunications' in tax_name):
                    tax.l10n_do_invoice_label = _('2% CDT Telecomunicaciones')
                
                elif 'transfer' in tax_name and 'bank' in tax_name:
                    tax.l10n_do_invoice_label = _('0.15% Transferencia Bancaria')
                
                # Retenciones ITBIS
                elif 'withholding' in tax_name and 'itbis' in tax_name:
                    if '100%' in tax_name or tax_amount == 100.0:
                        if 'security' in tax_name:
                            tax.l10n_do_invoice_label = _('Retención 100% ITBIS Servicios de Seguridad')
                        elif 'non-profit' in tax_name or 'nonprofit' in tax_name:
                            tax.l10n_do_invoice_label = _('Retención 100% ITBIS Servicios No Lucrativas')
                        elif 'individual' in tax_name or 'person' in tax_name:
                            tax.l10n_do_invoice_label = _('Retención 100% ITBIS Servicios a Físicas')
                        else:
                            tax.l10n_do_invoice_label = _('Retención 100% ITBIS')
                    elif '30%' in tax_name or tax_amount == 30.0:
                        if 'legal' in tax_name:
                            tax.l10n_do_invoice_label = _('Retención 30% ITBIS Servicios a Jurídicas')
                        elif 'professional' in tax_name:
                            tax.l10n_do_invoice_label = _('Retención 30% ITBIS Servicios Profesionales')
                        else:
                            tax.l10n_do_invoice_label = _('Retención 30% ITBIS')
                    elif '75%' in tax_name or tax_amount == 75.0:
                        tax.l10n_do_invoice_label = _('Retención 75% ITBIS Bienes a Informales')
                
                # Retenciones ISR
                elif 'withholding' in tax_name and 'isr' in tax_name:
                    if '10%' in tax_name or tax_amount == 10.0:
                        if 'fee' in tax_name or 'honorario' in tax_name:
                            tax.l10n_do_invoice_label = _('Retención 10% ISR Honorarios a Físicas')
                        elif 'rent' in tax_name or 'alquiler' in tax_name:
                            tax.l10n_do_invoice_label = _('Retención 10% ISR Alquileres a Físicas')
                        elif 'dividend' in tax_name:
                            tax.l10n_do_invoice_label = _('Retención 10% ISR por Dividendos')
                        else:
                            tax.l10n_do_invoice_label = _('Retención 10% ISR')
                    elif '27%' in tax_name or tax_amount == 27.0:
                        tax.l10n_do_invoice_label = _('Retención 27% ISR por Remesas al Exterior')
                    elif '5%' in tax_name or tax_amount == 5.0:
                        tax.l10n_do_invoice_label = _('Retención 5% ISR Gubernamentales')
                    elif '2%' in tax_name or tax_amount == 2.0:
                        tax.l10n_do_invoice_label = _('Retención 2% ISR a Física (con Materiales)')
                
                else:
                    # Mantener la etiqueta original si no hay traducción específica
                    tax.l10n_do_invoice_label = tax.invoice_label or tax.name
            else:
                # Para otros países, usar la etiqueta original
                tax.l10n_do_invoice_label = tax.invoice_label or tax.name

    @api.model
    def _get_invoice_label(self):
        """Obtener la etiqueta traducida para facturas"""
        if self.company_id.country_id.code == 'DO':
            return self.l10n_do_invoice_label or self.invoice_label or self.name
        return self.invoice_label or self.name
