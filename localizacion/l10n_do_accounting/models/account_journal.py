# MIGRADO: Arturo Diaz Lora - 2026-03-27 - Agregar import logging
import logging

from odoo import fields, models, api, _
from odoo.exceptions import RedirectWarning
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _get_l10n_do_payment_form(self):
        """ Return the list of payment forms allowed by DGII. """
        return [
            ("cash", _("Cash")),
            ("bank", _("Check / Transfer")),
            ("card", _("Credit Card")),
            ("credit", _("Credit")),
            ("swap", _("Swap")),
            ("bond", _("Bonds or Gift Certificate")),
            ("others", _("Other Sale Type")),
        ]

    l10n_do_payment_form = fields.Selection(
        selection="_get_l10n_do_payment_form",
        string="Payment Form",
    )

    l10n_latam_use_documents = fields.Boolean(
        'Use Documents?', help="If active: will be using for legal invoicing (invoices, debit/credit notes)."
                               " If not set means that will be used to register accounting entries not related to invoicing legal documents."
                               " For Example: Receipts, Tax Payments, Register journal entries")
    l10n_latam_company_use_documents = fields.Boolean(compute='_compute_l10n_latam_company_use_documents')

    @api.depends('company_id')
    def _compute_l10n_latam_company_use_documents(self):
        for rec in self:
            rec.l10n_latam_company_use_documents = rec.company_id._localization_use_documents()

    @api.onchange('company_id', 'type')
    def _onchange_company(self):
        self.l10n_latam_use_documents = self.type in ['sale', 'purchase'] and \
                                        self.l10n_latam_company_use_documents

    # @api.constrains('l10n_latam_use_documents')
    # def check_use_document(self):
    #     for rec in self:
    #         if rec.env['account.move'].search([('journal_id', '=', rec.id), ('posted_before', '=', True)], limit=1):
    #             raise ValidationError(_(
    #                 'You can not modify the field "Use Documents?" if there are validated invoices in this journal!'))

    @api.onchange('type', 'l10n_latam_use_documents')
    def _onchange_type(self):
        parent_method = getattr(super(AccountJournal, self), "_onchange_type", None)
        if parent_method:
            res = parent_method()
        else:
            res = None  # Si no existe, evitar llamarlo
        if self.l10n_latam_use_documents:
            self.refund_sequence = False
        return res

    def _get_all_ncf_types(self, types_list):
        """
        Include ECF type prefixes if company is ECF issuer
        :param types_list: NCF list used to create fiscal sequences
        :return: types_list
        """
        # Autor: Arturo Diaz Lora
        # Fecha: 2025-11-22 22:35
        # Razón: Evitar duplicación de tipos electrónicos y doble prefijo "e-e-"
        if self.company_id.l10n_do_ecf_issuer:
            # Solo agregar prefijo "e-" a tipos que no lo tienen ya
            # Evita duplicados como "e-credit_note" dos veces y tipos inválidos como "e-e-credit_note"
            types_list.extend(
                ["e-%s" % d for d in types_list if d not in ("unique", "import") and not d.startswith("e-")]
            )
        return types_list

    @api.model
    def _get_l10n_do_ncf_types_data(self):
        return {
            "issued": {
                "taxpayer": ["fiscal"],
                "non_payer": ["consumer", "unique"],
                "nonprofit": ["fiscal"],
                "special": ["special"],
                "governmental": ["governmental"],
                "foreigner": ["export", "consumer"],
            },
            "received": {
                "taxpayer": [
                    "fiscal",
                    "informal",
                    "special",
                    "governmental",
                    "e-fiscal",
                    "e-informal",
                     ],
                "non_payer": ["informal", "e-informal"],
                "nonprofit": ["special", "governmental"],
                "special": ["fiscal", "special", "governmental"],
                "governmental": ["fiscal", "special", "governmental"],
                "foreigner": ["import", "exterior"],
            },
        }

    def _get_journal_ncf_types(self, counterpart_partner=False, invoice=False):
        """
        Regarding the DGII type of company and the type of journal
        (sale/purchase), get the allowed NCF types. Optionally, receive
        the counterpart partner (customer/supplier) and get the allowed
        NCF types to work with him. This method is used to populate
        document types on journals and also to filter document types on
        specific invoices to/from customer/supplier
        """
        self.ensure_one()

        ncf_types_data = self._get_l10n_do_ncf_types_data()
        if not self.company_id.vat:
            action = self.env.ref("base.action_res_company_form")
            msg = _("Cannot create chart of account until you configure your VAT.")
            raise RedirectWarning(msg, action.id, _("Go to Companies"))

        # Get all the ncf_types values from the nested dictionary, remove 
        # duplicates and convert it into a list
        ncf_types = list(
            set(
                [
                    value
                    for dic in ncf_types_data[
                        "issued" if self.type == "sale" else "received"
                    ].values()
                    for value in dic
                ]
            )
        )
        if not counterpart_partner:
            ncf_notes = list(["fiscal", "debit_note", "credit_note", "e-debit_note", "e-credit_note"])
            # IMPORTANT: fiscal y e-fiscal NO deben excluirse de compras - son válidos cuando recibes facturas de proveedores
            # Solo excluir tipos que son exclusivamente para ventas
            ncf_external = list(["special", "governmental", "e-special", "e-governmental"])
            res = (
                ncf_types + ncf_notes
                if self.type == "sale"
                else [ncf for ncf in ncf_types if ncf not in ncf_external]
            )
            return self._get_all_ncf_types(res)
        else:
            # Handle case where partner doesn't have a tax payer type set
            partner_tax_type = counterpart_partner.l10n_do_dgii_tax_payer_type
            if not partner_tax_type:
                # Default to 'taxpayer' if no type is set
                partner_tax_type = 'taxpayer'
                _logger.warning(f"Partner {counterpart_partner.name} has no tax payer type set, defaulting to 'taxpayer'")
            
            counterpart_ncf_types = ncf_types_data[
                "issued" if self.type == "sale" else "received"
            ].get(partner_tax_type, [])
            ncf_types = list(set(ncf_types) & set(counterpart_ncf_types))
        
        # Handle specific move types for credit and debit notes
        if invoice and invoice.move_type in ["out_refund", "in_refund"]:
            ncf_types = ["credit_note", "e-credit_note"]
        elif invoice and invoice.debit_origin_id:
            ncf_types = ["debit_note", "e-debit_note"]
        elif invoice and invoice.env.context.get('internal_type') == 'debit_note':
            ncf_types = ["debit_note", "e-debit_note"]

        return self._get_all_ncf_types(ncf_types)

    def _get_journal_codes(self):
        self.ensure_one()
        if self.type != "sale":
            return []
        return ["E"] if self.company_id.l10n_do_ecf_issuer else ["B"]
