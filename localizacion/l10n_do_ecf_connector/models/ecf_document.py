from odoo import api, fields, models, _
from odoo.exceptions import UserError, RedirectWarning, ValidationError
from . import E31
from . import E32
from . import E33
from . import E34
from . import E41
from . import E43
from . import E44
from . import E45
from . import E46
from . import E47
from odoo.tools import float_compare

from lxml import etree
from ..netvux_api import NETVUXApi
from collections import OrderedDict
import re
import subprocess
import tempfile
import base64
import logging
import requests
import pyqrcode

import json
import xmltodict

_logger = logging.getLogger(__name__)
parser = etree.XMLParser(remove_blank_text=True)

ECF_STATE_MAP = {
    "Aceptado": "delivered_accepted",
    "Aceptado Condicional": "conditionally_accepted",
    "En Proceso": "delivered_pending",
    "Rechazado": "delivered_refused",
    "No encontrado": "not_found",
}


def _get_l10n_do_ecf_send_state(self):
    """Returns actual invoice ECF sending status

    - to_send: default state.
    - invalid: sent ecf didn't pass XSD validation.
    - contingency: DGII unreachable by external service. Odoo should send it later
      until delivered accepted state is received.
    - delivered_accepted: expected state that indicate everything is ok with ecf
      issuing.
    - conditionally_accepted: DGII has accepted the ECF but has some remarks
    - delivered_refused: ecf rejected by DGII.
    - not_sent: Odoo have not connection.
    - service_unreachable: external service may be down.
    - signed_pending: ECF was signed but API could not reach DGII. May be resend
      later.

    """
    return [
        ("to_send", _("To sent")),
        ("signed_pending", _("Signed and pending")),
        ("not_sent", _("Could not send the e-CF")),
        ("contingency", _("Contingency")),
        ("delivered_accepted", _("Delivered and accepted")),
        ("conditionally_accepted", _("Conditionally accepted")),
        ("delivered_pending", _("Delivered and pending")),
        ("delivered_refused", _("Delivered and refused")),
        ("not_found", _("Not Found")),
    ]


class ECFDocument(models.Model):
    _name = 'ecf.document'
    _description = 'Electronic Document'
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string='e-NCF', readonly=True)
    invoice_id = fields.Many2one('account.move', string='Invoice', ondelete='cascade', readonly=True,
                                 required=True, index=True)
    l10n_latam_document_type_id = fields.Many2one('l10n_latam.document.type', string='Voucher Type', readonly=True)
    ncf_type = fields.Char(compute="_compute_ncf_type")
    is_rfce = fields.Boolean(compute="_compute_ncf_type", string="Is RFCE")
    l10n_do_ecf_send_state = fields.Selection(selection=_get_l10n_do_ecf_send_state, string="e-CF Send State",
                                              copy=False, required=True, readonly=True, default="to_send",
                                              tracking=True, index=True,
                                              help="No enviado(Estado por defecto): ECF en borrador. En este punto aun no se ha enviado el xml."
                                                   "\n Firmado y pendiente: ECF firmado y pendiente de enviar a la DGII."
                                                   "\n Error al enviar a DGII: Odoo no tine conexion."
                                                   "\n Aceptado: ECF recepcionado y procesado de forma exitosa por la FGII."
                                                   "\n Aceptado Condicional: ECF recepcionado y procesado, no cumplió en algún punto pero que no ameritó el rechazo."
                                                   "\n Pendiente: ECF recepcionado y procesado, corresponde a que el comprobante aún no ha sido validado y por ende se debe esperar un tiempo prudencial antes de volver a consultar."
                                                   "\n Rechazado: ECF recepcionado y procesado, implica la nulidad del comprobante para fines tributario debido a que en algún punto no cumplió."
                                              )
    company_id = fields.Many2one('res.company', string='Company', required=True)
    company_currency_id = fields.Many2one(
        string='Company Currency',
        related='company_id.currency_id', readonly=True,
    )
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    xml_file = fields.Binary("XML File", attachment=True,
                             help="This field holds the XML file generated and signed by system")
    xml_file_name = fields.Char("Name of XML file")

    xml_netvux_file = fields.Binary("XML NETVUX File", attachment=True,
                                    help="This field holds the XML file generated and signed by system")
    xml_netvux_file_name = fields.Char("Name of NETVUX XML file")

    currency_id = fields.Many2one('res.currency', readonly=True, string='Currency')
    xml_amount_tax = fields.Monetary('Amount Total Tax')
    xml_amount_total = fields.Monetary('Amount Total')
    xml_amount_untaxed_signed = fields.Monetary('Amount Untaxed Signed', related="invoice_id.amount_untaxed_signed")
    send_dgii = fields.Boolean(compute="_compute_send_dgii")

    # Response DGII
    xml_dgii_file = fields.Binary(string="XML DGII File", attachment=True, copy=False)
    xml_dgii_file_name = fields.Char(string="Nombre Archivo XML", copy=False)
    message_detail_dgii = fields.Text(string="Archivo XML Text", copy=False)

    # QR
    l10n_do_ecf_security_code = fields.Char(string="e-CF Security Code", copy=False, readonly=True)
    l10n_do_ecf_sign_date = fields.Char(string="e-CF Sign Date", copy=False, readonly=True)
    l10n_do_electronic_stamp = fields.Text(string="Electronic Stamp", copy=False, readonly=True)
    QR_code = fields.Binary(string="Code QR", readonly=True, copy=False)

    netvux_warning_message = fields.Html(readonly=True, copy=False, default="")

    # === COMPUTE METHODS ===#

    def _compute_send_dgii(self):
        for record in self:
            record.send_dgii = record.l10n_do_ecf_send_state in ['delivered_accepted', 'conditionally_accepted',
                                                                 'delivered_pending', 'delivered_refused']

    def _compute_ncf_type(self):
        for record in self:
            l10n_do_ncf_type = record.get_l10n_do_ncf_type()
            record.ncf_type = l10n_do_ncf_type
            record.is_rfce = (record.xml_amount_untaxed_signed and l10n_do_ncf_type == '32') and \
                             record.xml_amount_untaxed_signed < 250000 or False

    # ===== BUTTONS =====

    def action_gen_xml(self):
        self.ensure_one()

        if len(self.invoice_id.invoice_line_ids) == 0 or abs(self.xml_amount_untaxed_signed) == 0.00:
            # Order is amount == 0 and no lines in it,
            # let's not create an XML for it
            return False
        try:
            cedoc = self._gen_cedoc()
            file = tempfile.NamedTemporaryFile(delete=False)
            file.write(b'<?xml version="1.0" encoding="utf-8"?>')
            cedoc.export(file, 0, namespacedef_="", pretty_print=True)
            file.write(b'\n')
            file.close()

            return self._xml_doc(file.name)
        except Exception as e:
            self.message_post(body="No se pudo generar el XML: \n %s" % e)
            return False

    def action_recreate_xml(self):
        self.xml_file = None
        self.action_gen_xml()
        self.action_send_to_netvux()

    def action_send_to_netvux(self):
        company_id = self.company_id
        if not company_id.ecf_config:
            action = self.env.ref("base.action_res_company_form")
            msg = _("Must be selected an Environment in a Company.")
            raise RedirectWarning(msg, action.id, _("Go to Setting"))

        return self._send_to_netvux()

    def action_request_state_to_netvux(self):
        company_id = self.company_id
        if not company_id.ecf_config:
            action = self.env.ref("base.action_res_company_form")
            msg = _("Must be selected an Environment in a Company.")
            raise RedirectWarning(msg, action.id, _("Go to Setting"))

        ceconfig = company_id.ecf_config
        env = ceconfig.environment
        if env == 'CerteCF':
            raise UserError(_("This service is not available in this environment (%s)") % env)

        return self._action_request_state_to_netvux()

    # === BUSINESS METHODS ===#

    def _xml_doc(self, filename):
        if self.xml_file:
            raise ValidationError(_('Error XML file already generated and cannot be modified'))

        company_id = self.company_id
        if not company_id.ecf_config:
            action = self.env.ref("base.action_res_company_form")
            msg = _("Must be selected an Environment in a Company.")
            raise RedirectWarning(msg, action.id, _("Go to Setting"))

        ecf_name = self.name
        args = 'mv ' + filename
        args = args.split()
        signed_filename = "/tmp/{}.xml".format(ecf_name)
        args.append(signed_filename)
        subprocess.run(args)
        xml_f = open(signed_filename, 'rb')
        xml_file = xml_f.read()
        xml_encoded = bytes(xml_file)
        subprocess.call(['rm', '-f', signed_filename])

        _logger.info("##### ECF GENERADO: " + signed_filename)

        self.write({"xml_file": base64.b64encode(xml_encoded),
                    "xml_file_name": "{}.xml".format(ecf_name),
                    })

        xml_f.close()
        return True

    def gen_emisor(self, classdoc):
        """Retorna la instancia de un emisor

            :param object classdoc: Clase del tipo de documento.
            """

        if not self.company_id.vat:
            raise ValidationError(_('Your company has not defined an NIF.'))
        if not self.company_id.name:
            raise ValidationError(_('Your company has not defined an Name.'))
        if not self.company_id.street or not len(str(self.company_id.street).strip()):
            action = self.env.ref("base.action_res_company_form")
            msg = _('Your company has not defined a street.')
            raise RedirectWarning(msg, action.id, _("Go to Companies"))

        emisor = classdoc.Emisor(RNCEmisor=self.company_id.vat,
                                 RazonSocialEmisor=self.limit(self.company_id.name, 150),
                                 DireccionEmisor=self.limit(self.company_id.street, 100),
                                 FechaEmision=self.invoice_id.invoice_date,
                                 )

        return emisor

    def gen_totales(self, classdoc, cedoc):
        """Invoice amounts related values.

            :param object classdoc: Clase del tipo de documento.
            """
        self.ensure_one()

        self.xml_amount_tax = self.invoice_id.amount_tax
        self.xml_amount_total = self.invoice_id.amount_total

        l10n_do_ncf_type = self.ncf_type
        tax_data = self.get_taxed_amount_data()
        total_taxed = sum(
            [
                tax_data["18_taxed_base"],
                tax_data["16_taxed_base"],
                tax_data["0_taxed_base"],
            ]
        )
        total_itbis = sum(
            [
                tax_data["18_taxed_amount"],
                tax_data["16_taxed_amount"],
                tax_data["0_taxed_amount"],
            ]
        )

        rate = 1
        is_company_currency = self.is_company_currency()
        if not is_company_currency:
            rate = abs(
                round(1 / (self.invoice_id.amount_total / (self.invoice_id.amount_total_signed or 1) or 1), 2)
            )

        if l10n_do_ncf_type not in ("43", "44") and total_taxed:
            totales = classdoc.Totales(
                MontoTotal=abs(round(total_taxed + total_itbis + tax_data['exempt_amount'], 2) * rate))
        else:
            totales = classdoc.Totales(MontoTotal=abs(round(self.invoice_id.amount_untaxed, 2) * rate))

        if l10n_do_ncf_type not in ("43", "44", "47"):
            # ✅ REGLA ESPECIAL E46: Forzar campos obligatorios de Totales
            if l10n_do_ncf_type == "46":
                monto_total_sin_impuestos = abs(round(self.invoice_id.amount_untaxed, 2)) * rate
                totales.set_MontoGravadoTotal(monto_total_sin_impuestos)
                totales.set_MontoGravadoI3(monto_total_sin_impuestos)
                totales.set_ITBIS3(0)
                totales.set_TotalITBIS(0.00)
                totales.set_TotalITBIS3(0.00)
                _logger.info(f"🔥 E46 ECF - Forzando MontoGravadoTotal={monto_total_sin_impuestos}, MontoGravadoI3={monto_total_sin_impuestos}, ITBIS3=0, TotalITBIS=0.00, TotalITBIS3=0.00")
            else:
                if total_taxed:
                    totales.set_MontoGravadoTotal(abs(round(total_taxed, 2)) * rate)
                if tax_data["18_taxed_base"]:
                    totales.set_MontoGravadoI1(abs(round(tax_data["18_taxed_base"], 2)) * rate)
                if tax_data["16_taxed_base"]:
                    totales.set_MontoGravadoI2(abs(round(tax_data["16_taxed_base"], 2)) * rate)
                if tax_data["0_taxed_base"]:
                    totales.set_MontoGravadoI3(abs(round(tax_data["0_taxed_base"], 2)) * rate)
                if tax_data["exempt_amount"]:
                    totales.set_MontoExento(abs(round(tax_data["exempt_amount"], 2)) * rate)
                if tax_data["18_taxed_base"]:
                    totales.set_ITBIS1(18)
                if tax_data["16_taxed_base"]:
                    totales.set_ITBIS2(16)
                if tax_data["0_taxed_base"]:
                    totales.set_ITBIS3(0)
                if tax_data["0_taxed_base"]:
                    totales.set_TotalITBIS(0)
                if total_taxed:
                    totales.set_TotalITBIS(abs(round(total_itbis, 2)) * rate)
                if tax_data["18_taxed_base"]:
                    totales.set_TotalITBIS1(abs(round(tax_data["18_taxed_amount"], 2)) * rate)
                if tax_data["16_taxed_base"]:
                    totales.set_TotalITBIS2(abs(round(tax_data["16_taxed_amount"], 2)) * rate)
                if tax_data["0_taxed_base"]:
                    totales.set_TotalITBIS3(abs(round(tax_data["0_taxed_amount"], 2)) * rate)
        else:
            if tax_data["exempt_amount"]:
                totales.set_MontoExento(abs(round(tax_data["exempt_amount"], 2)) * rate)

        if l10n_do_ncf_type not in ("43", "44", "45"):
            if tax_data["itbis_withholding_amount"] or l10n_do_ncf_type == "41":
                totales.set_TotalITBISRetenido(abs(
                    round(tax_data["itbis_withholding_amount"], 2)
                ) * rate)
            if tax_data["isr_withholding_amount"] or l10n_do_ncf_type in ("41", "47"):
                totales.set_TotalISRRetencion(abs(
                    round(tax_data["isr_withholding_amount"], 2)
                ) * rate)

        # if l10n_do_ncf_type not in ("43", "44", "47"):
        #     self.xml_amount_tax = totales.get_TotalITBIS()
        #
        # self.xml_amount_total = totales.get_MontoTotal()

        return totales

    def _get_taxed_tips_data(self, detalles_items):
        group_data = {"001": {'TipoImpuesto': "001",
                              "TasaImpuestoAdicional": 10.0,
                              "OtrosImpuestosAdicionales": 0.00,
                              }}

        for it in detalles_items.get_Item():
            if it.get_TablaImpuestoAdicional():
                imp_ad = it.get_TablaImpuestoAdicional()
                for aa in imp_ad.get_ImpuestoAdicional():
                    tax_tips_id = self.env["account.tax"].search([('ecf_code', '=', aa.get_TipoImpuesto()),
                                                                  ('company_id', 'parent_of', self.company_id.ids),
                                                                  ('country_id', '=', self.env.ref("base.do").id)
                                                                  ], limit=1)
                    value_tax = (it.get_MontoItem() * tax_tips_id.amount) / 100

                    row = group_data[aa.get_TipoImpuesto()]
                    row['OtrosImpuestosAdicionales'] += value_tax

        return group_data

    def _gen_otra_mondeda(self, classdoc):
        """Only used if invoice currency is not company currency

            :param object classdoc: Clase del tipo de documento.
            """

        otra_mondeda = classdoc.OtraMoneda()
        otra_mondeda.set_TipoMoneda(self.currency_id.name)
        otra_mondeda.set_TipoCambio(abs(
            round(1 / (self.invoice_id.amount_total / (self.invoice_id.amount_total_signed or 1) or 1), 2)
        ))

        return otra_mondeda

    def _get_item_withholding_vals(self, invoice_line):
        """ Returns invoice line withholding taxes values """

        price_unit_untaxed = self._construct_tax_excluded(invoice_line.price_unit, invoice_line)
        line_withholding_vals = invoice_line.tax_ids.compute_all(
            # price_unit=invoice_line.price_unit,
            price_unit=price_unit_untaxed,
            currency=invoice_line.currency_id,
            quantity=invoice_line.quantity,
            product=invoice_line.product_id,
            partner=invoice_line.move_id.partner_id,
            is_refund=True if invoice_line.move_id.move_type == "in_refund" else False,
        )

        withholding_vals = OrderedDict()
        itbis_group = self.env["account.tax.group"].search(
            [("name", '=', 'ITBIS'),
             ('company_id', 'parent_of', self.company_id.ids),
             ('country_id', '=', self.env.ref("base.do").id)], limit=1)
        isr_group = self.env["account.tax.group"].search(
            [("name", '=', 'ISR'),
             ('company_id', 'parent_of', self.company_id.ids),
             ('country_id', '=', self.env.ref("base.do").id)], limit=1)

        itbis_withhold_amount = abs(
            sum(
                tax["amount"]
                for tax in line_withholding_vals["taxes"]
                if tax["amount"] < 0
                and self.env["account.tax"].browse(tax["id"]).tax_group_id == itbis_group
            )
        )
        isr_withhold_amount = abs(
            sum(
                tax["amount"]
                for tax in line_withholding_vals["taxes"]
                if tax["amount"] < 0
                and self.env["account.tax"].browse(tax["id"]).tax_group_id == isr_group
            )
        )

        # Corrección Error [272]: Redondear a 2 decimales para cumplir con XSD
        # Tipo: Decimal18D1or2ValidationTypeMayorIgualCero - máximo 2 decimales
        # Autor: Arturo Diaz Lora - 2025-12-10
        if itbis_withhold_amount or self.ncf_type == "41":
            withholding_vals["MontoITBISRetenido"] = round(itbis_withhold_amount, 2)

        # Corrección Error [272]: MontoISRRetenido solo se envía si hay retención ISR > 0
        # Según XSD e-CF 41: minOccurs="0" (campo OPCIONAL)
        # Si no hay retención ISR, NO se debe incluir el tag en el XML
        # Autor: Arturo Diaz Lora - 2025-12-11
        if isr_withhold_amount > 0:
            withholding_vals["MontoISRRetenido"] = round(isr_withhold_amount, 2)
        return withholding_vals

    def _construct_tax_excluded(self, price, line):
        res = line.tax_ids.compute_all(price, product=line.product_id, partner=self.env['res.partner'])
        excluded = res['total_excluded']
        return excluded

    def _gen_invoice(self, cedoc, classdoc):
        """Product lines related values

            :param object cedoc: Instancia u objeto del Elemento raiz.
            :param object classdoc: Clase del tipo de documento.

            :returns: tuple (response, vals)
            """

        detalle = classdoc.DetallesItems()
        is_company_currency = self.is_company_currency()

        itbis_group = self.env["account.tax.group"].search(
            [("name", '=', 'ITBIS'),
             ('company_id', 'parent_of', self.company_id.ids),
             ('country_id', '=', self.env.ref("base.do").id)], limit=1)

        tips_group = self.env["account.tax.group"].search(
            [("name", '=', 'Propina'),
             ('company_id', 'parent_of', self.company_id.ids),
             ('country_id', '=', self.env.ref("base.do").id)], limit=1)

        l10n_do_ncf_type = self.ncf_type

        def get_invoicing_indicator(inv_line):
            "IndicadorFacturacion"
            if l10n_do_ncf_type in ('43', '44', '47'):
                return 4

            # REGLA ESPECIAL E46: SIEMPRE TASA CERO (3)
            # Según documentación DGII y XMLs aceptados, E46 solo usa IndicadorFacturacion = 3
            if l10n_do_ncf_type == "46":
                return 3  # TASA CERO obligatorio para exportaciones

            if not inv_line.tax_ids:
                return 4
            tax_set = set(
                tax.amount
                for tax in inv_line.tax_ids
                if tax.tax_group_id.id == itbis_group.id
            )
            if len(tax_set) > 1 or 18 in tax_set:
                return 1
            elif 16 in tax_set:
                return 2
            elif 0 in tax_set:
                return 3
            else:
                return 4

        for i, line in enumerate(
                self.invoice_id.invoice_line_ids.filtered(lambda l: l.display_type == 'product' and l.quantity).sorted(
                    "sequence"
                ),
                1,
        ):
            total_discount = 0.00
            rate = 1
            if cedoc.get_Encabezado().get_OtraMoneda():
                rate = cedoc.get_Encabezado().get_OtraMoneda().get_TipoCambio()

            product_id = line.product_id
            product_name = product_id.name if product_id else line.name

            price_unit_untaxed = self._construct_tax_excluded(line.price_unit, line)

            item = classdoc.Item(
                NumeroLinea=i,
                NombreItem=self.limit(product_name, 80),
                IndicadorBienoServicio=2
                if (product_id and product_id.type == "service") or l10n_do_ncf_type == "47"
                else 1,
                CantidadItem=abs(line.quantity),
                PrecioUnitarioItem=abs(
                    round(
                        # line.price_unit if is_company_currency else line.price_unit * rate,
                        price_unit_untaxed if is_company_currency else price_unit_untaxed * rate,
                        4,
                    )
                ),
                # MontoItem=(line.quantity * line.price_unit) * rate,
                MontoItem=(line.quantity * price_unit_untaxed) * rate,
                IndicadorFacturacion=get_invoicing_indicator(line),
            )

            if l10n_do_ncf_type in ("41", "47"):  # Tag Retencion es obligatorio en E41 y E47.
                withholding_vals = OrderedDict([("IndicadorAgenteRetencionoPercepcion", 1)])
                for k, v in self._get_item_withholding_vals(line).items():
                    withholding_vals[k] = round(
                        v if is_company_currency else v * rate, 2
                    )
                retencion = classdoc.Retencion(IndicadorAgenteRetencionoPercepcion=1)

                for val in withholding_vals:
                    if val == 'MontoITBISRetenido':
                        retencion.set_MontoITBISRetenido(withholding_vals[val])
                    if val == 'MontoISRRetenido':
                        retencion.set_MontoISRRetenido(withholding_vals[val])

                item.set_Retencion(retencion)

            if line.discount and l10n_do_ncf_type not in ("41", "43", "44", "46", "47"):
                # price_wo_discount = line.quantity * line.price_unit
                price_wo_discount = line.quantity * price_unit_untaxed
                price_with_discount = price_wo_discount * (1 - (line.discount / 100.0))

                discount_amount = (
                    abs(round(price_with_discount - price_wo_discount, 2))
                    if line.discount
                    else 0
                )

                discount_amount = (
                    discount_amount
                    if is_company_currency
                    else round(discount_amount * rate, 2)
                )

                total_discount += discount_amount
                item.set_DescuentoMonto(discount_amount)
                tabla_sub_descuento = classdoc.TablaSubDescuento()

                sub_descuento = classdoc.SubDescuento(TipoSubDescuento="%",
                                                      SubDescuentoPorcentaje=line.discount,
                                                      MontoSubDescuento=discount_amount)

                tabla_sub_descuento.add_SubDescuento(sub_descuento)
                item.set_TablaSubDescuento(tabla_sub_descuento)

            if total_discount:
                item.set_MontoItem(item.get_MontoItem() - total_discount)

            if line.name:
                item.set_DescripcionItem(self.limit(line.name, 100))

            if line.product_uom_id:
                if not line.product_uom_id.ecf_code:
                    raise ValidationError('La unidad de medida no tiene codigo para la DGII.')
                item.set_UnidadMedida(line.product_uom_id.ecf_code)

            # Tax Tip
            taxes = line.tax_ids.filtered(lambda imp: imp.tax_group_id.id == tips_group.id)
            if taxes:
                tabla_imp_ad = classdoc.ImpuestosAdicionales()

                for t in taxes:
                    imp1 = classdoc.ImpuestoAdicional(TipoImpuesto=t.ecf_code)
                    tabla_imp_ad.add_ImpuestoAdicional(imp1)

                item.set_TablaImpuestoAdicional(tabla_imp_ad)

            detalle.add_Item(item)

        cedoc.set_DetallesItems(detalle)
        return cedoc

    def _gen_informacion_referencia(self, cedoc, classdoc, origin_id):
        """Informacion Referencia

            :param object cedoc: Instancia del Elemento raiz.
            :param object classdoc: Clase del tipo de documento.
            :param object origin_id: Origen.

            :returns: tuple (response, vals)
            """

        info_referencia = classdoc.InformacionReferencia(NCFModificado=self.invoice_id.l10n_do_origin_ncf,
                                                         FechaNCFModificado=origin_id.invoice_date,
                                                         CodigoModificacion=int(
                                                             self.invoice_id.l10n_do_ecf_modification_code),
                                                         )
        if self.invoice_id.ref:
            info_referencia.set_RazonModificacion(self.invoice_id.ref)

        cedoc.set_InformacionReferencia(info_referencia)

    def gen_encabezado(self):
        """Logica y validaciones del encabezado de tipo de documento.

            :returns: obj del encabezado del tipo de documento electronico.
            """

        ceconfig = self.company_id.ecf_config
        l10n_do_ncf_type = self.ncf_type
        version = ceconfig.ce_version.name
        invoice_id = self.invoice_id

        indicador_monto_gravado = 0  # Only 0: no tienen ITBIS incluido.

        if l10n_do_ncf_type == "31":
            """Factura de Credito Fiscal Electronica"""
            if not self.name:
                raise ValidationError('No esta definida la secuencia para este tipo de documento.')

            if not invoice_id.l10n_do_ncf_expiration_date:
                raise ValidationError(
                    'No esta definida la fecha de vencimiento de la secuencia para este tipo de comprobante.')
            classdoc = E31

            IdDoc = classdoc.IdDoc(TipoeCF=l10n_do_ncf_type,
                                   eNCF=self.name,
                                   FechaVencimientoSecuencia=invoice_id.l10n_do_ncf_expiration_date,
                                   TipoIngresos=invoice_id.l10n_do_income_type,
                                   TipoPago=self.get_payment_type(),
                                   )

            IdDoc.set_IndicadorMontoGravado(indicador_monto_gravado)

            if IdDoc.get_TipoPago() == 2:  # Pago a credito
                IdDoc.set_FechaLimitePago(invoice_id.invoice_date_due)
            if invoice_id.invoice_payment_term_id:
                delta = invoice_id.invoice_date_due - invoice_id.invoice_date
                IdDoc.set_TerminoPago(self.limit("%s días" % delta.days, 15))

            emisor = self.gen_emisor(classdoc)
            comprador = self.gen_comprador(classdoc)
            encabezado = classdoc.Encabezado(Version=version,
                                             IdDoc=IdDoc,
                                             Emisor=emisor,
                                             Comprador=comprador,
                                             )

            is_company_currency = self.is_company_currency()
            if not is_company_currency:
                otra_moneda = self._gen_otra_mondeda(classdoc)
                encabezado.set_OtraMoneda(otra_moneda)

            return encabezado
        elif l10n_do_ncf_type == '32':
            """Factura de Consumo Electronica"""
            if not self.name:
                raise ValidationError('No esta definida la secuencia para este tipo de documento.')

            classdoc = E32
            IdDoc = classdoc.IdDoc(TipoeCF=l10n_do_ncf_type,
                                   eNCF=self.name,
                                   TipoIngresos=invoice_id.l10n_do_income_type,
                                   TipoPago=self.get_payment_type(),
                                   )
            IdDoc.set_IndicadorMontoGravado(indicador_monto_gravado)

            if IdDoc.get_TipoPago() == 2:  # Pago a credito
                IdDoc.set_FechaLimitePago(invoice_id.invoice_date_due)
            if invoice_id.invoice_payment_term_id:
                delta = invoice_id.invoice_date_due - invoice_id.invoice_date
                IdDoc.set_TerminoPago(self.limit("%s días" % delta.days, 15))

            emisor = self.gen_emisor(classdoc)
            comprador = self.gen_comprador(classdoc)
            encabezado = classdoc.Encabezado(Version=version,
                                             IdDoc=IdDoc,
                                             Emisor=emisor,
                                             Comprador=comprador,
                                             )
            is_company_currency = self.is_company_currency()
            if not is_company_currency:
                otra_moneda = self._gen_otra_mondeda(classdoc)
                encabezado.set_OtraMoneda(otra_moneda)

            return encabezado
        elif l10n_do_ncf_type == '33':
            """Nota de Débito Electrónica"""
            if not self.name:
                raise ValidationError('No esta definida la secuencia para este tipo de documento.')

            if not invoice_id.l10n_do_ncf_expiration_date:
                raise ValidationError(
                    'No esta definida la fecha de vencimiento de la secuencia para este tipo de comprobante.')

            classdoc = E33
            IdDoc = classdoc.IdDoc(TipoeCF=l10n_do_ncf_type,
                                   eNCF=self.name,
                                   FechaVencimientoSecuencia=invoice_id.l10n_do_ncf_expiration_date,
                                   TipoIngresos=invoice_id.l10n_do_income_type,
                                   TipoPago=self.get_payment_type(),
                                   )

            IdDoc.set_IndicadorMontoGravado(indicador_monto_gravado)

            if IdDoc.get_TipoPago() == 2:  # Pago a credito
                IdDoc.set_FechaLimitePago(invoice_id.invoice_date_due)
            if invoice_id.invoice_payment_term_id:
                delta = invoice_id.invoice_date_due - invoice_id.invoice_date
                IdDoc.set_TerminoPago(self.limit("%s días" % delta.days, 15))

            emisor = self.gen_emisor(classdoc)
            comprador = self.gen_comprador(classdoc)
            encabezado = classdoc.Encabezado(Version=version,
                                             IdDoc=IdDoc,
                                             Emisor=emisor,
                                             Comprador=comprador,
                                             )

            is_company_currency = self.is_company_currency()
            if not is_company_currency:
                otra_moneda = self._gen_otra_mondeda(classdoc)
                encabezado.set_OtraMoneda(otra_moneda)

            return encabezado
        elif l10n_do_ncf_type == '34':
            """Nota de Crédito Electrónica"""
            if not self.name:
                raise ValidationError('No esta definida la secuencia para este tipo de documento.')

            classdoc = E34

            credit_origin_id = self.env["account.move"].sudo().search(
                [("l10n_latam_document_number", "=", invoice_id.l10n_do_origin_ncf)], limit=1
            )

            if float_compare(abs(invoice_id.amount_total_signed), credit_origin_id.amount_total_signed, 2) == 1:
                raise UserError("El monto total deberá ser menor o igual al monto total del e-CF modificado.")

            IdDoc = classdoc.IdDoc(TipoeCF=l10n_do_ncf_type,
                                   eNCF=self.name,
                                   TipoIngresos=invoice_id.l10n_do_income_type,
                                   TipoPago=self.get_payment_type(),
                                   )

            IdDoc.set_IndicadorMontoGravado(indicador_monto_gravado)

            if self.company_id.l10n_do_ecf_deferred_submissions:
                IdDoc.set_IndicadorEnvioDiferido(1)
            if invoice_id.invoice_date_due:
                IdDoc.set_FechaLimitePago(invoice_id.invoice_date_due)

            emisor = self.gen_emisor(classdoc)
            comprador = self.gen_comprador(classdoc)
            encabezado = classdoc.Encabezado(Version=version,
                                             IdDoc=IdDoc,
                                             Emisor=emisor,
                                             Comprador=comprador,
                                             )

            is_company_currency = self.is_company_currency()
            if not is_company_currency:
                otra_moneda = self._gen_otra_mondeda(classdoc)
                encabezado.set_OtraMoneda(otra_moneda)

            return encabezado
        elif l10n_do_ncf_type == '41':
            """Compras Electrónico"""
            if not self.name:
                raise ValidationError('No esta definida la secuencia para este tipo de documento.')

            if not invoice_id.l10n_do_ncf_expiration_date:
                # Como es una compra se toma la fecha vencimiento secuencia de la compañia.
                l10n_do_ncf_expiration_date = invoice_id.company_id.l10n_do_ncf_exp_date
            else:
                l10n_do_ncf_expiration_date = invoice_id.l10n_do_ncf_expiration_date

            if not l10n_do_ncf_expiration_date:
                raise ValidationError(
                    'No esta definida la fecha de vencimiento de la secuencia para este tipo de comprobante.')

            classdoc = E41
            IdDoc = classdoc.IdDoc(TipoeCF=l10n_do_ncf_type,
                                   eNCF=self.name,
                                   FechaVencimientoSecuencia=l10n_do_ncf_expiration_date,
                                   TipoPago=self.get_payment_type(),
                                   )

            IdDoc.set_IndicadorMontoGravado(indicador_monto_gravado)

            if IdDoc.get_TipoPago() == 2:  # Pago a credito
                IdDoc.set_FechaLimitePago(invoice_id.invoice_date_due)
            if invoice_id.invoice_payment_term_id:
                delta = invoice_id.invoice_date_due - invoice_id.invoice_date
                IdDoc.set_TerminoPago(self.limit("%s días" % delta.days, 15))

            emisor = self.gen_emisor(classdoc)
            comprador = self.gen_comprador(classdoc)
            encabezado = classdoc.Encabezado(Version=version,
                                             IdDoc=IdDoc,
                                             Emisor=emisor,
                                             Comprador=comprador,
                                             )

            is_company_currency = self.is_company_currency()
            if not is_company_currency:
                otra_mondeda = self._gen_otra_mondeda(classdoc)
                encabezado.set_OtraMoneda(otra_mondeda)

            return encabezado
        elif l10n_do_ncf_type == '43':
            """Gastos Menores Electrónico"""
            if not self.name:
                raise ValidationError('No esta definida la secuencia para este tipo de documento.')

            if not invoice_id.l10n_do_ncf_expiration_date:
                # Como es una compra se toma la fecha vencimiento secuencia de la compañia.
                l10n_do_ncf_expiration_date = invoice_id.company_id.l10n_do_ncf_exp_date
            else:
                l10n_do_ncf_expiration_date = invoice_id.l10n_do_ncf_expiration_date

            if not l10n_do_ncf_expiration_date:
                raise ValidationError(
                    'No esta definida la fecha de vencimiento de la secuencia para este tipo de comprobante.')

            classdoc = E43
            IdDoc = classdoc.IdDoc(TipoeCF=l10n_do_ncf_type,
                                   eNCF=self.name,
                                   FechaVencimientoSecuencia=l10n_do_ncf_expiration_date,
                                   )

            emisor = self.gen_emisor(classdoc)
            encabezado = classdoc.Encabezado(Version=version,
                                             IdDoc=IdDoc,
                                             Emisor=emisor,
                                             )

            is_company_currency = self.is_company_currency()
            if not is_company_currency:
                otra_mondeda = self._gen_otra_mondeda(classdoc)
                encabezado.set_OtraMoneda(otra_mondeda)

            return encabezado
        elif l10n_do_ncf_type == '44':
            """Regímenes Especiales Electrónico"""
            if not self.name:
                raise ValidationError('No esta definida la secuencia para este tipo de documento.')

            if not invoice_id.l10n_do_ncf_expiration_date:
                raise ValidationError(
                    'No esta definida la fecha de vencimiento de la secuencia para este tipo de comprobante.')

            classdoc = E44
            IdDoc = classdoc.IdDoc(TipoeCF=l10n_do_ncf_type,
                                   eNCF=self.name,
                                   FechaVencimientoSecuencia=invoice_id.l10n_do_ncf_expiration_date,
                                   TipoIngresos=invoice_id.l10n_do_income_type,
                                   TipoPago=self.get_payment_type(),
                                   )

            if IdDoc.get_TipoPago() == 2:  # Pago a credito
                IdDoc.set_FechaLimitePago(invoice_id.invoice_date_due)
            if invoice_id.invoice_payment_term_id:
                delta = invoice_id.invoice_date_due - invoice_id.invoice_date
                IdDoc.set_TerminoPago(self.limit("%s días" % delta.days, 15))

            emisor = self.gen_emisor(classdoc)
            comprador = self.gen_comprador(classdoc)
            encabezado = classdoc.Encabezado(Version=version,
                                             IdDoc=IdDoc,
                                             Emisor=emisor,
                                             Comprador=comprador,
                                             )

            is_company_currency = self.is_company_currency()
            if not is_company_currency:
                otra_mondeda = self._gen_otra_mondeda(classdoc)
                encabezado.set_OtraMoneda(otra_mondeda)

            return encabezado
        elif l10n_do_ncf_type == '45':
            """Gubernamental Electrónico"""
            if not self.name:
                raise ValidationError('No esta definida la secuencia para este tipo de documento.')

            if not invoice_id.l10n_do_ncf_expiration_date:
                raise ValidationError(
                    'No esta definida la fecha de vencimiento de la secuencia para este tipo de comprobante.')

            classdoc = E45
            IdDoc = classdoc.IdDoc(TipoeCF=l10n_do_ncf_type,
                                   eNCF=self.name,
                                   FechaVencimientoSecuencia=invoice_id.l10n_do_ncf_expiration_date,
                                   TipoIngresos=invoice_id.l10n_do_income_type,
                                   TipoPago=self.get_payment_type(),
                                   )

            IdDoc.set_IndicadorMontoGravado(indicador_monto_gravado)

            if IdDoc.get_TipoPago() == 2:  # Pago a credito
                IdDoc.set_FechaLimitePago(invoice_id.invoice_date_due)
            if invoice_id.invoice_payment_term_id:
                delta = invoice_id.invoice_date_due - invoice_id.invoice_date
                IdDoc.set_TerminoPago(self.limit("%s días" % delta.days, 15))

            emisor = self.gen_emisor(classdoc)
            comprador = self.gen_comprador(classdoc)
            encabezado = classdoc.Encabezado(Version=version,
                                             IdDoc=IdDoc,
                                             Emisor=emisor,
                                             Comprador=comprador,
                                             )

            is_company_currency = self.is_company_currency()
            if not is_company_currency:
                otra_mondeda = self._gen_otra_mondeda(classdoc)
                encabezado.set_OtraMoneda(otra_mondeda)

            return encabezado
        elif l10n_do_ncf_type == '46':
            """Comprobante de Exportaciones Electrónico"""
            if not self.name:
                raise ValidationError('No esta definida la secuencia para este tipo de documento.')

            if not invoice_id.l10n_do_ncf_expiration_date:
                raise ValidationError(
                    'No esta definida la fecha de vencimiento de la secuencia para este tipo de comprobante.')

            classdoc = E46
            IdDoc = classdoc.IdDoc(TipoeCF=l10n_do_ncf_type,
                                   eNCF=self.name,
                                   FechaVencimientoSecuencia=invoice_id.l10n_do_ncf_expiration_date,
                                   TipoIngresos=invoice_id.l10n_do_income_type,
                                   TipoPago=self.get_payment_type(),
                                   )

            if IdDoc.get_TipoPago() == 2:  # Pago a credito
                IdDoc.set_FechaLimitePago(invoice_id.invoice_date_due)
            if invoice_id.invoice_payment_term_id:
                delta = invoice_id.invoice_date_due - invoice_id.invoice_date
                IdDoc.set_TerminoPago(self.limit("%s días" % delta.days, 15))

            emisor = self.gen_emisor(classdoc)
            comprador = self.gen_comprador(classdoc)
            encabezado = classdoc.Encabezado(Version=version,
                                             IdDoc=IdDoc,
                                             Emisor=emisor,
                                             Comprador=comprador,
                                             )

            is_company_currency = self.is_company_currency()
            if not is_company_currency:
                otra_moneda = self._gen_otra_mondeda(classdoc)
                encabezado.set_OtraMoneda(otra_moneda)

            return encabezado
        elif l10n_do_ncf_type == '47':
            """Comprobante para Pagos al Exterior Electrónico"""
            if not self.name:
                raise ValidationError('No esta definida la secuencia para este tipo de documento.')

            if not invoice_id.l10n_do_ncf_expiration_date:
                raise ValidationError(
                    'No esta definida la fecha de vencimiento de la secuencia para este tipo de comprobante.')

            classdoc = E47
            IdDoc = classdoc.IdDoc(TipoeCF=l10n_do_ncf_type,
                                   eNCF=self.name,
                                   FechaVencimientoSecuencia=invoice_id.l10n_do_ncf_expiration_date,
                                   )

            if IdDoc.get_TipoPago() == 2:  # Pago a credito
                IdDoc.set_FechaLimitePago(invoice_id.invoice_date_due)
            if invoice_id.invoice_payment_term_id:
                delta = invoice_id.invoice_date_due - invoice_id.invoice_date
                IdDoc.set_TerminoPago(self.limit("%s días" % delta.days, 15))

            emisor = self.gen_emisor(classdoc)
            comprador = self.gen_comprador(classdoc)
            encabezado = classdoc.Encabezado(Version=version,
                                             IdDoc=IdDoc,
                                             Emisor=emisor,
                                             Comprador=comprador,
                                             )

            is_company_currency = self.is_company_currency()
            if not is_company_currency:
                otra_mondeda = self._gen_otra_mondeda(classdoc)
                encabezado.set_OtraMoneda(otra_mondeda)

            return encabezado

    def gen_comprador(self, classdoc):
        """Logica y validaciones del comprador de tipo de documento.

            :param object classdoc: Clase del tipo de documento.
            :returns: obj del comprador del tipo de documento electronico.
            """

        if not self.partner_id:
            return None

        def validate_and_dpa():
            if self.partner_id.country_id == self.env.ref("base.do"):
                if self.partner_id.state_id:
                    if not self.partner_id.state_id.ecf_code:
                        raise ValidationError('La Provincia seleccionada no tiene codigo para DGII, favor corregir!')
                if self.partner_id.res_municipality_id:
                    if not self.partner_id.res_municipality_id.ecf_code:
                        raise ValidationError('El municipio seleccionada no tiene codigo para DGII, favor corregir!')

        l10n_do_ncf_type = self.ncf_type
        if l10n_do_ncf_type == "31":
            """Credito Fiscal Electronica"""
            if not self.partner_id.vat:
                raise ValidationError(_('The partner has not defined an NIF'))

            validate_and_dpa()
            comprador = classdoc.Comprador(RNCComprador=self.partner_id.vat,
                                           RazonSocialComprador=self.limit(self.partner_id.name, 150),
                                           )

            if self.partner_id.email:
                email = self.partner_id.email.lower()
                if re.match("[^@]+@[^@]+\.[^@]+", email):
                    comprador.set_CorreoComprador(self.limit(self.partner_id.email, 80))
            if self.partner_id.street:
                comprador.set_DireccionComprador(self.limit(self.partner_id.street, 100))
            if self.partner_id.res_municipality_id:
                comprador.set_MunicipioComprador(self.partner_id.res_municipality_id.ecf_code)
            if self.partner_id.state_id:
                comprador.set_ProvinciaComprador(self.partner_id.state_id.ecf_code)

            return comprador
        elif l10n_do_ncf_type == '32':
            """Consumo Electronica"""
            partner_vat = self.partner_id.vat or ""
            amount_total_signed = self.xml_amount_untaxed_signed
            if amount_total_signed >= 250000:
                if not partner_vat:
                    raise ValidationError(_('For amount >= 2500 must be specific a RNC'))
                if not self.partner_id.name:
                    raise ValidationError(_('For amount >= 2500 must be specific a Razon Social o Name'))

            validate_and_dpa()
            comprador = classdoc.Comprador(RazonSocialComprador=self.limit(self.partner_id.name, 80))

            if self.is_l10n_do_partner() and self.partner_id.vat:
                comprador.set_RNCComprador(partner_vat)
            elif not self.is_l10n_do_partner() and self.xml_amount_untaxed_signed >= 250000:
                comprador.set_IdentificadorExtranjero(partner_vat)

            if self.partner_id.phone:
                comprador.set_ContactoComprador(self.limit(self.partner_id.phone, 80))
            if self.partner_id.email:
                email = self.partner_id.email.lower()
                if re.match("[^@]+@[^@]+\.[^@]+", email):
                    comprador.set_CorreoComprador(self.limit(self.partner_id.email, 80))
            if self.partner_id.street:
                comprador.set_DireccionComprador(self.limit(self.partner_id.street, 100))
            if self.partner_id.res_municipality_id:
                comprador.set_MunicipioComprador(self.partner_id.res_municipality_id.ecf_code)
            if self.partner_id.state_id:
                comprador.set_ProvinciaComprador(self.partner_id.state_id.ecf_code)

            return comprador
        elif l10n_do_ncf_type == '33':
            """Nota de Débito Electrónica"""
            partner_vat = self.partner_id.vat or ""
            amount_total_signed = self.invoice_id.amount_total_signed
            if float_compare(amount_total_signed, float(250000.00), 2) == 1:
                if not partner_vat:
                    raise ValidationError(_('For amount >= 2500 must be specific a RNC'))
                if not self.partner_id.name:
                    raise ValidationError(_('For amount >= 2500 must be specific a Razon Social o Name'))

            comprador = classdoc.Comprador(RazonSocialComprador=self.limit(self.partner_id.name, 80))

            if self.is_l10n_do_partner():
                comprador.set_RNCComprador(partner_vat)
            else:
                comprador.set_RNCComprador("")
                comprador.set_IdentificadorExtranjero(partner_vat)

            if self.partner_id.phone:
                comprador.set_ContactoComprador(self.limit(self.partner_id.phone, 80))
            if self.partner_id.email:
                email = self.partner_id.email.lower()
                if re.match("[^@]+@[^@]+\.[^@]+", email):
                    comprador.set_CorreoComprador(self.limit(self.partner_id.email, 80))
            if self.partner_id.street:
                comprador.set_DireccionComprador(self.limit(self.partner_id.street, 100))
            if self.partner_id.res_municipality_id:
                comprador.set_MunicipioComprador(self.partner_id.res_municipality_id.ecf_code)
            if self.partner_id.state_id:
                comprador.set_ProvinciaComprador(self.partner_id.state_id.ecf_code)

            return comprador
        elif l10n_do_ncf_type == '34':
            """Nota de Crédito Electrónica"""
            comprador = classdoc.Comprador()
            comprador.set_RazonSocialComprador(self.limit(self.partner_id.name, 80))

            if self.partner_id.vat:
                comprador.set_RNCComprador(self.partner_id.vat)

            if self.partner_id.email:
                email = self.partner_id.email.lower()
                if re.match("[^@]+@[^@]+\.[^@]+", email):
                    comprador.set_CorreoComprador(self.limit(self.partner_id.email, 80))
            if self.partner_id.street:
                comprador.set_DireccionComprador(self.limit(self.partner_id.street, 100))
            if self.partner_id.res_municipality_id:
                comprador.set_MunicipioComprador(self.partner_id.res_municipality_id.ecf_code)
            if self.partner_id.state_id:
                comprador.set_ProvinciaComprador(self.partner_id.state_id.ecf_code)

            return comprador
        elif l10n_do_ncf_type == '41':
            """Compras Electrónico"""
            if not self.partner_id.vat:
                raise ValidationError(_('The partner has not defined an NIF'))

            comprador = classdoc.Comprador(RNCComprador=self.partner_id.vat,
                                           RazonSocialComprador=self.limit(self.partner_id.name, 150),
                                           )

            if self.partner_id.email:
                email = self.partner_id.email.lower()
                if re.match("[^@]+@[^@]+\.[^@]+", email):
                    comprador.set_CorreoComprador(self.limit(self.partner_id.email, 80))
            if self.partner_id.street:
                comprador.set_DireccionComprador(self.limit(self.partner_id.street, 100))
            if self.partner_id.res_municipality_id:
                comprador.set_MunicipioComprador(self.partner_id.res_municipality_id.ecf_code)
            if self.partner_id.state_id:
                comprador.set_ProvinciaComprador(self.partner_id.state_id.ecf_code)

            return comprador
        elif l10n_do_ncf_type == '44':
            """Regímenes Especiales Electrónico"""
            if not self.partner_id.vat:
                raise ValidationError(_('The partner has not defined an NIF'))

            validate_and_dpa()
            comprador = classdoc.Comprador(RNCComprador=self.partner_id.vat,
                                           RazonSocialComprador=self.limit(self.partner_id.name, 150),
                                           )

            if self.partner_id.email:
                email = self.partner_id.email.lower()
                if re.match("[^@]+@[^@]+\.[^@]+", email):
                    comprador.set_CorreoComprador(self.limit(self.partner_id.email, 80))
            if self.partner_id.street:
                comprador.set_DireccionComprador(self.limit(self.partner_id.street, 100))
            if self.partner_id.res_municipality_id:
                comprador.set_MunicipioComprador(self.partner_id.res_municipality_id.ecf_code)
            if self.partner_id.state_id:
                comprador.set_ProvinciaComprador(self.partner_id.state_id.ecf_code)

            return comprador
        elif l10n_do_ncf_type == '45':
            """Gubernamental Electrónico"""
            if not self.partner_id.vat:
                raise ValidationError(_('The partner has not defined an NIF'))

            validate_and_dpa()
            comprador = classdoc.Comprador(RNCComprador=self.partner_id.vat,
                                           RazonSocialComprador=self.limit(self.partner_id.name, 150),
                                           )

            if self.partner_id.email:
                email = self.partner_id.email.lower()
                if re.match("[^@]+@[^@]+\.[^@]+", email):
                    comprador.set_CorreoComprador(self.limit(self.partner_id.email, 80))
            if self.partner_id.street:
                comprador.set_DireccionComprador(self.limit(self.partner_id.street, 100))
            if self.partner_id.res_municipality_id:
                comprador.set_MunicipioComprador(self.partner_id.res_municipality_id.ecf_code)
            if self.partner_id.state_id:
                comprador.set_ProvinciaComprador(self.partner_id.state_id.ecf_code)

            return comprador
        elif l10n_do_ncf_type == '46':
            """Comprobante de Exportaciones Electrónico"""
            if not self.partner_id.vat:
                raise ValidationError(_('The partner has not defined an NIF'))

            validate_and_dpa()
            comprador = classdoc.Comprador(RNCComprador=self.partner_id.vat,
                                           RazonSocialComprador=self.limit(self.partner_id.name, 150),
                                           )

            if self.partner_id.email:
                email = self.partner_id.email.lower()
                if re.match("[^@]+@[^@]+\.[^@]+", email):
                    comprador.set_CorreoComprador(self.limit(self.partner_id.email, 80))
            if self.partner_id.street:
                comprador.set_DireccionComprador(self.limit(self.partner_id.street, 100))
            if self.partner_id.res_municipality_id:
                comprador.set_MunicipioComprador(self.partner_id.res_municipality_id.ecf_code)
            if self.partner_id.state_id:
                comprador.set_ProvinciaComprador(self.partner_id.state_id.ecf_code)

            return comprador
        elif l10n_do_ncf_type == '47':
            """Comprobante para Pagos al Exterior Electrónico"""
            if not self.partner_id.vat:
                raise ValidationError(_('The partner has not defined an NIF'))

            comprador = classdoc.Comprador(RazonSocialComprador=self.limit(self.partner_id.name, 150))

            if self.partner_id.vat:
                comprador.set_IdentificadorExtranjero(self.partner_id.vat)

            return comprador

    def _gen_taxed_tips(self, cedoc, classdoc, totales):
        """l10n_do_ncf_type not in ("41", "43", "44", "46", "47")"""
        tax_data = self.get_taxed_amount_data()
        total_tax_tips = tax_data["tax_additional"]

        totales.set_MontoTotal(totales.get_MontoTotal() + total_tax_tips)
        totales.set_MontoImpuestoAdicional(total_tax_tips)
        imp_ads = classdoc.ImpuestosAdicionales()

        group_data = self._get_taxed_tips_data(cedoc.get_DetallesItems())

        ia = classdoc.ImpuestoAdicional(TipoImpuesto=group_data["001"]['TipoImpuesto'],
                                        TasaImpuestoAdicional=group_data["001"]['TasaImpuestoAdicional'],
                                        OtrosImpuestosAdicionales=group_data["001"]['OtrosImpuestosAdicionales'],
                                        )
        imp_ads.add_ImpuestoAdicional(ia)

        totales.set_ImpuestosAdicionales(imp_ads)

    def _gen_cedoc(self):
        """ Retorna el elemento raiz de un documento electronico.

            :returns: obj del tipo de documento electronico.
            """

        l10n_do_ncf_type = self.ncf_type
        if l10n_do_ncf_type == '31':
            """Factura de Credito Fiscal Electronica"""
            classdoc = E31
            encabezado = self.gen_encabezado()
            cedoc = classdoc.FacturaCreditoFiscalElectronica(Encabezado=encabezado)

            totales = self.gen_totales(classdoc, cedoc)
            encabezado.set_Totales(totales)

            if self.invoice_id:
                cedoc = self._gen_invoice(cedoc, classdoc)

            any_taxed_tip = any(item.get_TablaImpuestoAdicional() for item in cedoc.get_DetallesItems().get_Item())
            if any_taxed_tip:
                self._gen_taxed_tips(cedoc, classdoc, totales)

            self.xml_amount_tax = totales.get_TotalITBIS()
            self.xml_amount_total = totales.get_MontoTotal()

            return cedoc
        elif l10n_do_ncf_type == '32':
            """Factura de Consumo Electronica"""
            classdoc = E32
            encabezado = self.gen_encabezado()
            cedoc = classdoc.FacturaConsumoElectronica(Encabezado=encabezado)

            totales = self.gen_totales(classdoc, cedoc)
            encabezado.set_Totales(totales)

            if self.invoice_id:
                cedoc = self._gen_invoice(cedoc, classdoc)

            any_taxed_tip = any(item.get_TablaImpuestoAdicional() for item in cedoc.get_DetallesItems().get_Item())
            if any_taxed_tip:
                self._gen_taxed_tips(cedoc, classdoc, totales)

            self.xml_amount_tax = totales.get_TotalITBIS()
            self.xml_amount_total = totales.get_MontoTotal()

            return cedoc
        elif l10n_do_ncf_type == '33':
            """Nota de Débito Electrónica"""
            classdoc = E33
            encabezado = self.gen_encabezado()
            cedoc = classdoc.NotaDebitoElectronica(Encabezado=encabezado)

            totales = self.gen_totales(classdoc, cedoc)
            encabezado.set_Totales(totales)

            if self.invoice_id:
                cedoc = self._gen_invoice(cedoc, classdoc)

            origin_id = self.invoice_id.debit_origin_id
            if not origin_id:
                raise ValidationError(_("Could not found origin document " + origin_id.l10n_latam_document_number))

            self.xml_amount_tax = totales.get_TotalITBIS()
            self.xml_amount_total = totales.get_MontoTotal()

            self._gen_informacion_referencia(cedoc, classdoc, origin_id)
            return cedoc
        elif l10n_do_ncf_type == '34':
            """Nota de Crédito Electrónica"""
            if not self.invoice_id.l10n_do_origin_ncf:
                raise ValidationError(_("Could not exist origin document"))

            l10n_do_origin_ncf = self.invoice_id.l10n_do_origin_ncf
            origin_id = self.env["account.move"].search([("l10n_latam_document_number", "=", l10n_do_origin_ncf)],
                                                        limit=1)

            if not origin_id:
                raise ValidationError(_("Could not found origin document: " + l10n_do_origin_ncf))

            classdoc = E34
            encabezado = self.gen_encabezado()
            cedoc = classdoc.NotaCreditoElectronica(Encabezado=encabezado)

            totales = self.gen_totales(classdoc, cedoc)
            encabezado.set_Totales(totales)

            if self.invoice_id:
                cedoc = self._gen_invoice(cedoc, classdoc)

            self.xml_amount_tax = totales.get_TotalITBIS()
            self.xml_amount_total = totales.get_MontoTotal()

            self._gen_informacion_referencia(cedoc, classdoc, origin_id)
            return cedoc
        elif l10n_do_ncf_type == '41':
            """Compras Electrónico"""
            classdoc = E41
            encabezado = self.gen_encabezado()
            cedoc = E41.ComprasElectronica(Encabezado=encabezado)

            if self.invoice_id:
                cedoc = self._gen_invoice(cedoc, classdoc)

            return cedoc
        elif l10n_do_ncf_type == '43':
            """Gastos Menores Electrónico"""
            classdoc = E43
            encabezado = self.gen_encabezado()
            cedoc = E43.GastosMenoresElectronico(Encabezado=encabezado)

            if self.invoice_id:
                cedoc = self._gen_invoice(cedoc, classdoc)

            return cedoc
        elif l10n_do_ncf_type == '44':
            """Regímenes Especiales Electrónico"""
            classdoc = E44
            encabezado = self.gen_encabezado()
            cedoc = E44.RegimenesEspecialesElectronico(Encabezado=encabezado)

            if self.invoice_id:
                cedoc = self._gen_invoice(cedoc, classdoc)

            return cedoc
        elif l10n_do_ncf_type == '45':
            """Gubernamental Electrónico"""
            classdoc = E45
            encabezado = self.gen_encabezado()
            cedoc = E45.GubernamentalElectronico(Encabezado=encabezado)

            if self.invoice_id:
                cedoc = self._gen_invoice(cedoc, classdoc)

            return cedoc
        elif l10n_do_ncf_type == '46':
            """Comprobante de Exportaciones Electrónico"""
            classdoc = E46
            encabezado = self.gen_encabezado()
            cedoc = E46.ComprobanteExportacionesElectronico(Encabezado=encabezado)

            if self.invoice_id:
                cedoc = self._gen_invoice(cedoc, classdoc)

            return cedoc
        elif l10n_do_ncf_type == '47':
            """Comprobante para Pagos al Exterior Electrónico"""
            classdoc = E47
            encabezado = self.gen_encabezado()
            cedoc = E47.ComprobantePagosExteriorElectronico(Encabezado=encabezado)

            if self.invoice_id:
                cedoc = self._gen_invoice(cedoc, classdoc)

            return cedoc

    def _send_to_netvux(self):
        ceconfig = self.company_id.ecf_config
        netvux_api = NETVUXApi(ceconfig)
        return self.receipt_ecf(netvux_api)

    def receipt_ecf(self, netvux_api):
        kernel = netvux_api.authentication()
        if not isinstance(kernel, dict):
            raise ValidationError(kernel)

        try:
            response, vals, token = netvux_api.receipt_xml_ecf(base64.b64decode(self.xml_file), self.xml_file_name,
                                                               kernel)
            if response.status_code == 200:
                data_dict = xmltodict.parse(response.text)
                ceconfig = self.company_id.ecf_config
                ecf_name = self.company_id.vat + "" + data_dict.get('MensajeEnviado').get("encf")

                document_vals = self.default_get(['netvux_warning_message'])
                document_vals['name'] = data_dict.get('MensajeEnviado').get("encf")
                document_vals['l10n_do_electronic_stamp'] = data_dict.get('MensajeEnviado').get("electronic_stamp")
                document_vals['l10n_do_ecf_sign_date'] = data_dict.get('MensajeEnviado').get("sign_date")
                document_vals['l10n_do_ecf_send_state'] = data_dict.get('MensajeEnviado').get("estado")
                document_vals['message_detail_dgii'] = data_dict.get('MensajeEnviado').get("message_detail_dgii")
                document_vals['l10n_do_ecf_security_code'] = data_dict.get('MensajeEnviado').get("security_code")
                document_vals['xml_file_name'] = "{}.xml".format(ecf_name)

                response1, vals1 = netvux_api.send_ecf_request_xml(token, data_dict.get('MensajeEnviado').get("encf"))
                if response1.status_code == 200:
                    xml_encoded = bytes(vals1.encode())
                    document_vals["xml_netvux_file"] = base64.b64encode(xml_encoded)

                self.write(document_vals)
                self.QR_code = self._generate_barcode(ceconfig.environment)
                if self.l10n_do_ecf_send_state == 'delivered_refused':
                    self.invoice_id.with_context(
                        cancelled_by_dgii=True
                    ).action_cancel_()

                return True
            elif response.status_code == 400:
                response_text = response.text
                data_dict = xmltodict.parse(response_text)
                self.netvux_warning_message = self._prepare_msg_error_vals(data_dict)
                return False
            elif response.status_code == 404:
                response_text = response.text
                data_dict = xmltodict.parse(response_text)
                self.netvux_warning_message = self._prepare_msg_error_vals(data_dict)
                return False
            elif response.status_code == 500:
                response_text = response.text
                data_dict = xmltodict.parse(response_text)
                self.netvux_warning_message = self._prepare_msg_error_vals(data_dict)
                return False

        except requests.exceptions.MissingSchema:
            self.message_detail_dgii = "Wrong external service URL"
            return False

        except requests.exceptions.ConnectionError:
            # Odoo could not send the request
            self.l10n_do_ecf_send_state = "not_sent"

    def _action_request_state_to_netvux(self):
        """

        """
        ceconfig = self.company_id.ecf_config
        netvux_api = NETVUXApi(ceconfig)

        kernel = netvux_api.authentication()
        if not isinstance(kernel, dict):
            raise ValidationError(kernel)

        response = netvux_api.send_ecf_status_request(self.company_id.vat, self.name, kernel)
        if response.status_code == 200:
            vals = json.loads(response.text)
            self.write({"l10n_do_ecf_send_state": vals.get('l10n_do_ecf_send_state'),
                        "message_detail_dgii": vals.get('message_detail_dgii'),
                        })
            return True

    def _generate_barcode(self, environment):
        security_code = self.l10n_do_ecf_security_code
        date_sign_formatted = self.l10n_do_ecf_sign_date

        if self.is_rfce:
            api_url = 'https://fc.dgii.gov.do/{Environment}/consultatimbrefc?RncEmisor={RncEmisor}&ENCF={ENCF}' \
                      '&MontoTotal={MontoTotal}&CodigoSeguridad={CodigoSeguridad}'. \
                format(
                Environment=environment,
                RncEmisor=self.company_id.vat,
                ENCF=self.name,
                MontoTotal=("%f" % abs(self.xml_amount_total)).rstrip("0").rstrip("."),
                CodigoSeguridad=security_code,
            )
        else:
            api_url = 'https://ecf.dgii.gov.do/{Environment}/ConsultaTimbre?RncEmisor={RncEmisor}'.format(
                Environment=environment,
                RncEmisor=self.company_id.vat)
            if self.ncf_type != '43':
                api_url += '&RncComprador={RncComprador}'.format(RncComprador=self.partner_id.vat)

            api_url += '&ENCF={ENCF}&FechaEmision={FechaEmision}' \
                       '&MontoTotal={MontoTotal}&FechaFirma={FechaFirma}&CodigoSeguridad={CodigoSeguridad}'. \
                format(
                ENCF=self.name,
                FechaEmision=self.invoice_id.invoice_date.strftime("%d-%m-%Y"),
                MontoTotal=("%f" % abs(self.xml_amount_total)).rstrip("0").rstrip(".") if self.ncf_type != '43' else (
                        "%f" % abs(self.xml_amount_untaxed_signed)).rstrip("0").rstrip("."),
                FechaFirma=date_sign_formatted,
                CodigoSeguridad=security_code,
            )

        self.write({
            "l10n_do_electronic_stamp": api_url,
        })

        # Genera código QR
        qr_code = pyqrcode.create(api_url)
        return qr_code.png_as_base64_str(scale=2)

    def get_l10n_do_ncf_type(self):
        """
        Indicates if the document Code Type:

        31: Factura de Crédito Fiscal Electrónica
        32: Factura de Consumo Electrónica
        33: Nota de Débito Electrónica
        34: Nota de Crédito Electrónica
        41: Compras Electrónico
        43: Gastos Menores Electrónico
        44: Regímenes Especiales Electrónica
        45: Gubernamental Electrónico
        46: Comprobante para Exportaciones Electrónico
        47: Comprobante para Pagos al Exterior Electrónico
        """

        return self.l10n_latam_document_type_id.doc_code_prefix[1:]

    def get_taxed_amount_data(self):
        """ITBIS taxed amount
        According to the DGII, there are three types of amounts taxed by ITBIS:

        18% -- Most common
        16% -- Used on 'healthy products' like Yogurt, coffee and so on.
        0% -- Should be used on exported products

        See Law No. 253-12, art. 343 of dominican Tributary Code for further info
        """
        itbis_group = self.env["account.tax.group"].search(
            [("name", '=', 'ITBIS'),
             ('company_id', 'parent_of', self.company_id.ids),
             ('country_id', '=', self.env.ref("base.do").id)], limit=1)
        isr_group = self.env["account.tax.group"].search(
            [("name", '=', 'ISR'),
             ('company_id', 'parent_of', self.company_id.ids),
             ('country_id', '=', self.env.ref("base.do").id)], limit=1)
        tips_group = self.env["account.tax.group"].search(
            [("name", '=', 'Propina'),
             ('company_id', 'parent_of', self.company_id.ids),
             ('country_id', '=', self.env.ref("base.do").id)], limit=1)

        itbis_data = {
            "total_taxed_amount": 0,
            "18_taxed_base": 0,
            "18_taxed_amount": 0,
            "16_taxed_base": 0,
            "16_taxed_amount": 0,
            "0_taxed_base": 0,
            "0_taxed_amount": 0,
            "exempt_amount": 0,
            "itbis_withholding_amount": 0,
            "isr_withholding_amount": 0,
            "tax_additional": 0,
        }

        tax_data = [
            line.tax_ids.compute_all(
                price_unit=line.price_subtotal,
                currency=line.currency_id,
                product=line.product_id,
                partner=line.move_id.partner_id,
                handle_price_include=False,
            )
            for line in self.invoice_id.invoice_line_ids
        ]

        itbis_data["total_taxed_amount"] = sum(
            line["total_excluded"] for line in tax_data
        )
        l10n_do_ncf_type = self.ncf_type

        for line_taxes in tax_data:
            for tax in line_taxes["taxes"]:
                if not tax["amount"] and l10n_do_ncf_type != "46":
                    itbis_data["exempt_amount"] += tax["base"]

                tax_id = self.env["account.tax"].browse(tax["id"])
                if tax_id.amount == 18 and l10n_do_ncf_type != "46":
                    itbis_data["18_taxed_base"] += tax["base"]
                    itbis_data["18_taxed_amount"] += tax["amount"]
                elif tax_id.amount == 16 and l10n_do_ncf_type != "46":
                    itbis_data["16_taxed_base"] += tax["base"]
                    itbis_data["16_taxed_amount"] += tax["amount"]
                elif tax_id.amount == 0 and l10n_do_ncf_type == "46":
                    itbis_data["0_taxed_base"] += tax["base"]
                    itbis_data["0_taxed_amount"] += tax["amount"]
                elif tax_id.amount < 0 and tax_id.tax_group_id == itbis_group:
                    itbis_data["itbis_withholding_amount"] += tax["amount"]
                elif tax_id.amount < 0 and tax_id.tax_group_id == isr_group:
                    itbis_data["isr_withholding_amount"] += tax["amount"]
                elif tax_id.amount == 10 and tax_id.tax_group_id == tips_group:
                    itbis_data["tax_additional"] += tax["amount"]

        return itbis_data

    def get_payment_type(self):
        """
        Indicates the type of customer payment. Free delivery invoices (code 3)
        are not valid for Crédito Fiscal.

        1 - Al Contado
        2 - Crédito
        3 - Gratuito
        """
        # TODO: evaluate payment type 3 <Gratuito> Check DGII docs
        if not self.invoice_id.invoice_payment_term_id and self.invoice_id.invoice_date_due:
            if (
                    self.invoice_id.invoice_date_due and self.invoice_id.invoice_date
            ) and self.invoice_id.invoice_date_due > self.invoice_id.invoice_date:
                return 2
            else:
                return 1
        elif not self.invoice_id.invoice_payment_term_id:
            return 1
        elif not self.invoice_id.invoice_payment_term_id == self.env.ref(
                "account.account_payment_term_immediate"
        ):
            return 2
        else:
            return 1

    def is_l10n_do_partner(self):
        return self.partner_id.country_id and self.partner_id.country_id == self.env.ref("base.do")

    def is_company_currency(self):
        return self.currency_id == self.company_id.currency_id

    @staticmethod
    def limit(text, limit):
        return (text[:limit - 3] + '...') if len(text) > limit else text

    def _prepare_msg_error_vals(self, data_dict):
        respuesta = data_dict.get('MensajeError')
        code = respuesta.get("valor", "")
        body_message = respuesta.get("descripcion", "")
        message = ("No se pudo firmar el XML: \n " +
                   f"<ul><li>Code: {code}</li><li>Message: {body_message}</li></ul>")
        return message

    # ===== CRONs =====

    @api.model
    def cron_ecf_invoices_pending_send_netvux(self):
        """Busca los ecf q fueron firmados y pendiente y actualiza su estado."""

        documents = self.search([('invoice_id', '!=', False),
                                 ('l10n_do_ecf_send_state', 'in', ['signed_pending', 'delivered_pending'])])
        for doc in documents:
            if doc._action_request_state_to_netvux():
                _logger.info("##### CONSULTANDO ESTADO ECF A NETVUX: " + doc.name)

        _logger.info("##### FIN")

    @api.model
    def cron_ecf_invoices_to_dent_netvux(self):
        """."""

        documents = self.search([('invoice_id', '!=', False),
                                 ('xml_file', '!=', False),
                                 ('l10n_do_ecf_send_state', 'in', ['to_send'])])
        for doc in documents:
            if doc.action_send_to_netvux():
                _logger.info("##### CONSULTANDO ESTADO ECF A NETVUX: " + doc.name)

        _logger.info("##### FIN")
