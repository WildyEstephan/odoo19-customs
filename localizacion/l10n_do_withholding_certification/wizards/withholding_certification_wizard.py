# -*- coding: utf-8 -*-
# MODIFICADO: Arturo Diaz Lora - 2026-03-19 01:00
# Razón: Corrección completa del wizard de certificación de retención DGII
# Cambios:
#   - Corregido uso deprecado self.env.user.company_id → self.env.company
#   - Campo month ahora almacena nombre del mes en español (no número)
#   - Validación de que existan retenciones (ITBIS o ISR) en las facturas
#   - Filtro de facturas incluye también notas de débito (in_invoice, in_refund)
#   - Campos computados para totales de retención
#   - Mejora en formato de fecha actual

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime

MONTH_MAP = {
    '01': 'Enero',
    '02': 'Febrero',
    '03': 'Marzo',
    '04': 'Abril',
    '05': 'Mayo',
    '06': 'Junio',
    '07': 'Julio',
    '08': 'Agosto',
    '09': 'Septiembre',
    '10': 'Octubre',
    '11': 'Noviembre',
    '12': 'Diciembre',
}


class WithholdingCertificacionWizard(models.TransientModel):
    _name = 'withholding.certification.wizard'
    _description = 'Generar Certificación de Retención DGII'

    partner_id = fields.Many2one('res.partner', string='Proveedor')
    date_from = fields.Date('Desde')
    date_to = fields.Date('Hasta')
    invoice_ids = fields.Many2many(
        'account.move', string='Facturas',
        domain="[('partner_id', '=', partner_id)]",
    )
    month = fields.Char(string='Mes')
    year = fields.Char(string='Año')
    now_date = fields.Char(string='Fecha Actual')

    # MODIFICADO: Arturo Diaz Lora - 2026-03-19 01:00
    # Razón: Campos computados para totales en el reporte
    total_base = fields.Monetary(
        string='Total Base Imponible',
        compute='_compute_totals',
        currency_field='currency_id',
    )
    total_itbis_retenido = fields.Monetary(
        string='Total ITBIS Retenido',
        compute='_compute_totals',
        currency_field='currency_id',
    )
    total_isr_retenido = fields.Monetary(
        string='Total ISR Retenido',
        compute='_compute_totals',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        default=lambda self: self.env.company.currency_id,
    )

    @api.depends('invoice_ids')
    def _compute_totals(self):
        for wizard in self:
            wizard.total_base = sum(wizard.invoice_ids.mapped('amount_untaxed'))
            wizard.total_itbis_retenido = sum(wizard.invoice_ids.mapped('withholded_itbis'))
            wizard.total_isr_retenido = sum(wizard.invoice_ids.mapped('income_withholding'))

    @api.onchange('partner_id', 'date_from', 'date_to')
    def onchange_dates(self):
        if self.date_from and self.date_to and self.partner_id:
            # MODIFICADO: Arturo Diaz Lora - 2026-03-19 01:00
            # Razón: Formato de fecha mejorado sin dependencia de locale del SO
            now = datetime.now()
            month_name = MONTH_MAP[now.strftime("%m")]
            self.now_date = "{} de {} de {}".format(
                now.day, month_name, now.year
            )

            if self.date_from > self.date_to:
                raise ValidationError(
                    _('La fecha "Desde" debe ser anterior a la fecha "Hasta".')
                )

            # MODIFICADO: Arturo Diaz Lora - 2026-03-19 01:00
            # Razón: Usar self.env.company en vez de self.env.user.company_id (deprecado)
            invoices = self.env['account.move'].search([
                ('company_id', '=', self.env.company.id),
                ('partner_id', '=', self.partner_id.id),
                ('invoice_date', '>=', self.date_from),
                ('invoice_date', '<=', self.date_to),
                ('state', '=', 'posted'),
                ('move_type', 'in', ('in_invoice', 'in_refund')),
            ])

            # MODIFICADO: Arturo Diaz Lora - 2026-03-19 01:00
            # Razón: Mes como nombre en español, no como número
            self.month = MONTH_MAP.get(
                str(self.date_to.month).zfill(2), ''
            )
            self.year = str(self.date_to.year)
            self.invoice_ids = [(6, 0, invoices.ids)]

    def generate_certification(self):
        if not self.invoice_ids:
            raise ValidationError(
                _('No se puede generar una certificación de retención sin facturas.')
            )

        # MODIFICADO: Arturo Diaz Lora - 2026-03-19 01:00
        # Razón: Validar que al menos una factura tenga retenciones
        has_withholding = any(
            inv.withholded_itbis > 0 or inv.income_withholding > 0
            for inv in self.invoice_ids
        )
        if not has_withholding:
            raise ValidationError(
                _('Las facturas seleccionadas no tienen retenciones de ITBIS ni de ISR. '
                  'No se puede generar una certificación sin retenciones.')
            )

        return self.env.ref(
            'l10n_do_withholding_certification.withholding_certification_report'
        ).report_action(self.id, config=False)
