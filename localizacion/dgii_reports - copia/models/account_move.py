# Part of Domincana Premium.
# See LICENSE file for full copyright and licensing details.

import json

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime as dt


class AccountInvoice(models.Model):
    _inherit = "account.move"

    def _valid_field_parameter(self, field, name):
        return name == 'size' or super(AccountInvoice, self)._valid_field_parameter(field, name)
    
    def _is_invoice_paid_for_dgii_reports(self):
        """
        Determina si una factura debe considerarse pagada para efectos de reportes DGII.
        Una factura se considera pagada si:
        1. Está completamente conciliada (amount_residual == 0), O
        2. Tiene payment_state 'in_payment' (pagada pero no conciliada)
        
        Esto considera que los pagos in_process toman tiempo en conciliar
        pero ya están efectivamente pagados.
        """
        self.ensure_one()
        if self.payment_state in ["reversed", "invoicing_legacy"]:
            return False
        
        # Completamente conciliada
        if self.amount_residual == 0:
            return True
            
        # Pagada pero no conciliada (in_payment incluye in_process)
        if self.payment_state == 'in_payment':
            return True
            
        return False

    def _get_invoice_payment_widget(self):
        if hasattr(self, 'invoice_payments_widget') and self.invoice_payments_widget:
            j = self.invoice_payments_widget
            return j["content"] if j else []
        return []

    def _compute_invoice_payment_date(self):
        for inv in self:
            if inv._is_invoice_paid_for_dgii_reports():
                dates = [str(payment["date"]) for payment in inv._get_invoice_payment_widget()]
                
                if dates:
                    max_date = max(dates)
 
                    invoice_date = inv.invoice_date
                    inv.payment_date = max_date if max_date >= str(invoice_date) else invoice_date
                else:
                    # Si no hay fechas de pago en el widget, usar la fecha actual para facturas en in_payment
                    if inv.payment_state == 'in_payment':
                        inv.payment_date = inv.invoice_date
                    else:
                        inv.payment_date = False
            else:
                inv.payment_date = False

    @api.depends('line_ids.tax_ids')
    def _check_isr_tax(self):
        """Restrict one ISR tax per invoice"""
        for inv in self:
            line = [
                tax_line.purchase_tax_type
                for tax_line in inv._get_tax_line_ids()
                if tax_line.purchase_tax_type in ['isr', 'ritbis']
            ]
            if len(line) != len(set(line)):
                raise ValidationError(_('An invoice cannot have multiple'
                                        'withholding taxes.'))

    def _convert_to_local_currency(self, amount):
        sign = -1 if self.move_type in ['in_refund', 'out_refund'] else 1
        amount = self.currency_id._convert(
            amount, self.company_id.currency_id, self.company_id, self.date or fields.Date.context_today(self)
        )
        return amount * sign

    def _get_tax_line_ids(self):
        return self.line_ids.tax_ids
        
    # MODIFICADO: Arturo Diaz Lora - 2026-03-24 10:30
    # Razón: Fix CR8 - product.type "product" no existe en Odoo 19, agregar "combo".
    # Agregar else clause para move_types no purchase.
    @api.depends("invoice_line_ids", "invoice_line_ids.product_id", "state")
    def _compute_amount_fields(self):
        """Compute Purchase amount by product type"""
        for inv in self:
            if inv.move_type in ["in_invoice", "in_refund"] and inv.state != "draft":
                service_amount = 0
                good_amount = 0

                for line in inv.invoice_line_ids:

                    # Monto calculado en bienes (Odoo 19: consu, combo)
                    if line.product_id and line.product_id.type in ["consu", "combo"]:
                        good_amount += line.price_subtotal

                    # Si la linea no tiene un producto → servicio
                    elif not line.product_id:
                        service_amount += line.price_subtotal

                    # Monto calculado en servicio (type == 'service' u otro)
                    else:
                        service_amount += line.price_subtotal

                inv.service_total_amount = inv._convert_to_local_currency(service_amount)
                inv.good_total_amount = inv._convert_to_local_currency(good_amount)
            else:
                inv.service_total_amount = 0
                inv.good_total_amount = 0

    @api.depends('state', 'line_ids.tax_line_id')
    def _compute_isr_withholding_type(self):
        """Compute ISR Withholding Type

        Keyword / Values:
        01 -- Alquileres
        02 -- Honorarios por Servicios
        03 -- Otras Rentas
        04 -- Rentas Presuntas
        05 -- Intereses Pagados a Personas Jurídicas
        06 -- Intereses Pagados a Personas Físicas
        07 -- Retención por Proveedores del Estado
        08 -- Juegos Telefónicos
        """
        for inv in self:
            if inv.state != 'draft':  # Calcular siempre que no esté en borrador

                isr = [tax_line.tax_line_id for tax_line in inv.line_ids if tax_line.tax_line_id.purchase_tax_type == "isr"]

                if isr:
                    tax = isr[0]  # Tomar el primer impuesto ISR
                    # Si el impuesto no tiene isr_retention_type configurado, inferirlo del nombre
                    if tax.isr_retention_type:
                        inv.isr_withholding_type = tax.isr_retention_type
                    else:
                        # Inferir tipo según el nombre del impuesto
                        tax_name = tax.name.get('en_US', '') if isinstance(tax.name, dict) else str(tax.name)
                        if 'honorarios' in tax_name.lower() or 'fee' in tax_name.lower():
                            inv.isr_withholding_type = '02'  # Honorarios por Servicios
                        elif 'gubernamental' in tax_name.lower() or 'gov' in tax_name.lower():
                            inv.isr_withholding_type = '07'  # Retención por Proveedores del Estado
                        elif 'alquiler' in tax_name.lower() or 'rent' in tax_name.lower():
                            inv.isr_withholding_type = '01'  # Alquileres
                        else:
                            inv.isr_withholding_type = '03'  # Otras Rentas (por defecto)

   
    def _get_payment_string(self):
        """Compute Vendor Bills payment method string

        Keyword / Values:
        cash        -- Efectivo
        bank        -- Cheques / Transferencias / Depósitos
        card        -- Tarjeta Crédito / Débito
        credit      -- Compra a Crédito
        swap        -- Permuta
        credit_note -- Notas de Crédito
        mixed       -- Mixto
        """
        payments = []
        p_string = ""

        # Primero intentar con pagos conciliados (método original)
        for payment in self._get_invoice_payment_widget():
            payment_id = self.env["account.payment"].browse(payment.get("account_payment_id"))
            move_id = False
            if payment_id:
                if payment_id.journal_id.type in ["cash", "bank"]:
                    p_string = payment_id.journal_id.l10n_do_payment_form

            if not payment_id:
                move_id = self.env["account.move"].browse(payment.get("move_id"))
                if move_id:
                    p_string = "swap"

            # If invoice is paid, but the payment doesn't come from
            # a journal, assume it is a credit note
            payment = p_string if payment_id or move_id else "credit_note"
            payments.append(payment)

        # Si no hay pagos conciliados, buscar pagos relacionados por partner y fecha
        if not payments and self.payment_state == 'in_payment':
            related_payments = self.env["account.payment"].search([
                ('partner_id', '=', self.partner_id.id),
                ('amount', '=', self.amount_total),
                ('date', '=', self.invoice_date),
                ('state', 'in', ['posted', 'in_process']),
                ('payment_type', '=', 'inbound' if self.move_type == 'out_invoice' else 'outbound')
            ])
            
            for payment in related_payments:
                if payment.journal_id.type in ["cash", "bank"]:
                    p_string = payment.journal_id.l10n_do_payment_form or "bank"
                payments.append(p_string)

        methods = {p for p in payments}
        if len(methods) == 1:
            return list(methods)[0]
        elif len(methods) > 1:
            return "mixed"

    @api.depends("payment_state")
    def _compute_in_invoice_payment_form(self):
        for inv in self:
            if (
                inv.move_type in ["in_invoice", "out_invoice"]
                and inv._is_invoice_paid_for_dgii_reports()
            ):

                payment_dict = {
                    "cash": "01",
                    "bank": "02",
                    "card": "03",
                    "credit": "04",
                    "swap": "05",
                    "credit_note": "06",
                    "mixed": "07",
                }

                inv.payment_form = payment_dict.get(inv._get_payment_string())


            elif (
                inv.payment_state not in ["reversed", "invoicing_legacy"]
                and inv.payment_state != "not_paid"
                and not inv._is_invoice_paid_for_dgii_reports()
            ):
                inv.payment_form = "07"

            else:
                inv.payment_form = "04"

    @api.depends("line_ids.tax_ids", "line_ids.tax_base_amount", "state", "invoice_line_ids")
    def _compute_invoiced_itbis(self):
        """Compute invoice invoiced_itbis taking into account the currency"""
        for inv in self:
            amount = 0
            sign = -1 if inv.move_type in ('out_refund', 'in_refund') else 1
            itbis_taxes = ["ITBIS", "ITBIS 18%"]

            tax_line_id_filter = (lambda aml, tax: True)

            for line in inv.line_ids:
                if (
                    line.tax_line_id 
                    and tax_line_id_filter(line, line.tax_line_id) 
                    and line.tax_line_id.tax_group_id.name in itbis_taxes
                    and line.tax_line_id.purchase_tax_type != "ritbis" 
                ):
                        amount += line.amount_currency

                inv.invoiced_itbis = abs(inv._convert_to_local_currency(amount)) * sign

    def _get_payment_move_iterator(self, payment, inv_type, witheld_type):
        move_id = self.env["account.move"].browse(payment.get("move_id"))
        if move_id:
            if inv_type == "out_invoice":
                return [
                    move_line.debit
                    for move_line in move_id.line_ids
                    if move_line.account_id.account_fiscal_type in witheld_type
                ]
            else:
                return [
                    move_line.credit
                    for move_line in move_id.line_ids
                    if move_line.account_id.account_fiscal_type in witheld_type
                ]
        return []

    # MODIFICADO: Arturo Diaz Lora - 2026-03-24 10:30
    # Razón: CR5 - Agregar payment_state a depends para recomputar al reconciliar.
    # CR2e - Incluir out_refund en branch de ventas.
    @api.depends("state", "line_ids.tax_line_id", "line_ids.amount_currency", "payment_state")
    def _compute_withheld_taxes(self):
        for inv in self:

            inv.withholded_itbis = 0
            inv.income_withholding = 0
            inv.third_withheld_itbis = 0
            inv.third_income_withholding = 0

            if inv.state == 'draft':
                continue

            witheld_itbis_types = ["A34", "A36"]
            witheld_isr_types = ["ISR", "A38"]

            if inv.move_type in ("in_invoice", "in_refund"):
                ritbis_amount = 0
                isr_amount = 0
                for line in inv.line_ids:
                    if line.tax_line_id and line.tax_line_id.purchase_tax_type == "ritbis":
                        ritbis_amount += line.amount_currency
                    if line.tax_line_id and line.tax_line_id.purchase_tax_type == "isr":
                        isr_amount += line.amount_currency

                inv.withholded_itbis = inv._convert_to_local_currency(ritbis_amount) * -1
                inv.income_withholding = inv._convert_to_local_currency(isr_amount) * -1

            elif inv.move_type in ("out_invoice", "out_refund"):
                isr_amount = 0
                ritbis_amount = 0
                for line in inv.line_ids:
                    if line.tax_line_id and line.tax_line_id.purchase_tax_type == "isr":
                        isr_amount += line.amount_currency
                    if line.tax_line_id and line.tax_line_id.purchase_tax_type == "ritbis":
                        ritbis_amount += line.amount_currency

                inv.third_income_withholding = abs(inv._convert_to_local_currency(isr_amount))
                inv.third_withheld_itbis = abs(inv._convert_to_local_currency(ritbis_amount))

            # Retenciones adicionales desde pagos conciliados (account_fiscal_type)
            for payment in inv._get_invoice_payment_widget():
                if inv.move_type in ("out_invoice", "out_refund"):
                    inv.third_withheld_itbis += sum(
                        self._get_payment_move_iterator(payment, inv.move_type, witheld_itbis_types)
                    )
                    inv.third_income_withholding += sum(
                        self._get_payment_move_iterator(payment, inv.move_type, witheld_isr_types)
                    )
                elif inv.move_type in ("in_invoice", "in_refund"):
                    inv.withholded_itbis += sum(
                        self._get_payment_move_iterator(payment, inv.move_type, witheld_itbis_types)
                    )
                    inv.income_withholding += sum(
                        self._get_payment_move_iterator(payment, inv.move_type, witheld_isr_types)
                    )

    @api.depends("invoiced_itbis", "cost_itbis", "state")
    def _compute_advance_itbis(self):
        for inv in self:
            if inv.state != "draft":
                inv.advance_itbis = inv.invoiced_itbis - inv.cost_itbis

    @api.depends("l10n_latam_document_type_id.l10n_do_ncf_type")
    def _compute_is_exterior(self):
        for inv in self:
            inv.is_exterior = True if inv.l10n_latam_document_type_id.l10n_do_ncf_type in ("exterior", "e-exterior") else False

    @api.depends("l10n_latam_document_type_id.doc_code_prefix")
    def _compute_is_e47_b17(self):
        """Compute if invoice is E47 or B17 (Payment to Exterior)
        These types already have l10n_do_expense_type field, so service_type is redundant
        """
        for inv in self:
            inv.is_e47_b17 = True if inv.l10n_latam_document_type_id.doc_code_prefix in ("E47", "B17") else False

    @api.onchange("service_type")
    def onchange_service_type(self):
        self.service_type_detail = False
        return {"domain": {"service_type_detail": [("parent_code", "=", self.service_type)]}}

    @api.onchange("journal_id")
    def ext_onchange_journal_id(self):
        self.service_type = False
        self.service_type_detail = False

    # ISR Percibido       --> Este campo se va con 12 espacios en 0 para el 606
    # ITBIS Percibido     --> Este campo se va con 12 espacios en 0 para el 606
    payment_date = fields.Date(compute="_compute_taxes_fields", store=True)
    service_total_amount = fields.Monetary(
        compute="_compute_amount_fields", store=True, currency_field="company_currency_id"
    )
    good_total_amount = fields.Monetary(
        compute="_compute_amount_fields", store=True, currency_field="company_currency_id"
    )
    invoiced_itbis = fields.Monetary(
        compute="_compute_invoiced_itbis", store=True, currency_field="company_currency_id"
    )
    withholded_itbis = fields.Monetary(
        compute="_compute_withheld_taxes", store=True, currency_field="company_currency_id"
    )
    proportionality_tax = fields.Monetary(
        compute="_compute_taxes_fields", store=True, currency_field="company_currency_id"
    )
    cost_itbis = fields.Monetary(compute="_compute_taxes_fields", store=True, currency_field="company_currency_id")
    advance_itbis = fields.Monetary(compute="_compute_advance_itbis", store=True, currency_field="company_currency_id")
    isr_withholding_type = fields.Char(compute="_compute_isr_withholding_type", store=True, size=2)
    income_withholding = fields.Monetary(
        compute="_compute_withheld_taxes", store=True, currency_field="company_currency_id"
    )
    selective_tax = fields.Monetary(compute="_compute_taxes_fields", store=True, currency_field="company_currency_id")
    other_taxes = fields.Monetary(compute="_compute_taxes_fields", store=True, currency_field="company_currency_id")
    legal_tip = fields.Monetary(compute="_compute_taxes_fields", store=True, currency_field="company_currency_id")
    payment_form = fields.Selection(
        [
            ("01", "Cash"),
            ("02", "Check / Transfer / Deposit"),
            ("03", "Credit Card / Debit Card"),
            ("04", "Credit"),
            ("05", "Swap"),
            ("06", "Credit Note"),
            ("07", "Mixed"),
        ],
        compute="_compute_in_invoice_payment_form",
        store=True,
    )
    third_withheld_itbis = fields.Monetary(
        compute="_compute_withheld_taxes", store=True, currency_field="company_currency_id"
    )
    third_income_withholding = fields.Monetary(
        compute="_compute_withheld_taxes", store=True, currency_field="company_currency_id"
    )
    is_exterior = fields.Boolean(compute="_compute_is_exterior", store=True)
    is_e47_b17 = fields.Boolean(compute="_compute_is_e47_b17", store=True,
                                string="Is E47/B17",
                                help="Indicates if this is a Payment to Exterior (E47/B17) invoice")
    service_type = fields.Selection(
        [
            ("01", "Gastos de Personal"),
            ("02", "Gastos por Trabajos, Suministros y Servicios"),
            ("03", "Arrendamientos"),
            ("04", "Gastos de Activos Fijos"),
            ("05", "Gastos de Representación"),
            ("06", "Gastos Financieros"),
            ("07", "Gastos de Seguros"),
            ("08", "Gastos por Regalías y otros Intangibles"),
        ]
    )
    service_type_detail = fields.Many2one("invoice.service.type.detail")
    fiscal_status = fields.Selection(
        [("normal", "Partial"), ("done", "Reported"), ("blocked", "Not Sent")],
        copy=False,
        help="* The 'Grey' status means ...\n"
        "* The 'Green' status means ...\n"
        "* The 'Red' status means ...\n"
        "* The blank status means that the invoice have"
        "not been included in a report.",
    )

    @api.model
    def norma_recompute(self):
        """
        This method add all compute fields into []env
        add_todo and then recompute
        all compute fields in case dgii config change and need to recompute.
        :return:
        """
        active_ids = self.env.context.get("active_ids")
        invoice_ids = self.browse(active_ids)
        for k, v in self.fields_get().items():
            if v.get("store") and v.get("depends"):
                self.env.add_todo(self._fields[k], invoice_ids)

        self.recompute()
    

    @api.depends("line_ids.tax_ids", "payment_state","state")
    def _compute_taxes_fields(self):
        """Compute invoice common taxes fields"""

        for inv in self:
            sign = -1 if inv.is_inbound() else 1
            tax_line_id_filter = (lambda aml, tax: True)

            if inv.state != "draft":
                isc_amount = 0
                other_taxes = 0  
                legal_tip = 0
                for line in inv.line_ids:

                    # Monto Impuesto Selectivo al Consumo
                    if (
                        line.tax_line_id 
                        and tax_line_id_filter(line, line.tax_line_id) 
                        and line.tax_line_id.tax_group_id.name == "ISC" 
                    ):
                            isc_amount += line.amount_currency

                    # Monto Otros Impuestos/Tasas
                    if (
                        line.tax_line_id 
                        and tax_line_id_filter(line, line.tax_line_id) 
                        and line.tax_line_id.tax_group_id.name == "Otros Impuestos"
                    ):
                            other_taxes += line.amount_currency

                    # Monto Propina Legal
                    if (
                        line.tax_line_id 
                        and tax_line_id_filter(line, line.tax_line_id) 
                        and line.tax_line_id.tax_group_id.name == "Propina"
                    ):
                            legal_tip += line.amount_currency

                # Asignar valores finales calculados
                inv.selective_tax = inv._convert_to_local_currency(isc_amount) * sign
                inv.other_taxes = inv._convert_to_local_currency(other_taxes) * sign
                inv.legal_tip = inv._convert_to_local_currency(legal_tip) * sign

                # ITBIS sujeto a proporcionalidad
                inv.proportionality_tax = inv._convert_to_local_currency(
                    sum(
                        inv.line_ids.filtered(lambda line: line.account_id.account_fiscal_type in ["A29", "A30"]).mapped(
                            "amount_currency"
                        )
                    ))

                # ITBIS llevado al Costo
                inv.cost_itbis = inv._convert_to_local_currency(
                    sum(
                        inv.line_ids.filtered(lambda line: line.account_id.account_fiscal_type == "A51").mapped(
                            "amount_currency"
                        )
                    ))

                # MODIFICADO: Arturo Diaz Lora - 2026-03-24 10:30
                # Razón: CR4 - Consolidar lógica de payment_date en un solo bloque
                # coherente para evitar sobreescritura incorrecta.
                # 1. Si está pagada → fecha del pago
                # 2. Si tiene retenciones pero no pagada → fecha de factura
                # 3. Else → False
                if inv._is_invoice_paid_for_dgii_reports():
                    dates = [str(payment["date"]) for payment in inv._get_invoice_payment_widget()]
                    if dates:
                        max_date = max(dates)
                        invoice_date = inv.invoice_date
                        inv.payment_date = max_date if max_date >= str(invoice_date) else invoice_date
                    elif inv.payment_state == 'in_payment':
                        inv.payment_date = inv.invoice_date
                    else:
                        inv.payment_date = inv.invoice_date
                elif inv.move_type in ("in_invoice", "in_refund") and any([inv.withholded_itbis, inv.income_withholding]):
                    # Factura de compra con retenciones: usar fecha de factura
                    inv.payment_date = inv.invoice_date
                elif inv.move_type in ("out_invoice", "out_refund") and any([inv.third_withheld_itbis, inv.third_income_withholding]):
                    # Factura de venta con retenciones por terceros: usar fecha de factura
                    inv.payment_date = inv.invoice_date
                else:
                    inv.payment_date = False


