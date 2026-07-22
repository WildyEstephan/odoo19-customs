
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError, AccessError
import logging

from odoo.addons.l10n_latam_invoice_document.models.account_move import AccountMove as LatamAccountMove

_logger = logging.getLogger(__name__)

ncf_dict = {
    "B01": "fiscal",
    "B02": "consumo",
    "B15": "gov",
    "B14": "especial",
    "B12": "unico",
    "B16": "export",
    "B03": "debit",
    "B04": "credit",
    "B13": "minor",
    "B11": "informal",
    "B17": "exterior",
    "E31": "e-fiscal",
    "E32": "e-consumer",
    "E33": "e-debit_note",
    "E34": "e-credit_note",
    "E41": "e-informal",
    "E43": "e-minor",
    "E44": "e-special",
    "E45": "e-governmental",
    "E46": "e-export",
    "E47": "e-exterior",
}


class AccountMove(models.Model):
    _inherit = "account.move"

    @property
    def _sequence_fixed_regex(self):
        if self.l10n_latam_country_code == "DO" and self.l10n_latam_use_documents:
            return r'^(?P<prefix1>.*?)(?P<seq>\d{0,9})(?P<suffix>\D*?)$'
        return super(AccountMove, self)._sequence_fixed_regex

    def _get_l10n_do_cancellation_type(self):
        """ Return the list of cancellation types required by DGII. """
        return [
            ("01", _("01 - Pre-printed Invoice Impairment")),
            ("02", _("02 - Printing Errors (Pre-printed Invoice)")),
            ("03", _("03 - Defective Printing")),
            ("04", _("04 - Correction of Product Information")),
            ("05", _("05 - Product Change")),
            ("06", _("06 - Product Return")),
            ("07", _("07 - Product Omission")),
            ("08", _("08 - NCF Sequence Errors")),
            ("09", _("09 - For Cessation of Operations")),
            ("10", _("10 - Lossing or Hurting Of Counterfoil")),
        ]

    def _get_l10n_do_ecf_modification_code(self):
        """ Return the list of e-CF modification codes required by DGII.

        Autor: Arturo Diaz Lora
        Fecha: 2025-11-23 08:30
        Razón: Cambiado formato de valores de "1","2","3","4" a "01","02","03","04"
               para coincidir con el formato que envía el POS y el formato DGII.
               Antes: POS enviaba "01" pero Selection tenía "1", causando que el valor
               no se guardara y se enviara "0" a DGII (rechazado).
        """
        return [
            ("1", _("01 - Total Cancellation")),
            ("2", _("02 - Text Correction")),
            ("3", _("03 - Amount correction")),
            ("4", _("04 - NCF replacement issued in contingency")),
            ("5", _("05 - Reference Electronic Consumer Invoice")),
        ]

    def _get_l10n_do_income_type(self):
        """ Return the list of income types required by DGII. """
        return [
            ("01", _("01 - Operational Incomes")),
            ("02", _("02 - Financial Incomes")),
            ("03", _("03 - Extraordinary Incomes")),
            ("04", _("04 - Leasing Incomes")),
            ("05", _("05 - Income for Selling Depreciable Assets")),
            ("06", _("06 - Other Incomes")),
        ]

    l10n_do_expense_type = fields.Selection(
        selection=lambda self: self.env["res.partner"]._get_l10n_do_expense_type(),
        string="Tipo de Costos y Gastos",
    )

    l10n_do_cancellation_type = fields.Selection(
        selection="_get_l10n_do_cancellation_type",
        string="Tipo de Cancelación",
        copy=False,
    )

    @api.model
    def _default_income_type(self):
        """
        Default para l10n_do_income_type.
        Siempre retorna '01' - el método create() lo ajustará si es necesario.
        """
        return '01'

    l10n_do_income_type = fields.Selection(
        selection="_get_l10n_do_income_type",
        string="Tipo de Ingreso",
        copy=False,
        default=_default_income_type,
    )

    l10n_do_origin_ncf = fields.Char(
        string="Modifies",
    )

    # MODIFICADO: Arturo Diaz Lora - 2026-02-22
    # Razón: Agregar campo auxiliar para seleccionar factura original al crear NC/ND manual
    # desde un dropdown, evitando errores al escribir el NCF manualmente
    l10n_do_origin_move_id = fields.Many2one(
        'account.move',
        string="Factura Original",
        copy=False,
        help="Seleccione la factura original que esta nota de crédito/débito modifica",
    )

    l10n_do_origin_move_type_filter = fields.Char(
        compute='_compute_l10n_do_origin_move_type_filter',
    )



    @api.depends('move_type', 'debit_origin_id')
    def _compute_l10n_do_origin_move_type_filter(self):
        for move in self:
            if move.move_type == 'out_refund':
                move.l10n_do_origin_move_type_filter = 'out_invoice'
            elif move.move_type == 'in_refund':
                move.l10n_do_origin_move_type_filter = 'in_invoice'
            else:
                move.l10n_do_origin_move_type_filter = move.move_type

    @api.onchange('l10n_do_origin_move_id')
    def _onchange_l10n_do_origin_move_id(self):
        """Auto-llenar NCF modificado y líneas de factura al seleccionar factura original
        MODIFICADO: Arturo Diaz Lora - 2026-02-22
        Razón: Portado desde v18 - Permite seleccionar factura original y copiar líneas
        automáticamente en NC/ND manuales"""
        if self.l10n_do_origin_move_id:
            origin = self.l10n_do_origin_move_id
            self.l10n_do_origin_ncf = origin.l10n_latam_document_number

            # Verificar si las líneas actuales ya corresponden a la factura original
            # para evitar duplicación cuando el onchange se dispara múltiples veces
            origin_product_lines = origin.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
            current_product_lines = self.invoice_line_ids.filtered(lambda l: l.display_type == 'product')

            # Comparar por producto, cantidad y precio para determinar si ya están copiadas
            already_copied = (
                len(current_product_lines) == len(origin_product_lines)
                and len(current_product_lines) > 0
                and all(
                    any(
                        cl.product_id.id == ol.product_id.id
                        and cl.quantity == ol.quantity
                        and cl.price_unit == ol.price_unit
                        for cl in current_product_lines
                    )
                    for ol in origin_product_lines
                )
            )

            if not already_copied:
                # Copiar líneas de la factura original usando recordsets virtuales
                new_lines = self.env['account.move.line']
                for line in origin_product_lines:
                    new_lines += new_lines.new({
                        'move_id': self._origin.id or self.id,
                        'product_id': line.product_id.id,
                        'name': line.name,
                        'quantity': line.quantity,
                        'product_uom_id': line.product_uom_id.id,
                        'price_unit': line.price_unit,
                        'discount': line.discount,
                        'tax_ids': line.tax_ids,
                        'analytic_distribution': line.analytic_distribution,
                    })
                self.invoice_line_ids = new_lines
        else:
            self.l10n_do_origin_ncf = False

    is_ecf_invoice = fields.Boolean(
        copy=False,
        default=lambda self: self.env.user.company_id.l10n_do_ecf_issuer
                             and self.env.user.company_id.l10n_do_country_code
                             and self.env.user.company_id.l10n_do_country_code == "DO",
    )

    is_debit_note = fields.Boolean(
        string="Is Debit Note",
        compute="_compute_is_debit_note",
        store=False,
        help="Indicates if this move is a debit note based on document type or debit_origin_id"
    )

    l10n_do_ecf_modification_code = fields.Selection(
        selection="_get_l10n_do_ecf_modification_code",
        string="Código de Modificación e-CF",
        copy=False,
    )

    l10n_do_ecf_security_code = fields.Char(string="e-CF Security Code", copy=False)
    l10n_do_ecf_sign_date = fields.Datetime(string="e-CF Sign Date", copy=False)
    l10n_do_electronic_stamp = fields.Char(
        string="Electronic Stamp",
        compute="_compute_l10n_do_electronic_stamp",
        store=True,
    )

    l10n_do_company_in_contingency = fields.Boolean(
        string="Company in contingency",
        compute="_compute_company_in_contingency",
    )
    l10n_latam_country_code = fields.Char(
        "Latam Country Code",
        compute="_compute_l10n_latam_country_code",
        store=True,
    )

    @api.depends('company_id')
    def _compute_l10n_latam_country_code(self):
        for move in self:
            move.l10n_latam_country_code = move.company_id.country_id.code if move.company_id and move.company_id.country_id else False

    l10n_do_fiscal_sequence_id = fields.Many2one(
        "account.fiscal.sequence", string="Secuencia Fiscal",
        copy=False, compute="_compute_l10n_do_fiscal_sequence", store=True,
    )

    l10n_do_ncf_expiration_date = fields.Date(
        string="Válida hasta",
    )

    l10n_do_fiscal_sequence_status = fields.Selection(
        [
            ("no_fiscal", "No fiscal"),
            ("fiscal_ok", "Ok"),
            ("almost_no_sequence", "Almost no sequence"),
            ("no_sequence", "Depleted"),
        ],
        compute="_compute_l10n_do_fiscal_sequence_status",
    )

    l10n_latam_amount_untaxed = fields.Monetary(compute='_compute_l10n_latam_amount_and_taxes')
    l10n_latam_tax_ids = fields.One2many(compute="_compute_l10n_latam_amount_and_taxes",
                                         comodel_name='account.move.line')
    l10n_latam_available_document_type_ids = fields.Many2many('l10n_latam.document.type',
                                                              compute='_compute_l10n_latam_available_document_types')

    l10n_latam_document_type_id = fields.Many2one(
        'l10n_latam.document.type', string='Tipo de Documento', readonly=False, index=True,
        compute='_compute_l10n_latam_document_type', store=True)
    # MODIFICADO: Arturo Diaz Lora - 2026-03-22
    # Razón: inverse solo formatea NCF/e-CF; name permanece INV/BILL (secuencia diario).
    l10n_latam_document_number = fields.Char(
        string='Número de Documento', copy=False, readonly=False,
        store=True, compute=False, inverse='_inverse_l10n_latam_document_number',
    )
    l10n_latam_use_documents = fields.Boolean(related='journal_id.l10n_latam_use_documents')
    l10n_latam_manual_document_number = fields.Boolean(compute='_compute_l10n_latam_manual_document_number',
                                                       string='Número Manual')

    total_discount = fields.Monetary(string='Descuento Total', store=True, readonly=True, compute='_compute_amount',
                                     tracking=True)
    warning_message = fields.Char(compute='_compute_warning_message', store=True, readonly=True)
    currency_rate = fields.Float(string="Tipo de cambio", compute='_get_currency_rate')

    # === Debit Note fields === #
    debit_origin_id = fields.Many2one(
        'account.move', 
        'Original Invoice Debited', 
        readonly=True, 
        copy=False, 
        index='btree_not_null',
        help="The original invoice that this debit note is related to"
    )
    debit_note_ids = fields.One2many(
        'account.move', 
        'debit_origin_id', 
        'Debit Notes',
        help="The debit notes created for this invoice"
    )
    debit_note_count = fields.Integer(
        'Number of Debit Notes', 
        compute='_compute_debit_count'
    )
    
    # === Credit Note fields === #
    credit_note_count = fields.Integer(
        'Number of Credit Notes',
        compute='_compute_credit_count'
    )

    @api.depends("l10n_do_ecf_security_code", "l10n_do_ecf_sign_date", "invoice_date")
    def _compute_l10n_do_electronic_stamp(self):
        l10n_do_ecf_invoice = self.filtered(
            lambda i: i.is_ecf_invoice
            and not i.l10n_latam_manual_document_number
            and i.l10n_do_ecf_security_code
            and i.state == "posted"
        )

        for invoice in l10n_do_ecf_invoice:
            if hasattr(invoice.company_id, "l10n_do_ecf_service_env"):
                ecf_service_env = invoice.company_id.l10n_do_ecf_service_env
            else:
                ecf_service_env = "TesteCF"

            doc_code_prefix = invoice.l10n_latam_document_type_id.doc_code_prefix
            is_rfc = (  # Es un Resumen Factura Consumo
                doc_code_prefix == "E32" and invoice.amount_total_signed < 250000
            )

            qr_string = "https://%s.dgii.gov.do/%s/ConsultaTimbre%s?" % (
                "fc" if is_rfc else "ecf",
                ecf_service_env,
                "FC" if is_rfc else "",
            )
            qr_string += "RncEmisor=%s&" % invoice.company_id.vat or ""
            if not is_rfc:
                qr_string += (
                    "RncComprador=%s&" % invoice.commercial_partner_id.vat
                    if invoice.l10n_latam_document_type_id.doc_code_prefix[1:]
                    not in ("43", "47")
                    else ""
                )
            qr_string += "ENCF=%s&" % invoice.l10n_do_fiscal_number or ""
            if not is_rfc:
                qr_string += "FechaEmision=%s&" % (
                    invoice.invoice_date or fields.Date.today()
                ).strftime("%d-%m-%Y")

            total_field = "l10n_do_invoice_total"
            if invoice.currency_id != invoice.company_id.currency_id:
                total_field += "_currency"
            l10n_do_total = invoice._get_l10n_do_amounts()[total_field]

            qr_string += "MontoTotal=%s&" % ("%f" % l10n_do_total).rstrip("0").rstrip(
                "."
            )
            if not is_rfc:
                qr_string += "FechaFirma=%s&" % invoice.l10n_do_ecf_sign_date.strftime(
                    "%d-%m-%Y %H:%M:%S"
                )

            special_chars = " !#$&'()*+,/:;=?@[]\"-.<>\\^_`"
            security_code = "".join(
                c.replace(c, "%" + c.encode("utf-8").hex()).upper()
                if c in special_chars
                else c
                for c in invoice.l10n_do_ecf_security_code or ""
            )
            qr_string += "CodigoSeguridad=%s" % security_code

            invoice.l10n_do_electronic_stamp = urls.url_quote_plus(qr_string, safe="%")

        (self - l10n_do_ecf_invoice).l10n_do_electronic_stamp = False

    def _clean_empty_origin_lines(self, vals):
        """MODIFICADO: Arturo Diaz Lora - 2026-02-22
        Razón: Portado desde v18 - Limpiar líneas de producto vacías (sin product_id y precio 0)
        cuando hay factura original seleccionada. Esto evita la duplicación causada por el
        web client que envía la línea vacía por defecto junto con las líneas del onchange."""
        if not vals.get('l10n_do_origin_move_id') or 'invoice_line_ids' not in vals:
            return
        line_commands = vals['invoice_line_ids']
        if not line_commands:
            return

        has_product_line = False
        cleaned = []
        for cmd in line_commands:
            if isinstance(cmd, (list, tuple)) and len(cmd) >= 3 and cmd[0] == 0:
                line_vals = cmd[2] if isinstance(cmd[2], dict) else {}
                # Es una línea de producto vacía (sin product_id y precio 0)?
                if (not line_vals.get('product_id')
                        and not line_vals.get('price_unit')
                        and line_vals.get('display_type', 'product') == 'product'):
                    continue
                else:
                    if line_vals.get('product_id'):
                        has_product_line = True
            cleaned.append(cmd)

        # Solo aplicar limpieza si encontramos al menos una línea con producto real
        if has_product_line:
            vals['invoice_line_ids'] = cleaned

    @api.model_create_multi
    def create(self, vals_list):
        """
        Sobrescribir create para ajustar l10n_do_income_type según el tipo de movimiento.
        Solo facturas de cliente deben tener este campo.
        MODIFICADO: Arturo Diaz Lora - 2026-02-22 - Agregar sincronización de l10n_do_origin_ncf
        y limpieza de líneas vacías duplicadas
        """
        for vals in vals_list:
            move_type = vals.get('move_type')
            # Si no es factura de cliente, limpiar el campo
            if move_type and move_type not in ('out_invoice', 'out_refund', 'out_receipt'):
                vals['l10n_do_income_type'] = False
            # Si es factura de cliente y no tiene valor, usar '01'
            elif move_type and move_type in ('out_invoice', 'out_refund', 'out_receipt'):
                if 'l10n_do_income_type' not in vals or not vals.get('l10n_do_income_type'):
                    vals['l10n_do_income_type'] = '01'

            # MODIFICADO: Arturo Diaz Lora - 2026-02-22
            # Sincronizar l10n_do_origin_ncf desde l10n_do_origin_move_id al crear
            if vals.get('l10n_do_origin_move_id') and not vals.get('l10n_do_origin_ncf'):
                origin = self.env['account.move'].browse(vals['l10n_do_origin_move_id'])
                if origin.exists() and origin.l10n_latam_document_number:
                    vals['l10n_do_origin_ncf'] = origin.l10n_latam_document_number

            # Limpiar líneas de producto vacías que el web client envía duplicadas
            self._clean_empty_origin_lines(vals)

        records = super(AccountMove, self).create(vals_list)

        # Post-create cleanup: eliminar líneas de producto vacías si existen
        # líneas con producto real y hay factura original seleccionada
        for move in records.filtered(lambda m: m.l10n_do_origin_move_id):
            empty_lines = move.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'
                and not l.product_id
                and not l.price_unit
            )
            real_lines = move.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'
                and l.product_id
            )
            if empty_lines and real_lines:
                _logger.info(
                    "Post-create cleanup: removing %d empty product lines from %s",
                    len(empty_lines), move.name or move.id
                )
                empty_lines.with_context(dynamic_unlink=True).unlink()

        return records

    def write(self, vals):
        """MODIFICADO: Arturo Diaz Lora - 2026-02-22
        Razón: Portado desde v18 - Sincronizar l10n_do_origin_ncf cuando se establece
        l10n_do_origin_move_id vía write y limpiar líneas vacías duplicadas"""
        if 'l10n_do_origin_move_id' in vals and vals['l10n_do_origin_move_id'] and 'l10n_do_origin_ncf' not in vals:
            origin = self.env['account.move'].browse(vals['l10n_do_origin_move_id'])
            if origin.exists() and origin.l10n_latam_document_number:
                vals['l10n_do_origin_ncf'] = origin.l10n_latam_document_number

        # Limpiar líneas de producto vacías cuando se escribe con factura original
        if vals.get('l10n_do_origin_move_id') or (
            'invoice_line_ids' in vals and any(m.l10n_do_origin_move_id for m in self)
        ):
            self._clean_empty_origin_lines(vals)

        res = super(AccountMove, self).write(vals)

        # Post-write cleanup: eliminar líneas de producto vacías cuando existen
        # líneas con producto real y hay factura original seleccionada
        if 'l10n_do_origin_move_id' in vals or 'invoice_line_ids' in vals:
            for move in self.filtered(
                lambda m: m.l10n_do_origin_move_id and m.state == 'draft'
            ):
                empty_lines = move.invoice_line_ids.filtered(
                    lambda l: l.display_type == 'product'
                    and not l.product_id
                    and not l.price_unit
                )
                real_lines = move.invoice_line_ids.filtered(
                    lambda l: l.display_type == 'product'
                    and l.product_id
                )
                if empty_lines and real_lines:
                    _logger.info(
                        "Removing %d empty product lines from %s (has %d real product lines)",
                        len(empty_lines), move.name or move.id, len(real_lines)
                    )
                    empty_lines.with_context(
                        skip_readonly_check=True,
                        dynamic_unlink=True
                    ).unlink()

        return res

    @api.depends('debit_note_ids')
    def _compute_debit_count(self):
        debit_data = self.env['account.move']._read_group(
            [('debit_origin_id', 'in', self.ids)],
            ['debit_origin_id'], 
            ['__count']
        )
        data_map = {debit_origin.id: count for debit_origin, count in debit_data}
        for inv in self:
            inv.debit_note_count = data_map.get(inv.id, 0.0)

    @api.depends('reversal_move_ids')
    def _compute_credit_count(self):
        credit_data = self.env['account.move']._read_group(
            [('reversed_entry_id', 'in', self.ids)],
            ['reversed_entry_id'], 
            ['__count']
        )
        data_map = {credit_origin.id: count for credit_origin, count in credit_data}
        for inv in self:
            inv.credit_note_count = data_map.get(inv.id, 0.0)

    def action_view_debit_notes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Debit Notes'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('debit_origin_id', '=', self.id)],
        }

    def action_view_credit_notes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Credit Notes'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('reversed_entry_id', '=', self.id)],
        }

    def action_debit_note(self):
        """ Create a debit note for this invoice """
        self.ensure_one()
        action = self.env.ref('l10n_do_accounting.action_account_debit_note')._get_action_dict()
        action['context'] = {
            'default_move_ids': [self.id],
            'default_move_type': self.move_type,
        }
        return action

    def action_credit_note(self):
        """ Create a credit note for this invoice """
        self.ensure_one()
        action = self.env.ref('account.action_view_account_move_reversal')._get_action_dict()
        action['context'] = {
            'default_move_ids': [self.id],
        }
        return action

    # MODIFICADO: Arturo Diaz Lora - 2026-03-27
    # Razón: Para facturas de proveedor DO, excluir registros con prefijos NCF (B01, E31, etc.)
    # del lookup de secuencia para que las nuevas facturas usen el formato estándar BILL1/YYYY/MM/NNNN.
    # Sin este filtro, _get_last_sequence() encuentra registros viejos con sequence_prefix "B01 B0"
    # y todas las facturas nuevas heredan ese prefijo incorrecto.
    def _get_last_sequence_domain(self, relaxed=False):
        where_string, param = super()._get_last_sequence_domain(relaxed)
        if hasattr(self.journal_id, 'debit_sequence') and self.journal_id.debit_sequence:
            where_string += " AND debit_origin_id IS " + ("NOT NULL" if self.debit_origin_id else "NULL")
        # Para facturas de proveedor DO: excluir registros con prefijos NCF
        # para que _get_last_sequence() use _get_starting_sequence() (formato BILL1/...)
        if (self.company_id.country_id.code == 'DO'
                and self.move_type in ('in_invoice', 'in_refund', 'in_receipt')
                and self.l10n_latam_use_documents):
            where_string += " AND sequence_prefix LIKE %(journal_prefix)s"
            param['journal_prefix'] = self.journal_id.code + '/%'
        return where_string, param

    def _get_starting_sequence(self):
        # MODIFICADO: Arturo Diaz Lora - 2026-03-22
        # Razón: En RD, name debe seguir secuencia contable (INV/..., BILL/...), no el
        # patrón E31 00000000 de l10n_latam. El NCF/e-CF va en l10n_latam_document_number.
        if (
            self.l10n_latam_use_documents
            and (self.l10n_latam_country_code == "DO" or self.company_id.country_id.code == "DO")
        ):
            starting_sequence = super(LatamAccountMove, self)._get_starting_sequence()
        else:
            starting_sequence = super()._get_starting_sequence()
        if (
            hasattr(self.journal_id, 'debit_sequence')
            and self.journal_id.debit_sequence
            and self.debit_origin_id
            and self.move_type in ("in_invoice", "out_invoice")
        ):
            starting_sequence = "D" + starting_sequence
        return starting_sequence

    @api.depends('l10n_do_fiscal_sequence_id')
    def _compute_warning_message(self):
        for move in self.filtered(lambda m: m.l10n_do_fiscal_sequence_id):
            move.warning_message = False
            warnings = []
            if move.l10n_do_fiscal_sequence_id.warning_gap >= move.l10n_do_fiscal_sequence_id.sequence_remaining:
                warnings.append(
                    "Secuencia fiscal {} proxima a alcanzar el maximo.".format(move.l10n_do_fiscal_sequence_id.name))
            if warnings:
                warnings = [_("This invoice can be erroneous :")] + warnings
                move.warning_message = "\n  ・ ".join(warnings)

    def _get_currency_rate(self):
        for record in self:
            record.currency_rate = abs(
                round(1 / (self.amount_total / (self.amount_total_signed or 1) or 1), 2)
            )

    def _compute_amount(self):
        super()._compute_amount()
        for inv in self:
            # if inv.move_type not in ('entry',):
            if inv.is_invoice(include_receipts=False):
                line_total_discount = sum(
                    (line.quantity * line.price_unit - line.price_subtotal) for line in inv.invoice_line_ids)
                discount_global = sum(line.price_unit for line in inv.invoice_line_ids if line.price_unit < 0)
                total_discount = line_total_discount + abs(discount_global)
                inv.total_discount = total_discount

    @api.depends('l10n_latam_document_type_id', 'l10n_latam_document_type_id.internal_type', 'debit_origin_id')
    def _compute_is_debit_note(self):
        """Compute if this move is a debit note based on document type or debit_origin_id"""
        for move in self:
            # Check if it's a debit note by document type or debit_origin_id
            is_debit = False
            if move.debit_origin_id:
                # Has debit origin - it's a debit note
                is_debit = True
            elif move.l10n_latam_document_type_id and move.l10n_latam_document_type_id.internal_type == 'debit_note':
                # Document type is debit_note - it's a debit note
                is_debit = True
            elif move.l10n_latam_document_type_id and move.l10n_latam_document_type_id.l10n_do_ncf_type in ('debit_note', 'e-debit_note'):
                # NCF type is debit note - it's a debit note
                is_debit = True
            move.is_debit_note = is_debit

    # Agregado 2025-11-22 por Arturo Diaz Lora
    # Onchange para actualizar visibilidad de campos en tiempo real en la UI
    # Cuando el usuario selecciona tipo de documento en el formulario, los campos
    # NCF modificado y Código Modificación e-CF deben aparecer inmediatamente
    @api.onchange('l10n_latam_document_type_id', 'debit_origin_id')
    def _onchange_document_type_for_visibility(self):
        """Force recompute of is_debit_note to update field visibility in UI"""
        # Este onchange fuerza la recalculación de is_debit_note
        # para que los campos invisibles se actualicen en tiempo real
        # No necesita retornar nada, solo disparar el compute
        pass

    @api.depends("company_id", "company_id.l10n_do_ecf_issuer")
    def _compute_company_in_contingency(self):
        for invoice in self:
            ecf_invoices = self.search([("is_ecf_invoice", "=", True)], limit=1)
            invoice.l10n_do_company_in_contingency = bool(
                ecf_invoices and not invoice.company_id.l10n_do_ecf_issuer
            )

    def button_cancel(self):

        fiscal_invoice = self.filtered(
            lambda inv: inv.l10n_latam_country_code == "DO"
                        and self.move_type[-6:] in ("nvoice", "refund")
                        and inv.l10n_latam_use_documents
        )

        if len(fiscal_invoice) > 1:
            raise ValidationError(
                _("You cannot cancel multiple fiscal invoices at a time.")
            )

        if fiscal_invoice and not self.env.user.has_group(
                "l10n_do_accounting.group_l10n_do_fiscal_invoice_cancel"
        ):
            raise AccessError(_("You are not allowed to cancel Fiscal Invoices"))

        if fiscal_invoice:
            action = self.env.ref(
                "l10n_do_accounting.action_account_move_cancel"
            ).read()[0]
            action["context"] = {"default_move_id": fiscal_invoice.id}
            return action

        return super(AccountMove, self).button_cancel()

    def action_reverse(self):

        fiscal_invoice = self.filtered(
            lambda inv: inv.l10n_latam_country_code == "DO"
                        and self.move_type[-6:] in ("nvoice", "refund")
        )
        if fiscal_invoice and not self.env.user.has_group(
                "l10n_do_accounting.group_l10n_do_fiscal_credit_note"
        ):
            raise AccessError(_("You are not allowed to issue Fiscal Credit Notes"))

        return super(AccountMove, self).action_reverse()

    def _get_l10n_latam_documents_domain(self):
        """
        Override to ensure proper domain for Dominican document types
        """
        self.ensure_one()

        # MODIFICADO: Arturo Diaz Lora - 2026-02-16
        # Si el diario no usa documentos fiscales, omitir todas las validaciones
        # Esto permite que diarios con l10n_latam_use_documents=False usen el flujo natural de Odoo
        if not self.l10n_latam_use_documents:
            return []

        # Validate partner DGII taxpayer type for Dominican Republic
        # Only validate for posted moves or when creating real invoices, not in wizard contexts
        if (not self.partner_id.l10n_do_dgii_tax_payer_type 
            and self.company_id.country_id.code == "DO"
            and not self.env.context.get('internal_type')  # Skip validation in wizard contexts
            and self.state != 'draft'):
            raise ValidationError(
                _(
                    "A Type Of Taxpayers is Mandatory. "
                    "Please set the current Type of this contact"
                )
            )

        # Determine internal types based on move_type and debit_origin_id
        if self.move_type in ['out_refund', 'in_refund']:
            internal_types = ['credit_note']
        elif self.debit_origin_id or self.env.context.get('internal_type') == 'debit_note':
            # This is a debit note - either has debit_origin_id or comes from debit note wizard
            internal_types = ['debit_note']
        elif self.move_type in ['in_invoice', 'in_receipt']:
            # Vendor bills and receipts
            # IMPORTANTE: Solo permitir tipos de documentos de COMPRA que se envían a DGII (E41, E43, E47)
            # Las facturas de venta recibidas (E31, E32, etc.) NO deben enviarse a DGII
            internal_types = ['in_invoice', 'invoice', 'debit_note']
        else:
            # Customer invoices - allow both invoice and debit_note types
            internal_types = ['invoice', 'debit_note']
        
        domain = [('internal_type', 'in', internal_types)]

        if (
                self.journal_id.l10n_latam_use_documents
                and self.journal_id.company_id.country_id == self.env.ref("base.do")
        ):
            # Get base NCF types from journal
            if self.partner_id == self.company_id.partner_id:
                ncf_types = ['minor', 'e-minor', 'import']
            else:
                ncf_types = self.journal_id._get_journal_ncf_types(
                    counterpart_partner=self.partner_id.commercial_partner_id, invoice=self
                )
            
            # For credit notes, REPLACE (don't extend) with credit note NCF types
            if self.move_type in ['out_refund', 'in_refund']:
                # MODIFICADO: Arturo Diaz Lora - 2026-03-27
                # Para notas de crédito de proveedor, siempre mostrar ambos tipos (electrónico y físico)
                # porque el proveedor puede ser emisor electrónico aunque la compañía no lo sea
                if self.move_type == 'in_refund':
                    # Vendor credit note - show both electronic and physical types
                    ncf_types = ['credit_note', 'e-credit_note']
                elif self.company_id.l10n_do_ecf_issuer:
                    # Customer credit note with ECF issuer - only electronic
                    ncf_types = ['e-credit_note']
                else:
                    # Customer credit note without ECF issuer - only physical
                    ncf_types = ['credit_note']

            # For debit notes, REPLACE (don't extend) with debit note NCF types
            elif self.debit_origin_id or self.env.context.get('internal_type') == 'debit_note':
                # MODIFICADO: Arturo Diaz Lora - 2026-03-27
                # Para notas de débito de proveedor, siempre mostrar ambos tipos
                is_purchase_debit = self.move_type == 'in_invoice' or self.env.context.get('active_model') == 'account.move' and self.env.context.get('active_ids') and self.env['account.move'].browse(self.env.context.get('active_ids')[0]).move_type == 'in_invoice'
                if is_purchase_debit:
                    # Vendor debit note - show both electronic and physical types
                    ncf_types = ['debit_note', 'e-debit_note']
                elif self.company_id.l10n_do_ecf_issuer:
                    # Customer debit note with ECF issuer - only electronic
                    ncf_types = ['e-debit_note']
                else:
                    # Customer debit note without ECF issuer - only physical
                    ncf_types = ['debit_note']

            # For vendor bills, EXCLUDE certain sales NCF types that don't apply to purchases
            # IMPORTANT: B01/E31 (Crédito Fiscal) DEBE permitirse cuando recibes facturas de proveedores contribuyentes
            # Solo se excluyen tipos que definitivamente no aplican a compras:
            # - Consumo (B02/E32): solo para ventas a consumidor final
            # - Régimen Especial (B14/E44): solo para empresas en régimen especial cuando VENDEN
            # - Gubernamental (B15/E45): solo para ventas a entidades gubernamentales
            # - Exportación (B16/E46): solo para ventas al exterior
            elif self.move_type in ['in_invoice', 'in_receipt']:
                # Exclude sales-only NCF types from vendor bills
                # NOTE: fiscal and e-fiscal (B01/E31) are NOT excluded - they are valid for vendor bills
                excluded_sales_types = [
                    'consumer', 'e-consumer',       # 02, E32 - Consumo (solo para ventas a consumidor final)
                    'special', 'e-special',         # 14, E44 - Régimen Especial (solo cuando empresa VENDE)
                    'governmental', 'e-governmental', # 15, E45 - Gubernamental (solo para ventas a gobierno)
                    'export', 'e-export',           # 16, E46 - Exportación (solo para ventas al exterior)
                ]
                # Remove excluded types from ncf_types
                ncf_types = [t for t in ncf_types if t not in excluded_sales_types]

            domain += [
                "|",
                ("l10n_do_ncf_type", "=", False),
                ("l10n_do_ncf_type", "in", ncf_types),
            ]
            codes = self.journal_id._get_journal_codes()
            if codes:
                domain.append(("code", "in", codes))
        return domain

    @api.constrains('l10n_latam_document_number', 'l10n_latam_document_type_id')
    def _check_ncf_format(self):
        """Validate NCF format according to DGII specifications"""
        # MODIFICADO: Arturo Diaz Lora - 2026-03-22
        # Razón: Validar aunque l10n_latam_manual_document_number sea False (name ya no es NCF).
        for rec in self.filtered(lambda x: x.l10n_latam_country_code == 'DO' and x.l10n_latam_use_documents and x.l10n_latam_document_number):
            if not rec._validate_ncf_format():
                raise ValidationError(_(
                    'El número de documento "%s" no cumple con los requisitos de formato NCF de la DGII.\n\n'
                    'NCF Físicos (serie B): B + 2 dígitos (01-17) + 9 dígitos = 11 caracteres\n'
                    'NCF Electrónicos (serie E): E + 2 dígitos (31-47) + 10 dígitos = 13 caracteres\n\n'
                    'Por favor verifique el formato según el tipo de documento fiscal.',
                    rec.l10n_latam_document_number
                ))

    def _validate_ncf_format(self):
        """Validate NCF format according to DGII specifications"""
        if not self.l10n_latam_document_number or not self.l10n_latam_document_type_id:
            return True
            
        ncf = self.l10n_latam_document_number.strip()
        doc_type = self.l10n_latam_document_type_id
        
        # Check if it's a physical NCF (B series)
        if doc_type.l10n_do_ncf_type in ['fiscal', 'minor', 'informal', 'exterior']:
            # Format: B + 2 digits + 9 digits = 11 characters total
            if len(ncf) != 11:
                return False
            if not ncf.startswith('B'):
                return False
            if not ncf[1:3].isdigit():
                return False
            if not ncf[3:].isdigit():
                return False
            # Validate type code (01-17 for physical NCFs)
            type_code = int(ncf[1:3])
            if type_code < 1 or type_code > 17:
                return False
                
        # Check if it's an electronic NCF (E series)
        elif doc_type.l10n_do_ncf_type in ['e-fiscal', 'e-consumer', 'e-debit_note', 'e-credit_note',
                                            'e-minor', 'e-informal', 'e-special', 'e-governmental',
                                            'e-export', 'e-exterior']:
            # Format: E + 2 digits + 10 digits = 13 characters total
            if len(ncf) != 13:
                return False
            if not ncf.startswith('E'):
                return False
            if not ncf[1:3].isdigit():
                return False
            if not ncf[3:].isdigit():
                return False
            # Validate type code (31-47 for electronic NCFs)
            type_code = int(ncf[1:3])
            if type_code < 31 or type_code > 47:
                return False
                
        # For non-fiscal documents, no specific format validation
        elif doc_type.l10n_do_ncf_type == 'non-fiscal':
            return True
            
        return True

    @api.constrains('l10n_latam_document_type_id', 'move_type', 'debit_origin_id', 'l10n_do_origin_ncf')
    def _check_invoice_type_document_type(self):
        # MODIFICADO: Arturo Diaz Lora - 2026-02-16
        # Agregar verificación de l10n_latam_use_documents para permitir flujo natural de Odoo
        for rec in self.filtered(lambda x: x.l10n_latam_use_documents and x.l10n_latam_document_type_id and x.l10n_latam_document_type_id.internal_type):
            internal_type = rec.l10n_latam_document_type_id.internal_type
            invoice_type = rec.move_type

            # Validate debit notes - identified by debit_origin_id field
            if internal_type == 'debit_note':
                # In Odoo v18, debit notes use same move_type as original invoice (out_invoice/in_invoice)
                # but are identified by having debit_origin_id set
                # Modificado 2025-11-22 por Arturo Diaz Lora - Comentada validación para permitir creación manual
                # Razón: Usuario requiere crear notas de débito manualmente sin wizard
                # El campo computed is_debit_note detecta correctamente las notas por tipo de documento
                # if not rec.debit_origin_id and rec.l10n_latam_document_type_id.code != '99':
                #     raise ValidationError(_('No puede usar un tipo de documento %s sin establecer un origen de débito. Use el asistente "Crear Nota de Débito" en su lugar.', internal_type))
                if invoice_type not in ['out_invoice', 'in_invoice'] and rec.l10n_latam_document_type_id.code != '99':
                    raise ValidationError(_('No puede usar un tipo de documento %s con un tipo de movimiento %s. Las notas de débito deben usar tipos de movimiento out_invoice o in_invoice.', internal_type, invoice_type))
                
                # NCF modificado se establece automáticamente para notas de débito pero no es requerido como validación
                # Las regulaciones dominicanas no exigen validación estricta del NCF modificado en notas de débito
                pass

            # Validate credit notes
            elif internal_type == 'credit_note':
                if invoice_type not in ['out_refund', 'in_refund'] and rec.l10n_latam_document_type_id.code != '99':
                    raise ValidationError(_('No puede usar un tipo de documento %s con un tipo de movimiento %s. Las notas de crédito requieren tipos de movimiento out_refund o in_refund.', internal_type, invoice_type))
                
                # Ensure l10n_do_origin_ncf is set for credit notes
                if not rec.l10n_do_origin_ncf and rec.l10n_latam_country_code == "DO" and rec.l10n_latam_use_documents:
                    raise ValidationError(_('El campo "NCF modificado" es requerido para notas de crédito en República Dominicana.'))
            
            # Validate invoices
            elif internal_type == 'invoice':
                if invoice_type in ['out_refund', 'in_refund'] and rec.l10n_latam_document_type_id.code != '99':
                    raise ValidationError(_('No puede usar un tipo de documento %s con un tipo de movimiento %s', internal_type, invoice_type))

    @api.onchange('l10n_latam_document_number', 'l10n_latam_document_type_id')
    def _onchange_document_number(self):
        """Validate NCF format on change and show warning if invalid"""
        if (self.l10n_latam_country_code == 'DO' and
            self.l10n_latam_use_documents and
            self.l10n_latam_document_number and
            self.l10n_latam_document_type_id):
            
            if not self._validate_ncf_format():
                return {
                    'warning': {
                        'title': _('Formato de NCF Inválido'),
                        'message': _('El número de documento "%s" no cumple con los requisitos de formato NCF de la DGII.\n\n'
                                   'NCF Físicos (serie B): B + 2 dígitos (01-17) + 9 dígitos = 11 caracteres\n'
                                   'NCF Electrónicos (serie E): E + 2 dígitos (31-47) + 10 dígitos = 13 caracteres\n\n'
                                   'Por favor verifique el formato según el tipo de documento fiscal.',
                                   self.l10n_latam_document_number)
                    }
                }

    @api.onchange("partner_id")
    def _onchange_partner_id(self):

        if (
                self.company_id.country_id == self.env.ref("base.do")
                and self.l10n_latam_document_type_id
                and self.move_type == "in_invoice"
                and self.partner_id
        ):
            self.l10n_do_expense_type = (
                self.partner_id.l10n_do_expense_type
                if not self.l10n_do_expense_type
                else self.l10n_do_expense_type
            )

        # MODIFICADO: Arturo Diaz Lora - 2026-02-22
        # Razón: Limpiar factura original seleccionada cuando cambia el partner
        self.l10n_do_origin_move_id = False

        return super(AccountMove, self)._onchange_partner_id()

    @api.constrains("name", "partner_id", "company_id")
    def _check_unique_vendor_number(self):

        l10n_do_invoice = self.filtered(
            lambda inv: inv.l10n_latam_country_code == "DO"
                        and inv.l10n_latam_use_documents
                        and inv.is_purchase_document()
                        and inv.l10n_latam_document_number
        )

        for rec in l10n_do_invoice:
            domain = [
                ("move_type", "=", rec.move_type),
                ("l10n_latam_document_number", "=", rec.l10n_latam_document_number),
                ("company_id", "=", rec.company_id.id),
                ("id", "!=", rec.id),
                ("commercial_partner_id", "=", rec.commercial_partner_id.id),
            ]
            if rec.search(domain):
                raise ValidationError(
                    _("Vendor bill NCF must be unique per vendor and company.")
                )

    # MODIFICADO: Arturo Diaz Lora - 2026-03-22
    # Razón: name = secuencia contable (INV/BILL); NCF/e-CF solo en l10n_latam_document_number.

    def _is_manual_document_number(self):
        """Determina si el documento debe usar numeración manual.

        MODIFICADO: Arturo Diaz Lora - 2026-03-22
        Razón: En RD, con comprobantes fiscales el número contable (name) no es el NCF;
        forzar NO manual para que _compute_name use secuencia de diario (salvo otros países).
        """
        if (
                self.company_id.country_id == self.env.ref("base.do")
                and self.l10n_latam_document_type_id
        ):
            # Compras / recibos: BILL/... en name; NCF del proveedor en l10n_latam_document_number
            if self.move_type in ("in_invoice", "in_refund", "in_receipt"):
                return False

            # Para notas de crédito de cliente, usar secuencias automáticas (NO manual)
            if self.move_type == "out_refund":
                return False

            # Para notas de débito de cliente (identificadas por debit_origin_id), usar secuencias automáticas (NO manual)
            if self.move_type == "out_invoice" and self.debit_origin_id:
                return False

        return super()._is_manual_document_number()

    @api.onchange('l10n_latam_document_type_id', 'l10n_latam_document_number', 'partner_id')
    def _inverse_l10n_latam_document_number(self):
        """En RD no copiar NCF/e-CF al name; el estándar latam sí lo hace en otros países."""
        do_doc = self.filtered(
            lambda m: m.company_id.country_id.code == "DO" and m.l10n_latam_use_documents
        )
        for rec in do_doc.filtered(lambda x: x.l10n_latam_document_type_id):
            if not rec.l10n_latam_document_number:
                continue
            l10n_latam_document_number = rec.l10n_latam_document_number
            if not rec._skip_format_document_number():
                l10n_latam_document_number = rec.l10n_latam_document_type_id._format_document_number(
                    rec.l10n_latam_document_number
                )
            if rec.l10n_latam_document_number != l10n_latam_document_number:
                rec.l10n_latam_document_number = l10n_latam_document_number
        remaining = self - do_doc
        if remaining:
            super(AccountMove, remaining)._inverse_l10n_latam_document_number()

    def _get_name_invoice_report(self):
        self.ensure_one()
        # if self.l10n_latam_use_documents and self.l10n_latam_country_code == "DO":
        #     return "l10n_do_accounting.report_invoice_document_inherited"
        # return super()._get_name_invoice_report()
        report_name = "l10n_do_accounting.report_invoice_document_inherited"
        _logger.debug(f"🖨️ _get_name_invoice_report para {self.name}: {report_name}")
        #_logger.debug(f"   QR Code: {'EXISTS' if self.qr_code else 'NULL'} ({len(self.qr_code) if self.qr_code else 0} bytes)")
        #_logger.debug(f"   Security Code: {self.l10n_do_ecf_security_code}")
        return report_name

    def _debug_qr_render_conditions(self):
        """Método helper para debug de condiciones de renderizado del QR"""
        self.ensure_one()

        is_l10n_do = self.l10n_latam_use_documents and self.company_id.country_id and self.company_id.l10n_do_country_code == 'DO'
        has_qr = bool(self.qr_code)
        has_security = bool(self.l10n_do_ecf_security_code)
        should_show = is_l10n_do and has_qr and has_security

        _logger.debug(f"🔍 DEBUG QR RENDER CONDITIONS para {self.name}:")
        _logger.debug(f"   l10n_latam_use_documents: {self.l10n_latam_use_documents}")
        _logger.debug(f"   company_id.country_id: {self.company_id.country_id.code if self.company_id.country_id else 'NULL'}")
        _logger.debug(f"   company_id.l10n_do_country_code: {self.company_id.l10n_do_country_code}")
        _logger.debug(f"   → is_l10n_do_invoice: {is_l10n_do}")
        _logger.debug(f"   qr_code exists: {has_qr}")
        if has_qr:
            _logger.debug(f"   qr_code size: {len(self.qr_code)} bytes")
            _logger.debug(f"   qr_code type: {type(self.qr_code)}")
            # Intentar decodificar
            try:
                decoded = self.qr_code.decode('utf-8')
                _logger.debug(f"   qr_code can decode: YES ({len(decoded)} chars)")
                _logger.debug(f"   qr_code first 50: {decoded[:50]}")
            except Exception as e:
                _logger.error(f"   qr_code decode ERROR: {e}")
        _logger.debug(f"   l10n_do_ecf_security_code: {has_security} ({self.l10n_do_ecf_security_code})")
        _logger.debug(f"   → SHOULD SHOW QR: {'✅ YES' if should_show else '❌ NO'}")

        return should_show

    @api.depends(
        "journal_id",
        "l10n_latam_use_documents",
        "state",
        "l10n_latam_document_type_id",
        "invoice_date", "move_type", "debit_origin_id", "partner_id",
    )
    def _compute_l10n_do_fiscal_sequence(self):
        """ Compute the sequence and fiscal position to be used depending on
            the fiscal type that has been set on the invoice (or partner).
        """
        _logger.debug("=== COMPUTING FISCAL SEQUENCE FOR ACCOUNT MOVES ===")
        for inv in self:
            _logger.debug(f"Processing move: {inv.name} ({inv.move_type})")
            _logger.debug(f"Document type: {inv.l10n_latam_document_type_id}")
            _logger.debug(f"Debit origin ID: {inv.debit_origin_id}")
            _logger.debug(f"Use documents: {inv.l10n_latam_use_documents}")
            
            assing_document_number = False
            
            # CUSTOMER INVOICES AND NOTES (out_*) - Use automatic sequences
            if inv.move_type == "out_invoice" and not inv.debit_origin_id:
                # Customer regular invoice
                assing_document_number = True
                _logger.debug("Customer regular invoice -> assign document number = True")
            elif inv.move_type == "out_invoice" and inv.debit_origin_id:
                # Customer debit note (identified by debit_origin_id)
                assing_document_number = True
                _logger.debug("Customer debit note -> assign document number = True")
            elif inv.move_type == "out_refund":
                # Customer credit note
                assing_document_number = True
                _logger.debug("Customer credit note -> assign document number = True")

            # VENDOR INVOICES - Some use automatic sequences, some don't
            # La empresa EMITE el comprobante en estos casos específicos:
            elif inv.move_type == "in_invoice" and not inv.debit_origin_id:
                ncf_type = inv.l10n_latam_document_type_id.l10n_do_ncf_type

                # B13/E43 (Gasto Menor): Emisor y receptor son la misma empresa
                # Según DGII: "el emisor y beneficiario del gasto son la misma entidad"
                if ncf_type in ("minor", "e-minor") and inv.partner_id == inv.company_id.partner_id:
                    assing_document_number = True
                    _logger.debug("Gasto Menor (E43/B13) -> auto sequence")

                # B11/E41 (Compras): Para proveedores informales SIN RNC
                # La empresa emite el comprobante para documentar compra a proveedor no registrado
                elif ncf_type in ("informal", "e-informal"):
                    assing_document_number = True
                    _logger.debug("Compras Informal (E41/B11) -> auto sequence")

                # B17/E47 (Pago al Exterior): Para pagos a no residentes
                # La empresa emite el comprobante para documentar el pago
                elif ncf_type in ("exterior", "e-exterior"):
                    assing_document_number = True
                    _logger.debug("Pago Exterior (E47/B17) -> auto sequence")

            # VENDOR CREDIT AND DEBIT NOTES - Use manual numbers from vendor
            elif inv.move_type == "in_refund":
                # Vendor credit note - always manual
                assing_document_number = False
            elif inv.move_type == "in_invoice" and inv.debit_origin_id:
                # Vendor debit note - always manual
                assing_document_number = False

            _logger.debug(f"Final decision: assign_document_number = {assing_document_number}")
            
            if inv.l10n_latam_use_documents and assing_document_number:
                _logger.debug("Searching for fiscal sequence...")

                domain = [
                    ('company_id', 'parent_of', inv.company_id.ids),
                    ("fiscal_type_id", "=", inv.l10n_latam_document_type_id.id),
                    ("state", "=", "active"),
                ]
                if inv.invoice_date:
                    domain.append(("expiration_date", ">=", inv.invoice_date))
                else:
                    today = fields.Date.context_today(inv)
                    domain.append(("expiration_date", ">=", today))

                _logger.debug(f"Fiscal sequence search domain: {domain}")

                l10n_do_fiscal_sequence_id = inv.env["account.fiscal.sequence"].search(
                    domain, order="expiration_date, id desc"
                )
                _logger.debug(f"Found fiscal sequences: {l10n_do_fiscal_sequence_id}")

                if not l10n_do_fiscal_sequence_id:
                    _logger.warning("No fiscal sequence found!")
                    continue

                l10n_do_fiscal_sequence_id.ensure_one()
                _logger.debug(f"Selected fiscal sequence: {l10n_do_fiscal_sequence_id.name} (state: {l10n_do_fiscal_sequence_id.state})")

                if l10n_do_fiscal_sequence_id.state == "active":
                    inv.l10n_do_fiscal_sequence_id = l10n_do_fiscal_sequence_id
                    # Auto-llenar fecha de expiración desde la secuencia fiscal
                    if not inv.l10n_do_ncf_expiration_date:
                        inv.l10n_do_ncf_expiration_date = l10n_do_fiscal_sequence_id.expiration_date
                    _logger.debug(f"SET fiscal sequence: {l10n_do_fiscal_sequence_id.name}, expiration: {l10n_do_fiscal_sequence_id.expiration_date}")
                else:
                    inv.l10n_do_fiscal_sequence_id = False
                    _logger.warning("Fiscal sequence is not active, set to False")
            else:
                inv.l10n_do_fiscal_sequence_id = False
                _logger.debug("No use documents or no assign document number -> fiscal sequence = False")

    @api.depends(
        "l10n_do_fiscal_sequence_id",
        "l10n_do_fiscal_sequence_id.sequence_remaining",
        "l10n_do_fiscal_sequence_id.remaining_percentage",
        "state",
        "journal_id",
    )
    def _compute_l10n_do_fiscal_sequence_status(self):
        """ Identify the percentage fiscal sequences that has been used so far.
            With this result the user can be warned if it's above the threshold
            or if there's no more sequences available.
        """
        for inv in self:

            if not inv.l10n_latam_use_documents or not inv.l10n_do_fiscal_sequence_id:
                inv.l10n_do_fiscal_sequence_status = "no_fiscal"
            else:
                fs_id = inv.l10n_do_fiscal_sequence_id  # Fiscal Sequence
                remaining = fs_id.sequence_remaining
                remaining_percent = fs_id.remaining_percentage
                seq_length = fs_id.sequence_end - fs_id.sequence_start + 1

                consumed_percent = round(1 - (remaining / seq_length), 2) * 100

                if consumed_percent < remaining_percent:
                    inv.l10n_do_fiscal_sequence_status = "fiscal_ok"
                elif remaining > 0 and consumed_percent >= remaining_percent:
                    inv.l10n_do_fiscal_sequence_status = "almost_no_sequence"
                else:
                    inv.l10n_do_fiscal_sequence_status = "no_sequence"

    @api.constrains("state", "invoice_line_ids", "partner_id")
    def validate_products_export_ncf(self):
        """ Validates that an invoices with a partner from country != DO
            and products type != service must have Exportaciones NCF.
            See DGII Norma 05-19, Art 10 for further information.
        """
        for inv in self:
            if (
                    inv.move_type == "out_invoice"
                    and inv.state in ("posted", "cancel")
                    and inv.partner_id.country_id
                    and inv.partner_id.country_id.code != "DO"
                    and inv.l10n_latam_use_documents
            ):
                if any([p for p in inv.invoice_line_ids.mapped("product_id") if p.type != "service"]):
                    if (
                            ncf_dict.get(inv.l10n_latam_document_type_id.doc_code_prefix) in (
                            "exterior", "e-exterior")
                    ):
                        raise UserError(_("Goods sales to overseas customers must have " "Exportaciones Fiscal Type"))
                elif (
                        ncf_dict.get(inv.l10n_latam_document_type_id.doc_code_prefix) not in ("consumo", "e-consumer")
                ):
                    raise UserError(_("Service sales to overseas customer must have " "Consumo Fiscal Type"))

    @api.constrains("state", "tax_line_ids")
    def validate_informal_withholding(self):
        """ Validates an invoice with Comprobante de Compras has 100% ITBIS
            withholding.
            See DGII Norma 05-19, Art 7 for further information.
        """
        for inv in self.filtered(lambda i: i.move_type == "in_invoice" and i.state == "posted"):
            if (
                    (
                            ncf_dict.get(inv.l10n_latam_document_type_id.doc_code_prefix) in ("informal", "e-informal")
                    )
                    and inv.l10n_latam_use_documents
            ):
                # If the sum of all taxes of category ITBIS is not 0
                if sum(
                        [
                            tax.amount
                            for tax in inv.tax_line_ids.mapped("tax_id").filtered(
                            lambda t: t.purchase_tax_type in ['itbis', 'ritbis'])
                        ]
                ):
                    raise UserError(_("You must withhold 100% of ITBIS"))

    @api.constrains('state', 'tax_line_ids')
    def validate_special_exempt(self):
        """ Validates an invoice with Regímenes Especiales sale_fiscal_type
            does not contain nor ITBIS or ISC.
            See DGII Norma 05-19, Art 3 for further information.
        """
        for inv in self:
            if inv.l10n_latam_use_documents:
                if (
                        inv.move_type == 'out_invoice'
                        and inv.state in ('posted', 'cancel')
                        and inv.l10n_latam_document_type_id.l10n_do_ncf_type
                        and 'special' in inv.l10n_latam_document_type_id.l10n_do_ncf_type
                ):

                    # If any invoice tax in ITBIS or ISC
                    if any([
                        tax for tax in inv.tax_line_ids.mapped('tax_id')
                                .filtered(lambda tax: tax.tax_group_id.name in (
                                'ITBIS', 'ISC') and tax.amount != 0)
                    ]):
                        raise UserError(_(
                            "No puede validar una factura para Regímen Especial "
                            " con ITBIS/ISC.\n\n"
                            "Consulte Norma General 05-19, Art. 3 de la DGII")
                        )

    def _post(self, soft=True):
        """ After all invoice validation routine, consume a NCF sequence and
            write it into ref field.
        """
        res = super()._post(soft)
        for inv in self:
            non_payer_type_invoices = self.filtered(
                lambda i: i.company_id.country_id == self.env.ref("base.do")
                          and i.l10n_latam_use_documents
                          and not i.partner_id.l10n_do_dgii_tax_payer_type
            )

            if non_payer_type_invoices:
                raise ValidationError(_("Las facturas fiscales requieren tipo fiscal del socio: %s" % inv.name))
                _logger.debug("Fiscal invoices require partner fiscal type: " + inv.name)

            if inv.l10n_latam_use_documents:
                # Because a Fiscal Sequence can be depleted while an invoice
                # is waiting to be validated, compute fiscal_sequence_id again
                # on invoice validate.
                inv._compute_l10n_do_fiscal_sequence()
                # Solo validar secuencia si no es un documento manual
                if not inv.l10n_latam_document_number and not inv.l10n_do_fiscal_sequence_id and not inv.l10n_latam_manual_document_number:
                    # Autor: Arturo Diaz Lora - 2025-11-26
                    # Mejorar mensaje de error para indicar si la secuencia está agotada
                    doc_type = inv.l10n_latam_document_type_id
                    doc_code = doc_type.doc_code_prefix if doc_type else 'N/A'
                    doc_name = doc_type.name if doc_type else 'N/A'

                    # Buscar si existe una secuencia agotada para este tipo de documento
                    depleted_sequence = inv.env["account.fiscal.sequence"].search([
                        ("company_id", "parent_of", inv.company_id.ids),
                        ("fiscal_type_id", "=", doc_type.id if doc_type else False),
                        ("state", "=", "depleted"),
                    ], limit=1)

                    if depleted_sequence:
                        # La secuencia existe pero está agotada
                        raise ValidationError(_(
                            "⚠️ SECUENCIA FISCAL AGOTADA\n\n"
                            "La secuencia fiscal para {} ({}) está AGOTADA.\n\n"
                            "• Secuencia: {}\n"
                            "• Rango: {} - {}\n"
                            "• Estado: Agotada (depleted)\n\n"
                            "Por favor, cree una nueva secuencia fiscal en:\n"
                            "Contabilidad → Configuración → Secuencias Fiscales"
                        ).format(doc_name, doc_code, depleted_sequence.name,
                                depleted_sequence.sequence_start, depleted_sequence.sequence_end))
                    else:
                        # No existe ninguna secuencia para este tipo de documento
                        raise ValidationError(_(
                            "⚠️ SECUENCIA FISCAL NO ENCONTRADA\n\n"
                            "No hay secuencia fiscal activa para {} ({}).\n\n"
                            "Verifique que exista una secuencia fiscal:\n"
                            "• Activa (state = 'active')\n"
                            "• No vencida\n"
                            "• Para el tipo de documento: {}\n\n"
                            "Configurar en: Contabilidad → Configuración → Secuencias Fiscales"
                        ).format(doc_name, doc_code, doc_code))

        _logger.debug("=== PROCESSING DOCUMENT NUMBER ASSIGNMENT IN _POST ===")
        for inv in self:
            _logger.debug(f"Processing invoice for document number assignment: {inv.name}")
            _logger.debug(f"- use_documents: {inv.l10n_latam_use_documents}")
            _logger.debug(f"- current document_number: {inv.l10n_latam_document_number}")
            _logger.debug(f"- res (post result): {res}")
            _logger.debug(f"- fiscal_sequence_id: {inv.l10n_do_fiscal_sequence_id}")
            
            if inv.l10n_latam_use_documents and not inv.l10n_latam_document_number and res and inv.l10n_do_fiscal_sequence_id:
                _logger.debug("CONDITIONS MET: Generating fiscal document number...")
                document_number = inv.l10n_do_fiscal_sequence_id.get_fiscal_number()
                _logger.debug(f"Generated document number: {document_number}")

                # MODIFICADO: Arturo Diaz Lora - 2026-03-10
                # Validación de consistencia: NCF generado debe coincidir con tipo de documento
                # Previene el bug de mezcla de secuencias (ej: B01 mostrando NCF B15)
                expected_prefix = inv.l10n_latam_document_type_id.doc_code_prefix
                if expected_prefix and not document_number.startswith(expected_prefix):
                    actual_prefix = document_number[:3] if len(document_number) >= 3 else document_number
                    _logger.error(
                        f"DISCREPANCIA NCF: Factura {inv.name} esperaba prefijo {expected_prefix} "
                        f"pero secuencia generó {actual_prefix}. Secuencia fiscal: {inv.l10n_do_fiscal_sequence_id.name}"
                    )
                    raise ValidationError(_(
                        "Error de consistencia en secuencia fiscal:\n\n"
                        "El NCF generado (%s) no corresponde al tipo de documento seleccionado (%s - %s).\n\n"
                        "Posibles causas:\n"
                        "• La secuencia fiscal '%s' está mal configurada\n"
                        "• El campo fiscal_type_id de la secuencia no coincide con el tipo de documento\n\n"
                        "Por favor verifique la configuración en:\n"
                        "Contabilidad → Configuración → Secuencias Fiscales"
                    ) % (document_number, expected_prefix, inv.l10n_latam_document_type_id.name,
                         inv.l10n_do_fiscal_sequence_id.name))

                inv.state = "draft"
                # MODIFICADO: Arturo Diaz Lora - 2026-03-22
                # Razón: name es secuencia contable (INV/BILL); referencia de pago enlaza con NCF.
                ref_name = (inv.name or "").strip()
                if ref_name:
                    pay_ref = "%s - NCF %s" % (ref_name, document_number)
                else:
                    pay_ref = "NCF %s" % document_number
                write_data = {
                    "state": "posted",
                    "l10n_latam_document_number": document_number,
                    "payment_reference": pay_ref,
                }
                
                # Solo establecer la fecha de expiración si no está ya establecida
                if not inv.l10n_do_ncf_expiration_date:
                    write_data["l10n_do_ncf_expiration_date"] = inv.l10n_do_fiscal_sequence_id.expiration_date
                
                _logger.debug(f"Writing data to invoice: {write_data}")
                inv.write(write_data)
                _logger.debug("Document number successfully assigned!")
            else:
                _logger.debug("CONDITIONS NOT MET for document number generation")

        # Validación final: asegurar que documentos fiscales usen NCF, no secuencias estándar de Odoo
        for inv in self.filtered(lambda x: x.l10n_latam_use_documents and x.l10n_latam_country_code == "DO"):
            if ((inv.move_type == "out_refund") or
                (inv.move_type == "out_invoice" and inv.debit_origin_id)):
                # Si es nota de crédito o débito de cliente, debe tener número de documento fiscal
                if not inv.l10n_latam_document_number:
                    raise ValidationError(_(
                        "Las notas de crédito y débito de cliente deben tener un número de documento fiscal asignado. "
                        "Verifique que exista una secuencia fiscal activa para el tipo de documento {}."
                    ).format(inv.l10n_latam_document_type_id.name))
                # Verificar que no esté usando secuencia estándar de Odoo
                elif inv.l10n_latam_document_number.startswith(('INV/', 'BILL/', 'RINV/', 'RBILL/')):
                    raise ValidationError(_(
                        "La nota {} está usando una secuencia estándar de Odoo ({}) en lugar de una secuencia fiscal. "
                        "Configure una secuencia fiscal apropiada en account.fiscal.sequence para el tipo de documento {}."
                    ).format(inv.move_type, inv.l10n_latam_document_number, inv.l10n_latam_document_type_id.name))

        return res

    @api.depends('l10n_latam_document_type_id', 'journal_id', 'move_type', 'company_id.country_id', 'debit_origin_id')
    def _compute_l10n_latam_manual_document_number(self):
        """ Indicates if this document type uses a sequence or if the numbering is made manually """
        for rec in self:
            if rec.journal_id and rec.journal_id.l10n_latam_use_documents:
                is_manual = rec._is_manual_document_number()
                rec.l10n_latam_manual_document_number = is_manual
                _logger.debug(f"Computed manual document number for {rec.name} ({rec.move_type}): {is_manual}")
            else:
                rec.l10n_latam_manual_document_number = False

    def _compute_l10n_latam_amount_and_taxes(self):
        recs_invoice = self.filtered(lambda x: x.is_invoice())
        for invoice in recs_invoice:
            tax_lines = invoice.line_ids.filtered('tax_line_id')
            currencies = invoice.line_ids.filtered(lambda x: x.currency_id == invoice.currency_id).mapped('currency_id')
            included_taxes = invoice.l10n_latam_document_type_id and \
                             invoice.l10n_latam_document_type_id._filter_taxes_included(tax_lines.mapped('tax_line_id'))
            if not included_taxes:
                l10n_latam_amount_untaxed = invoice.amount_untaxed
                not_included_invoice_taxes = tax_lines
            else:
                included_invoice_taxes = tax_lines.filtered(lambda x: x.tax_line_id in included_taxes)
                not_included_invoice_taxes = tax_lines - included_invoice_taxes
                if invoice.is_inbound():
                    sign = -1
                else:
                    sign = 1
                amount = 'amount_currency' if len(currencies) == 1 else 'balance'
                l10n_latam_amount_untaxed = invoice.amount_untaxed + sign * sum(included_invoice_taxes.mapped(amount))
            invoice.l10n_latam_amount_untaxed = l10n_latam_amount_untaxed
            invoice.l10n_latam_tax_ids = not_included_invoice_taxes
        remaining = self - recs_invoice
        remaining.l10n_latam_amount_untaxed = False
        remaining.l10n_latam_tax_ids = [(5, 0)]

    @api.constrains('move_type', 'l10n_latam_document_type_id')
    def _check_invoice_type_document_type(self):
        for rec in self.filtered('l10n_latam_document_type_id.internal_type'):
            internal_type = rec.l10n_latam_document_type_id.internal_type
            invoice_type = rec.move_type
            
            # Validate debit notes - identified by debit_origin_id field
            if internal_type == 'debit_note':
                # In Odoo v18, debit notes use same move_type as original invoice (out_invoice/in_invoice)
                # but are identified by having debit_origin_id set
                # Modificado 2025-11-22 por Arturo Diaz Lora - Comentada validación para permitir creación manual
                # Razón: Usuario requiere crear notas de débito manualmente sin wizard
                # El campo computed is_debit_note detecta correctamente las notas por tipo de documento
                # if not rec.debit_origin_id and rec.l10n_latam_document_type_id.code != '99':
                #     raise ValidationError(_('No puede usar un tipo de documento %s sin establecer un origen de débito. Use el asistente "Crear Nota de Débito" en su lugar.', internal_type))
                if invoice_type not in ['out_invoice', 'in_invoice'] and rec.l10n_latam_document_type_id.code != '99':
                    raise ValidationError(_('No puede usar un tipo de documento %s con un tipo de movimiento %s. Las notas de débito deben usar tipos de movimiento out_invoice o in_invoice.', internal_type, invoice_type))
            
            # Validate credit notes  
            elif internal_type == 'credit_note':
                if invoice_type not in ['out_refund', 'in_refund'] and rec.l10n_latam_document_type_id.code != '99':
                    raise ValidationError(_('No puede usar un tipo de documento %s con un tipo de movimiento %s. Las notas de crédito requieren tipos de movimiento out_refund o in_refund.', internal_type, invoice_type))
            
            # Validate invoices
            elif internal_type == 'invoice':
                if invoice_type in ['out_refund', 'in_refund'] and rec.l10n_latam_document_type_id.code != '99':
                    raise ValidationError(_('No puede usar un tipo de documento %s con un tipo de movimiento %s', internal_type, invoice_type))

    @api.constrains('amount_total', 'reversed_entry_id', 'move_type')
    def _check_credit_note_amount_not_exceed_original(self):
        """Validar que el monto de las notas de crédito no exceda el monto apropiado de la factura original"""
        for rec in self.filtered(lambda x: x.move_type in ['out_refund', 'in_refund'] and x.reversed_entry_id):
            original_invoice = rec.reversed_entry_id
            
            # Determinar si es una nota de crédito de reembolso completo o parcial
            # Las notas de crédito de reembolso completo pueden tener el monto total con impuestos
            # Las notas de crédito parciales deben respetar el monto sin impuestos
            
            # Verificar si es reembolso completo comparando montos
            credit_note_amount = abs(rec.amount_total_signed)
            original_amount_total = abs(original_invoice.amount_total_signed)
            original_amount_untaxed = abs(original_invoice.amount_untaxed_signed)
            
            # Si la nota de crédito tiene un monto muy cercano al total de la factura (con impuestos),
            # se considera reembolso completo y se valida contra el monto total
            # Si es significativamente menor, se considera parcial y se valida contra el monto sin impuestos
            
            # Tolerancia del 5% para considerar reembolso completo
            tolerance = original_amount_total * 0.05
            is_full_refund = credit_note_amount >= (original_amount_total - tolerance)
            
            if is_full_refund:
                # Para reembolso completo, validar contra el monto total con impuestos
                if credit_note_amount > original_amount_total:
                    raise ValidationError(_(
                        'El monto de la nota de crédito de reembolso completo (%(credit_amount).2f) no puede ser mayor al monto total de la factura original (%(original_amount).2f). '
                        'Por favor, ajuste el monto de la nota de crédito.',
                        credit_amount=credit_note_amount,
                        original_amount=original_amount_total
                    ))
            else:
                # Para reembolso parcial, validar contra el monto sin impuestos
                if credit_note_amount > original_amount_untaxed:
                    raise ValidationError(_(
                        'El monto de la nota de crédito parcial (%(credit_amount).2f) no puede ser mayor al monto sin impuestos de la factura original (%(original_amount).2f). '
                        'Por favor, ajuste el monto de la nota de crédito.',
                        credit_amount=credit_note_amount,
                        original_amount=original_amount_untaxed
                    ))

    @api.depends('journal_id', 'partner_id', 'company_id', 'move_type', 'debit_origin_id', 'reversed_entry_id')
    def _compute_l10n_latam_available_document_types(self):
        self.l10n_latam_available_document_type_ids = False
        for rec in self.filtered(lambda x: x.journal_id and x.journal_id.l10n_latam_use_documents and x.partner_id):
            rec.l10n_latam_available_document_type_ids = self.env['l10n_latam.document.type'].search(
                rec._get_l10n_latam_documents_domain())

    @api.depends('l10n_latam_available_document_type_ids', 'debit_origin_id', 'move_type', 'reversed_entry_id')
    def _compute_l10n_latam_document_type(self):
        
        for rec in self.filtered(lambda x: x.state == 'draft'):
            # Skip if no available document types
            if not rec.l10n_latam_available_document_type_ids:
                rec.l10n_latam_document_type_id = False
                continue
                
            document_types = rec.l10n_latam_available_document_type_ids._origin
            invoice_type = rec.move_type
            
            # Filter document types based on move_type and debit_origin_id
            if invoice_type in ['out_refund', 'in_refund']:
                # Credit note - filter for credit_note document types
                document_types = document_types.filtered(lambda x: x.internal_type == 'credit_note')
                
                # If no credit note types found, force computation
                if not document_types and rec.company_id.country_id.code == "DO":
                    if rec.company_id.l10n_do_ecf_issuer:
                        document_types = rec.l10n_latam_available_document_type_ids.filtered(
                            lambda x: getattr(x, 'l10n_do_ncf_type', '') == 'e-credit_note'
                        )
                    else:
                        document_types = rec.l10n_latam_available_document_type_ids.filtered(
                            lambda x: getattr(x, 'l10n_do_ncf_type', '') == 'credit_note'
                        )
                        
            elif rec.debit_origin_id or rec.env.context.get('internal_type') == 'debit_note':
                # Debit note - filter for debit_note document types
                document_types = document_types.filtered(lambda x: x.internal_type == 'debit_note')

                # If no debit note types found, force computation
                if not document_types and rec.company_id.country_id.code == "DO":
                    if rec.company_id.l10n_do_ecf_issuer:
                        document_types = rec.l10n_latam_available_document_type_ids.filtered(
                            lambda x: getattr(x, 'l10n_do_ncf_type', '') == 'e-debit_note'
                        )
                    else:
                        document_types = rec.l10n_latam_available_document_type_ids.filtered(
                            lambda x: getattr(x, 'l10n_do_ncf_type', '') == 'debit_note'
                        )

            elif invoice_type in ['out_invoice', 'in_invoice']:
                # Regular invoice - filter for invoice document types first
                document_types = document_types.filtered(lambda x: x.internal_type == 'invoice')

            # Set the document type - prioritize based on company ECF configuration
            if document_types:
                # For credit notes, prefer B04 (physical) or E34 (electronic)
                if invoice_type in ['out_refund', 'in_refund']:
                    if rec.company_id.l10n_do_ecf_issuer:
                        # Electronic company - prefer E34
                        preferred = document_types.filtered(lambda x: getattr(x, 'l10n_do_ncf_type', '') == 'e-credit_note')
                    else:
                        # Physical company - prefer B04
                        preferred = document_types.filtered(lambda x: getattr(x, 'l10n_do_ncf_type', '') == 'credit_note')

                    if preferred:
                        rec.l10n_latam_document_type_id = preferred[0]._origin.id if hasattr(preferred[0], '_origin') else preferred[0].id
                    else:
                        rec.l10n_latam_document_type_id = document_types[0]._origin.id if hasattr(document_types[0], '_origin') else document_types[0].id

                # For debit notes, prefer B03 (physical) or E33 (electronic)
                elif rec.debit_origin_id or rec.env.context.get('internal_type') == 'debit_note':
                    if rec.company_id.l10n_do_ecf_issuer:
                        # Electronic company - prefer E33
                        preferred = document_types.filtered(lambda x: getattr(x, 'l10n_do_ncf_type', '') == 'e-debit_note')
                    else:
                        # Physical company - prefer B03
                        preferred = document_types.filtered(lambda x: getattr(x, 'l10n_do_ncf_type', '') == 'debit_note')
                    
                    if preferred:
                        rec.l10n_latam_document_type_id = preferred[0]._origin.id if hasattr(preferred[0], '_origin') else preferred[0].id
                    else:
                        rec.l10n_latam_document_type_id = document_types[0]._origin.id if hasattr(document_types[0], '_origin') else document_types[0].id
                        
                # For regular invoices, use first available
                else:
                    rec.l10n_latam_document_type_id = document_types[0]._origin.id if hasattr(document_types[0], '_origin') else document_types[0].id
            else:
                rec.l10n_latam_document_type_id = False

    # MODIFICADO: Arturo Diaz Lora - 2026-03-19
    # Razón: Unicidad por NCF en l10n_latam_document_number (name es secuencia BILL/ no fiscal).
    @api.constrains('l10n_latam_document_number', 'partner_id', 'company_id', 'posted_before')
    def _check_unique_vendor_number(self):
        """ Validates that vendor document numbers (NCF) are unique per partner and company """
        for rec in self.filtered(
                lambda x: x.l10n_latam_document_number
                and x.is_purchase_document()
                and x.l10n_latam_use_documents):
            domain = [
                ('move_type', '=', rec.move_type),
                ('l10n_latam_document_number', '=', rec.l10n_latam_document_number),
                ('company_id', '=', rec.company_id.id),
                ('id', '!=', rec.id),
                ('commercial_partner_id', '=', rec.commercial_partner_id.id),
                ('state', '!=', 'cancel'),
            ]
            if rec.search(domain):
                raise ValidationError(_('El número de factura de proveedor debe ser único por proveedor y compañía.'))

    def unlink(self):
        """ When using documents, on vendor bills the document_number is set manually by the number given from the vendor,
        the odoo sequence is not used. In this case We allow to delete vendor bills with document_number/move_name """
        self.filtered(lambda x: x.move_type in x.get_purchase_types() and x.state in (
            'draft', 'cancel') and x.l10n_latam_use_documents).write({'name': '/'})
        return super().unlink()

    @api.constrains('l10n_latam_document_number', 'l10n_latam_document_type_id', 'move_type', 'debit_origin_id')
    def _check_ncf_format_vendor_notes(self):
        """Validar formato NCF para notas de crédito y débito de proveedor según DGII"""
        for rec in self.filtered(lambda x: x.l10n_latam_country_code == 'DO' and
                                x.l10n_latam_use_documents and
                                x.l10n_latam_manual_document_number and
                                x.l10n_latam_document_number and
                                (x.move_type == 'in_refund' or (x.move_type == 'in_invoice' and x.debit_origin_id))):

            if not rec._validate_ncf_format_vendor_notes():
                raise ValidationError(_(
                    'El número de comprobante "%s" no cumple con los requisitos de formato NCF de la DGII para notas de crédito/débito de proveedor.\n\n'
                    'NCF Físicos (serie B): B + 2 dígitos (01-17) + 9 dígitos = 11 caracteres\n'
                    'NCF Electrónicos (serie E): E + 2 dígitos (31-47) + 10 dígitos = 13 caracteres\n\n'
                    'Por favor verifique el formato según el tipo de documento fiscal.',
                    rec.l10n_latam_document_number
                ))

    def _validate_ncf_format_vendor_notes(self):
        """Validar formato NCF específicamente para notas de crédito y débito de proveedor"""
        if not self.l10n_latam_document_number or not self.l10n_latam_document_type_id:
            return True

        ncf = self.l10n_latam_document_number.strip()
        doc_type = self.l10n_latam_document_type_id

        # Para notas de crédito y débito de proveedor, validar según el tipo de documento
        if self.move_type == 'in_refund' or (self.move_type == 'in_invoice' and self.debit_origin_id):
            # Notas de crédito (B04) y débito (B03) físicas
            if doc_type.l10n_do_ncf_type in ['credit_note', 'debit_note']:
                # Formato: B + 2 dígitos (03-04) + 8 dígitos = 11 caracteres
                if len(ncf) != 11:
                    return False
                if not ncf.startswith('B'):
                    return False
                if not ncf[1:3].isdigit():
                    return False
                if not ncf[3:].isdigit():
                    return False
                # Validar tipo de código (03 para débito, 04 para crédito)
                type_code = int(ncf[1:3])
                if type_code not in [3, 4]:
                    return False

            # Notas de crédito (E34) y débito (E33) electrónicas
            elif doc_type.l10n_do_ncf_type in ['e-credit_note', 'e-debit_note']:
                # Formato: E + 2 dígitos (33-34) + 10 dígitos = 13 caracteres
                if len(ncf) != 13:
                    return False
                if not ncf.startswith('E'):
                    return False
                if not ncf[1:3].isdigit():
                    return False
                if not ncf[3:].isdigit():
                    return False
                # Validar tipo de código (33 para débito, 34 para crédito)
                type_code = int(ncf[1:3])
                if type_code not in [33, 34]:
                    return False

        return True

    @api.onchange('l10n_latam_document_number', 'l10n_latam_document_type_id', 'move_type', 'debit_origin_id')
    def _onchange_document_number_vendor_notes(self):
        """Validar formato NCF en tiempo real para notas de crédito y débito de proveedor"""
        if (self.l10n_latam_country_code == 'DO' and
            self.l10n_latam_use_documents and
            self.l10n_latam_manual_document_number and
            self.l10n_latam_document_number and
            self.l10n_latam_document_type_id and
            (self.move_type == 'in_refund' or (self.move_type == 'in_invoice' and self.debit_origin_id))):

            if not self._validate_ncf_format_vendor_notes():
                return {
                    'warning': {
                        'title': _('Formato de NCF Inválido'),
                        'message': _(
                            'El número de comprobante "%s" no cumple con los requisitos de formato NCF de la DGII para notas de crédito/débito de proveedor.\n\n'
                            'NCF Físicos (serie B): B + 2 dígitos (03-04) + 9 dígitos = 11 caracteres\n'
                            'NCF Electrónicos (serie E): E + 2 dígitos (33-34) + 10 dígitos = 13 caracteres\n\n'
                            'Por favor verifique el formato según el tipo de documento fiscal.',
                            self.l10n_latam_document_number
                        )
                    }
                }

    def _get_invoice_proforma_pdf_report_filename(self):
        """
        Sobrescribir para que facturas dominicanas NO usen el sufijo '_proforma'.
        Las facturas dominicanas ya tienen su NCF y no son proforma.
        """
        self.ensure_one()
        # Si es factura dominicana, usar nombre normal sin '_proforma'
        if self.l10n_latam_use_documents and self.company_id.country_id.code == 'DO':
            return f"{self._get_move_display_name().replace(' ', '_').replace('/', '_')}.pdf"
        # Para otras facturas, usar el comportamiento estándar
        return super()._get_invoice_proforma_pdf_report_filename()
