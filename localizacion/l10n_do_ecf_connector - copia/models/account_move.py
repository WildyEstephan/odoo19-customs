import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError, RedirectWarning
from ..netvux_api import NETVUXApi

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    ecf_id = fields.Many2one('ecf.document', string='ECF Document', copy=False, readonly=True)
    is_rfce = fields.Boolean(related='ecf_id.is_rfce', string="Is RFCE")
    l10n_do_ecf_send_state = fields.Selection(related='ecf_id.l10n_do_ecf_send_state', string='DGII State',
                                              tracking=True, store=True, copy=False, readonly=True)
    l10n_do_ecf_security_code = fields.Char(string="e-CF Security Code", related="ecf_id.l10n_do_ecf_security_code")
    # l10n_do_ecf_sign_date ya está definido en l10n_do_edi como Datetime
    l10n_do_electronic_stamp = fields.Text(string="Electronic Stamp", related="ecf_id.l10n_do_electronic_stamp")
    QR_code = fields.Binary(string="Code QR", related="ecf_id.QR_code")

    xml_file = fields.Binary("XML File", related="ecf_id.xml_file")

    netvux_warning_message = fields.Html(related="ecf_id.netvux_warning_message")

    def _create_doc(self, recreate=False):
        if not self.ecf_id or recreate:
            ecf_vals = {}
            ecf_vals.update({
                             'name': self.l10n_latam_document_number,
                             'l10n_latam_document_type_id': self.l10n_latam_document_type_id.id,
                             'invoice_id': self.id,
                             'partner_id': self.partner_id.id,
                             'currency_id': self.currency_id.id,
                             'company_id': self.company_id.id,
                             })

            ce_id = self.env['ecf.document'].create(ecf_vals)
            self.ecf_id.unlink()
            self.write({'ecf_id': ce_id.id})

    def _post(self, soft=True):
        res = super(AccountMove, self)._post(soft)
        # Primero se llama al padre para q genere el consecutivos, establecer la fecha de vencimiento, etc.

        for inv in self.filtered(lambda x: x.move_type not in ('entry', )):
            if not inv.company_id.ecf_config:
                action = self.env.ref("base.action_res_company_form")
                msg = _("Must be selected an Environment in a Company.")
                raise RedirectWarning(msg, action.id, _("Go to Setting"))

            ceconfig = inv.company_id.ecf_config
            netvux_api = NETVUXApi(ceconfig)

            kernel = netvux_api.authentication()
            if not isinstance(kernel, dict):
                raise ValidationError(kernel)

            ncf_type = inv.get_l10n_do_ncf_type()
            # Las facturas de proveedores (vendor bills) NO se envían a DGII si son tipos de VENTA
            # porque son facturas RECIBIDAS, no emitidas por la empresa
            # Solo se envían facturas de compra autogeneradas: E41, E43, E47
            if inv.move_type in ['in_invoice', 'in_refund']:
                sales_ncf_types = ["01", "02", "14", "15", "16", "31", "32", "33", "34", "44", "45", "46"]
                if ncf_type in sales_ncf_types:
                    _logger.info(
                        f"Factura de proveedor {inv.name} con tipo {ncf_type} NO se envía a DGII "
                        f"(es una factura recibida, no emitida)"
                    )
                    continue

            if inv.partner_id and inv.l10n_latam_document_type_id:
                inv._create_doc(recreate=True)
                valid = inv.ecf_id.action_gen_xml()
                if not inv.l10n_do_company_in_contingency and valid:
                    inv.ecf_id.action_send_to_netvux()

        return res

    # ===== BUTTONS =====

    def action_send_to_netvux(self):
        if self.ecf_id.xml_file:
            return self.ecf_id.action_send_to_netvux()
        else:
            raise UserError(_('Must be a xml file.'))

    def action_recreate_xml(self):
        self.ecf_id.action_recreate_xml()

    def action_request_state_to_netvux(self):
        if self.ecf_id.xml_file:
            return self.ecf_id.action_request_state_to_netvux()
        else:
            raise UserError(_('Must be a xml file.'))

    def button_draft(self):
        if self.l10n_do_ecf_send_state in ['delivered_accepted', 'conditionally_accepted', 'delivered_pending', 'delivered_refused']:
            if not self.env.context.get("cancelled_by_dgii", False):
                raise UserError("No puede establecer a borrador una factura enviada a la DGII.")

        res = super(AccountMove, self).button_draft()
        return res

    def button_cancel(self):
        if self.l10n_do_ecf_send_state in ['delivered_accepted', 'conditionally_accepted', 'delivered_pending', 'delivered_refused']:
            if not self.env.context.get("cancelled_by_dgii", False):
                raise UserError("No puede establecer a cancelada una factura enviada a la DGII.")

        res = super(AccountMove, self).button_cancel()
        # TODO: Roper la conciliacion de los pagos.
        return res

    # === BUSINESS METHODS ===#

    def action_cancel_(self):
        # TODO: Hacer q rompa la conciliacion de los pagos (POS)
        if 'pos_order_ids' in self._fields and self.pos_order_ids:
            return

        self.write({'state': 'cancel', 'l10n_do_cancellation_type': "04"})

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

        self.ensure_one()
        if not self.l10n_latam_document_type_id:
            return False

        return self.l10n_latam_document_type_id.doc_code_prefix[1:]
