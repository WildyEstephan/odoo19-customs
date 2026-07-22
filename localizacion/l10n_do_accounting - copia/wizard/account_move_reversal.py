from odoo import models, api, fields, _
from odoo.exceptions import UserError, ValidationError
import logging
_logger = logging.getLogger(__name__)


class AccountMoveReversal(models.TransientModel):
    _inherit = "account.move.reversal"

    @api.model
    def _get_refund_type_selection(self):
        selection = [
            ("full_refund", _("Full Refund")),
            ("percentage", _("Percentage")),
            ("fixed_amount", _("Amount")),
        ]
        return selection

    @api.model
    def _get_default_refund_type(self):
        return "full_refund"

    @api.model
    def _get_refund_action_selection(self):
        return [
            ("draft_refund", _("Partial Refund")),
            ("apply_refund", _("Full Refund")),
        ]

    @api.model
    def _default_account(self):
        move_type = self.env.context.get("type")
        # Get the journal from the selected moves or use a default one
        move_ids = self.env["account.move"].browse(self.env.context.get("active_ids", []))
        if move_ids:
            journal = move_ids[0].journal_id
        else:
            # Fallback to a default journal based on move type
            journal_types = []
            if move_type in ("out_invoice", "out_refund"):
                journal_types = ['sale']
            elif move_type in ("in_invoice", "in_refund"):
                journal_types = ['purchase']
            else:
                journal_types = ['sale', 'purchase']
            
            journal = self.env['account.journal'].search([
                ('type', 'in', journal_types),
                ('company_id', '=', self.env.company.id),
            ], limit=1)
        
        if not journal or not journal.default_account_id:
            return False
            
        return journal.default_account_id.id

    l10n_latam_use_documents = fields.Boolean(compute='_compute_documents_info')
    l10n_latam_document_type_id = fields.Many2one('l10n_latam.document.type', 'Document Type', ondelete='cascade',
                                                  domain="[('id', 'in', l10n_latam_available_document_type_ids)]",
                                                  compute='_compute_document_type', readonly=False, store=True)
    l10n_latam_available_document_type_ids = fields.Many2many('l10n_latam.document.type',
                                                              compute='_compute_documents_info')
    l10n_latam_document_number = fields.Char(string='Document Number')
    l10n_latam_manual_document_number = fields.Boolean(compute='_compute_l10n_latam_manual_document_number',
                                                       string='Manual Number')
    
    show_vendor_fields = fields.Boolean(
        string="Show Vendor Fields",
        compute="_compute_show_vendor_fields",
        help="Determines if vendor-specific fields should be shown"
    )
    l10n_do_origin_ncf = fields.Char(
        string="NCF modificado",
        help="NCF de la factura original que se modifica",
    )
    l10n_do_ncf_expiration_date = fields.Date(
        string="Válida hasta",
        help="Fecha de vencimiento del NCF",
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    move_type = fields.Selection(
        related='move_ids.move_type',
        string='Move Type',
        readonly=True,
    )
    l10n_latam_country_code = fields.Char(
        string="Latam Country Code",
        related="company_id.country_code",
        help="Technical field used to hide/show fields regarding the localization",
    )
    refund_type = fields.Selection(
        selection=_get_refund_type_selection,
        default=_get_default_refund_type,
    )
    refund_action = fields.Selection(
        selection=_get_refund_action_selection,
        default="draft_refund",
        string="Refund Action",
    )
    percentage = fields.Float()
    amount = fields.Float()
    account_id = fields.Many2one(
        "account.account",
        string="Account",
        domain=[("deprecated", "=", False)],
        default=_default_account,
    )
    l10n_do_ecf_modification_code = fields.Selection(
        selection=lambda self: self.env[
            "account.move"
        ]._get_l10n_do_ecf_modification_code(),
        string="e-CF Modification Code",
        copy=False,
        default="01",  # 01 - Anulación total
    )
    is_ecf_invoice = fields.Boolean(
        string="Is Electronic Invoice",
    )
    copy_lines = fields.Boolean(
        string="Copy Lines", 
        default=True, 
        store=False,
        compute='_compute_copy_lines',
        readonly=False,
        help="Whether to copy invoice lines to the credit note"
    )
    
    custom_description = fields.Char(
        string="Custom Description",
        help="Custom description to use when not copying product lines"
    )

    @api.depends('refund_type')
    def _compute_copy_lines(self):
        """Compute copy_lines based on refund type"""
        for record in self:
            if record.refund_type == 'full_refund':
                # For full refunds, always copy lines since we're refunding everything
                record.copy_lines = True
            else:
                # For partial refunds, default to True but allow user to change
                record.copy_lines = True

    @api.depends('l10n_latam_document_type_id', 'move_ids.move_type')
    def _compute_l10n_latam_manual_document_number(self):
        self.l10n_latam_manual_document_number = False
        for rec in self.filtered('move_ids'):
            move = rec.move_ids[0]
            if move.journal_id and move.journal_id.l10n_latam_use_documents:
                # Para notas de crédito de proveedor, siempre permitir números manuales
                if move.move_type == "in_invoice":  # Original invoice is vendor invoice
                    rec.l10n_latam_manual_document_number = True
                else:
                    rec.l10n_latam_manual_document_number = move._is_manual_document_number()

    @api.depends('move_ids', 'l10n_latam_country_code')
    def _compute_show_vendor_fields(self):
        """Determina si se deben mostrar campos específicos de proveedor"""
        _logger.info("=== COMPUTING SHOW VENDOR FIELDS ===")
        for rec in self:
            rec.show_vendor_fields = False
            
            # Solo mostrar para República Dominicana con facturas de proveedor
            if rec.l10n_latam_country_code == 'DO' and rec.move_ids:
                move = rec.move_ids[0]
                _logger.info(f"Checking move: {move.name} ({move.move_type})")
                
                # Solo mostrar para facturas de proveedor (in_invoice)
                if move.move_type == "in_invoice":
                    rec.show_vendor_fields = True
                    _logger.info(f"Show vendor fields = True")
                else:
                    _logger.info(f"Not vendor invoice -> show_vendor_fields = False")
            else:
                _logger.info(f"Not DO or no move_ids -> show_vendor_fields = False")

    @api.model
    def default_get(self, fields_list):
        _logger.info("=== DEFAULT_GET FOR CREDIT NOTE WIZARD ===")
        _logger.info(f"Requested fields: {fields_list}")
        _logger.info(f"Context: {self.env.context}")
        
        res = super(AccountMoveReversal, self).default_get(fields_list)
        _logger.info(f"Super default_get result: {res}")
        
        move_ids = (
            self.env["account.move"].browse(self.env.context["active_ids"])
            if self.env.context.get("active_model") == "account.move"
            else self.env["account.move"]
        )
        _logger.info(f"Active move IDs: {move_ids.ids}")
        move_ids_use_document = move_ids.filtered(
            lambda move: move.l10n_latam_use_documents
            and move.company_id.country_code == "DO"
        )

        if len(move_ids_use_document) > 1:
            raise UserError(
                _(
                    "You cannot create Credit Notes from multiple "
                    "documents at a time."
                )
            )
        if move_ids_use_document:
            res["is_ecf_invoice"] = move_ids_use_document[0].is_ecf_invoice

        res["l10n_do_ecf_modification_code"] = "01"

        # Auto-llenar el campo l10n_do_origin_ncf con el NCF de la factura original
        if move_ids and move_ids[0].l10n_latam_document_number:
            res["l10n_do_origin_ncf"] = move_ids[0].l10n_latam_document_number

        # Auto-llenar el campo l10n_do_ncf_expiration_date de la factura original
        if move_ids and move_ids[0].l10n_do_ncf_expiration_date:
            res["l10n_do_ncf_expiration_date"] = move_ids[0].l10n_do_ncf_expiration_date
        
        # Set default document type for Dominican Republic credit notes
        if move_ids_use_document and move_ids_use_document[0].company_id.country_id.code == "DO":
            move_id = move_ids_use_document[0]
            # Map to correct credit note move type
            refund_move_type = self._reverse_type_map(move_id.move_type)
            
            refund = (
                self.env["account.move"]
                .new(
                    {
                        "partner_id": move_id.partner_id.id,
                        "move_type": refund_move_type,
                        "journal_id": move_id.journal_id.id,
                        "reversed_entry_id": move_id.id,  # This is crucial for credit note identification
                    }
                )
            )
            
            try:
                domain_ids = (
                    self.env["l10n_latam.document.type"]
                    .search(refund._get_l10n_latam_documents_domain())
                )
                # Establecer los tipos de documento disponibles
                res["l10n_latam_available_document_type_ids"] = [(6, 0, domain_ids.ids)]

                # MODIFICADO: Arturo Diaz Lora - 2026-03-27
                # Para facturas de proveedor, siempre mostrar tipos electrónicos como opción
                # porque el proveedor puede ser emisor electrónico aunque la compañía no lo sea
                is_purchase = move_id.move_type in ('in_invoice', 'in_refund')
                use_electronic_types = is_purchase or move_id.company_id.l10n_do_ecf_issuer

                # Filtrar por comprobante B04 (Nota de Crédito) o E34 (electrónica)
                if use_electronic_types:
                    credit_note_type = domain_ids.filtered(lambda d: d.l10n_do_ncf_type == "e-credit_note")
                else:
                    credit_note_type = domain_ids.filtered(lambda d: d.l10n_do_ncf_type == "credit_note")
                
                # Fallback to any credit note type
                if not credit_note_type:
                    credit_note_type = domain_ids.filtered(lambda d: d.internal_type == "credit_note")
                    
                if credit_note_type:
                    res["l10n_latam_document_type_id"] = credit_note_type[0]._origin.id if hasattr(credit_note_type[0], '_origin') else credit_note_type[0].id
                elif domain_ids:
                    res["l10n_latam_document_type_id"] = domain_ids[0]._origin.id if hasattr(domain_ids[0], '_origin') else domain_ids[0].id
                    
            except Exception as e:
                # If there's an error getting document types, try to get them directly
                _logger.warning(f"Error computing document types in credit note default_get: {e}")
                
                # Fallback: search directly for credit note document types
                credit_types = self.env['l10n_latam.document.type'].search([
                    ('internal_type', '=', 'credit_note')
                ])
                
                # Establecer los tipos de documento disponibles como fallback
                res["l10n_latam_available_document_type_ids"] = [(6, 0, credit_types.ids)]

                # MODIFICADO: Arturo Diaz Lora - 2026-03-27
                # Para facturas de proveedor, siempre mostrar tipos electrónicos
                is_purchase = move_id.move_type in ('in_invoice', 'in_refund')
                use_electronic_types = is_purchase or move_id.company_id.l10n_do_ecf_issuer

                if use_electronic_types:
                    b04 = credit_types.filtered(lambda d: d.l10n_do_ncf_type == "e-credit_note")
                else:
                    b04 = credit_types.filtered(lambda d: d.l10n_do_ncf_type == "credit_note")
                
                if b04:
                    res["l10n_latam_document_type_id"] = b04[0]._origin.id if hasattr(b04[0], '_origin') else b04[0].id
                elif credit_types:
                    res["l10n_latam_document_type_id"] = credit_types[0]._origin.id if hasattr(credit_types[0], '_origin') else credit_types[0].id
        
        # Agregar campo l10n_latam_country_code para compatibilidad con vistas
        if move_ids and move_ids[0].company_id.country_id.code == "DO":
            res['l10n_latam_country_code'] = 'DO'
            _logger.info("Set l10n_latam_country_code for credit note wizard visibility")
            
            # Compute show_vendor_fields for immediate availability
            if move_ids[0].move_type == "in_invoice":
                res['show_vendor_fields'] = True
                _logger.info("Set show_vendor_fields = True for vendor invoice")
            else:
                res['show_vendor_fields'] = False
                _logger.info("Set show_vendor_fields = False for non-vendor invoice")
        else:
            res['show_vendor_fields'] = False
        
        return res

    @api.onchange("refund_type")
    def onchange_refund_type(self):
        # In Odoo 18, refund_method field doesn't exist
        # The refund behavior is handled in the reverse_moves method
        pass

    @api.onchange("l10n_latam_document_number", "l10n_latam_document_type_id")
    def _onchange_document_number(self):
        """Validar formato NCF en tiempo real para notas de crédito de proveedor"""
        if (self.l10n_latam_country_code == 'DO' and
            self.l10n_latam_use_documents and
            self.l10n_latam_manual_document_number and
            self.l10n_latam_document_number and
            self.l10n_latam_document_type_id and
            self.move_ids and
            self.move_ids[0].move_type == "in_invoice"):  # Original invoice is vendor invoice

            if not self._validate_ncf_format_vendor_notes():
                return {
                    'warning': {
                        'title': _('Formato de NCF Inválido'),
                        'message': _(
                            'El número de comprobante "%s" no cumple con los requisitos de formato NCF de la DGII para notas de crédito de proveedor.\n\n'
                            'NCF Físicos (serie B): B + 2 dígitos (04) + 9 dígitos = 11 caracteres\n'
                            'NCF Electrónicos (serie E): E + 2 dígitos (34) + 10 dígitos = 13 caracteres\n\n'
                            'Por favor verifique el formato según el tipo de documento fiscal.',
                            self.l10n_latam_document_number
                        )
                    }
                }

    def _validate_ncf_format_vendor_notes(self):
        """Validar formato NCF específicamente para notas de crédito de proveedor"""
        if not self.l10n_latam_document_number or not self.l10n_latam_document_type_id:
            return True

        ncf = self.l10n_latam_document_number.strip()
        doc_type = self.l10n_latam_document_type_id

        # Para notas de crédito de proveedor, validar según el tipo de documento
        # Notas de crédito (B04) físicas
        if doc_type.l10n_do_ncf_type in ['credit_note']:
            # Formato: B + 2 dígitos (04) + 8 dígitos = 11 caracteres
            if len(ncf) != 11:
                return False
            if not ncf.startswith('B'):
                return False
            if not ncf[1:3].isdigit():
                return False
            if not ncf[3:].isdigit():
                return False
            # Validar tipo de código (04 para crédito)
            type_code = int(ncf[1:3])
            if type_code != 4:
                return False

        # Notas de crédito (E34) electrónicas
        elif doc_type.l10n_do_ncf_type in ['e-credit_note']:
            # Formato: E + 2 dígitos (34) + 10 dígitos = 13 caracteres
            if len(ncf) != 13:
                return False
            if not ncf.startswith('E'):
                return False
            if not ncf[1:3].isdigit():
                return False
            if not ncf[3:].isdigit():
                return False
            # Validar tipo de código (34 para crédito)
            type_code = int(ncf[1:3])
            if type_code != 34:
                return False

        return True

    @api.onchange("amount", "percentage", "refund_type")
    def _onchange_refund_amount(self):
        """Validar que el monto de la nota de crédito no exceda el monto de la factura original (sin impuestos)"""
        if not self.move_ids:
            return
            
        move = self.move_ids[0]
        # Usar amount_untaxed_signed en lugar de amount_total_signed para comparar contra el monto sin impuestos
        original_amount_untaxed = abs(move.amount_untaxed_signed)
        
        if self.refund_type == 'percentage' and self.percentage:
            if self.percentage > 100:
                return {
                    'warning': {
                        'title': _('Porcentaje inválido'),
                        'message': _('El porcentaje no puede ser mayor al 100%.')
                    }
                }
            refund_amount = move.amount_untaxed * (self.percentage / 100)
            if refund_amount > original_amount_untaxed:
                return {
                    'warning': {
                        'title': _('Monto excesivo'),
                        'message': _(
                            'El monto calculado de la nota de crédito (%(credit_amount).2f) excede el monto sin impuestos de la factura original (%(original_amount).2f). '
                            'Por favor, ajuste el porcentaje.',
                            credit_amount=refund_amount,
                            original_amount=original_amount_untaxed
                        )
                    }
                }
        elif self.refund_type == 'fixed_amount' and self.amount:
            if self.amount > original_amount_untaxed:
                return {
                    'warning': {
                        'title': _('Monto excesivo'),
                        'message': _(
                            'El monto de la nota de crédito (%(credit_amount).2f) excede el monto sin impuestos de la factura original (%(original_amount).2f). '
                            'Por favor, ajuste el monto.',
                            credit_amount=self.amount,
                            original_amount=original_amount_untaxed
                        )
                    }
                }

    @api.model
    def _reverse_type_map(self, move_type):
        match = {
            'entry': 'entry',
            'out_invoice': 'out_refund',
            'in_invoice': 'in_refund',
            'in_refund': 'in_invoice',
            'out_receipt': 'in_receipt',
            'in_receipt': 'out_receipt'}
        return match.get(move_type)

    @api.depends('move_ids')
    def _compute_documents_info(self):
        self.l10n_latam_available_document_type_ids = False
        self.l10n_latam_use_documents = False
        for record in self:
            if len(record.move_ids) > 1:
                move_ids_use_document = record.move_ids._origin.filtered(lambda move: move.l10n_latam_use_documents)
                if move_ids_use_document:
                    raise UserError(
                        _('You can only reverse documents with legal invoicing documents from Latin America one at a time.\nProblematic documents: %s') % ", ".join(
                            move_ids_use_document.mapped('name')))
            else:
                if record.move_ids and record.move_ids.journal_id:
                    record.l10n_latam_use_documents = record.move_ids.journal_id.l10n_latam_use_documents

            if record.l10n_latam_use_documents:
                original_move = record.move_ids[0]
                refund_move_type = record._reverse_type_map(original_move.move_type)

                refund = record.env['account.move'].new({
                    'move_type': refund_move_type,
                    'journal_id': original_move.journal_id.id,
                    'partner_id': original_move.partner_id.id,
                    'company_id': original_move.company_id.id,
                    'reversed_entry_id': original_move.id,
                })

                refund._compute_l10n_latam_available_document_types()
                available_types = refund.l10n_latam_available_document_type_ids

                if not available_types:
                    domain = refund._get_l10n_latam_documents_domain()
                    available_types = record.env['l10n_latam.document.type'].search(domain)

                record.l10n_latam_available_document_type_ids = available_types

    @api.depends('l10n_latam_available_document_type_ids')
    def _compute_document_type(self):
        for record in self:
            if not record.l10n_latam_document_type_id or \
                    record.l10n_latam_document_type_id not in record.l10n_latam_available_document_type_ids:
                available_types = record.l10n_latam_available_document_type_ids._origin
                if available_types and record.move_ids:
                    original_move = record.move_ids[0]
                    # MODIFICADO: Arturo Diaz Lora - 2026-03-27
                    # Para facturas de proveedor, siempre mostrar tipos electrónicos
                    is_purchase = original_move.move_type in ('in_invoice', 'in_refund')
                    use_electronic_types = is_purchase or original_move.company_id.l10n_do_ecf_issuer

                    # Filter for credit note document types (B04 or E34)
                    if use_electronic_types:
                        credit_note_type = available_types.filtered(lambda d: d.l10n_do_ncf_type == "e-credit_note")
                    else:
                        credit_note_type = available_types.filtered(lambda d: d.l10n_do_ncf_type == "credit_note")

                    if not credit_note_type:
                        credit_note_type = available_types.filtered(lambda d: d.internal_type == "credit_note")

                    record.l10n_latam_document_type_id = credit_note_type[0] if credit_note_type else available_types[0]
                else:
                    record.l10n_latam_document_type_id = False

    def _prepare_default_reversal(self, move):
        """Prepare default values for credit note reversal"""
        res = super()._prepare_default_reversal(move)
        
        # Ensure auto_post is set correctly
        if 'auto_post' not in res:
            reverse_date = self.date
            res['auto_post'] = 'at_date' if reverse_date > fields.Date.context_today(self) else 'no'
        
        # Always include partner_id to ensure it's copied to credit notes
        res['partner_id'] = move.partner_id.id
        
        # Include Dominican fiscal fields when creating credit notes
        if move.company_id.country_id.code == "DO" and move.l10n_latam_use_documents:
            # Asegurar que se tenga un tipo de documento válido
            document_type_id = False
            if self.l10n_latam_document_type_id:
                document_type_id = self.l10n_latam_document_type_id._origin.id if hasattr(self.l10n_latam_document_type_id, '_origin') else self.l10n_latam_document_type_id.id
            
            # Si no hay tipo de documento, buscar el tipo de documento de crédito por defecto
            if not document_type_id:
                # MODIFICADO: Arturo Diaz Lora - 2026-03-27
                # Para facturas de proveedor, siempre usar tipos electrónicos
                is_purchase = move.move_type in ('in_invoice', 'in_refund')
                use_electronic_types = is_purchase or move.company_id.l10n_do_ecf_issuer

                if use_electronic_types:
                    credit_type = self.env['l10n_latam.document.type'].search([
                        ('l10n_do_ncf_type', '=', 'e-credit_note'),
                        ('country_id.code', '=', 'DO')
                    ], limit=1)
                else:
                    credit_type = self.env['l10n_latam.document.type'].search([
                        ('l10n_do_ncf_type', '=', 'credit_note'),
                        ('country_id.code', '=', 'DO')
                    ], limit=1)
                
                if credit_type:
                    document_type_id = credit_type.id
                    _logger.info(f"Usando tipo de documento de crédito por defecto en _prepare_default_reversal: {credit_type.name} (ID: {credit_type.id})")
            
            res.update({
                'l10n_latam_document_type_id': document_type_id,  # ¡CRÍTICO! Asegurar que haya un valor válido
                'l10n_do_origin_ncf': move.l10n_latam_document_number,
                'l10n_do_income_type': move.l10n_do_income_type,
                'l10n_do_expense_type': move.l10n_do_expense_type,
                'l10n_do_ecf_modification_code': self.l10n_do_ecf_modification_code,
                'invoice_origin': move.name,
                # Copy fiscal sequence expiration date to show "Válida hasta"  
                'l10n_do_ncf_expiration_date': move.l10n_do_ncf_expiration_date,
            })
        
        return res

    def reverse_moves(self, is_modify=False):
        # Validar formato NCF antes de crear la nota de crédito
        if (self.l10n_latam_country_code == 'DO' and
            self.l10n_latam_use_documents and
            self.l10n_latam_manual_document_number and
            self.l10n_latam_document_number and
            self.l10n_latam_document_type_id and
            self.move_ids and
            self.move_ids[0].move_type == "in_invoice"):  # Original invoice is vendor invoice
            
            if not self._validate_ncf_format_vendor_notes():
                raise ValidationError(_(
                    'El número de comprobante "%s" no cumple con los requisitos de formato NCF de la DGII para notas de crédito de proveedor.\n\n'
                    'NCF Físicos (serie B): B + 2 dígitos (04) + 9 dígitos = 11 caracteres\n'
                    'NCF Electrónicos (serie E): E + 2 dígitos (34) + 10 dígitos = 13 caracteres\n\n'
                    'Por favor verifique el formato según el tipo de documento fiscal.',
                    self.l10n_latam_document_number
                ))
        
        # Handle partial refunds with percentage or fixed amount
        if self.refund_type != "full_refund":
            return self._create_partial_refund()
        
        # Validar que las notas de crédito completas no excedan el monto de la factura original
        for move in self.move_ids:
            if move.state != 'posted':
                raise UserError(_('You can only create credit notes from posted invoices.'))
            
            # Para notas de crédito completas, verificar que no haya notas de crédito previas que excedan el monto
            existing_credit_notes = move.reversal_move_ids.filtered(
                lambda x: x.move_type in ['out_refund', 'in_refund'] and x.state != 'cancel'
            )
            
            if existing_credit_notes:
                total_credit_amount = sum(abs(cn.amount_total_signed) for cn in existing_credit_notes)
                # Para notas de crédito completas, comparar contra el monto total con impuestos
                # ya que se está reembolsando todo el documento
                original_amount = abs(move.amount_total_signed)
                
                if total_credit_amount >= original_amount:
                    raise UserError(_(
                        'Ya existe una nota de crédito por el monto total de la factura (%(original_amount).2f). '
                        'No se puede crear otra nota de crédito completa.',
                        original_amount=original_amount
                    ))
        
        # Handle full refunds with automatic reconciliation
        # For full refunds, we need to ensure the credit note is properly linked and reconciled
        res = super().reverse_moves(is_modify=is_modify)
        
        # Ensure fiscal fields are set for Dominican credit notes
        if isinstance(res, dict) and res.get('res_id'):
            credit_move = self.env['account.move'].browse(res['res_id'])
            original_move = self.move_ids[0]
            
            if original_move.company_id.country_id.code == "DO" and original_move.l10n_latam_use_documents:
                # Configurar campos fiscales para la nota de crédito
                # Asegurar que se tenga un tipo de documento válido
                document_type_id = False
                if self.l10n_latam_document_type_id:
                    document_type_id = self.l10n_latam_document_type_id._origin.id if hasattr(self.l10n_latam_document_type_id, '_origin') else self.l10n_latam_document_type_id.id
                
                # Si no hay tipo de documento, usar el tipo de documento de crédito por defecto
                if not document_type_id:
                    # MODIFICADO: Arturo Diaz Lora - 2026-03-27
                    # Para facturas de proveedor, siempre usar tipos electrónicos
                    is_purchase = original_move.move_type in ('in_invoice', 'in_refund')
                    use_electronic_types = is_purchase or original_move.company_id.l10n_do_ecf_issuer

                    if use_electronic_types:
                        credit_type = self.env['l10n_latam.document.type'].search([
                            ('l10n_do_ncf_type', '=', 'e-credit_note'),
                            ('country_id.code', '=', 'DO')
                        ], limit=1)
                    else:
                        credit_type = self.env['l10n_latam.document.type'].search([
                            ('l10n_do_ncf_type', '=', 'credit_note'),
                            ('country_id.code', '=', 'DO')
                        ], limit=1)

                    if credit_type:
                        document_type_id = credit_type.id
                        _logger.info(f"Usando tipo de documento de crédito por defecto: {credit_type.name} (ID: {credit_type.id})")
                
                fiscal_fields = {
                    'l10n_latam_document_type_id': document_type_id,  # ¡CRÍTICO! Asegurar que haya un valor válido
                    'l10n_do_origin_ncf': original_move.l10n_latam_document_number,
                    'l10n_do_income_type': original_move.l10n_do_income_type,
                    'l10n_do_expense_type': original_move.l10n_do_expense_type,
                    'l10n_do_ecf_modification_code': self.l10n_do_ecf_modification_code,
                    'l10n_do_ncf_expiration_date': self.l10n_do_ncf_expiration_date,
                }
                
                # Configurar el número de documento
                # Para notas de crédito de cliente, NO usar número manual ni copiar de la factura original
                # El sistema debe generar automáticamente un número de secuencia fiscal
                if original_move.move_type == "out_invoice":
                    # Nota de crédito de cliente - NO establecer número de documento manualmente
                    # Se generará automáticamente desde la secuencia fiscal durante _post()
                    pass
                else:
                    # Para notas de crédito de proveedor, permitir número manual
                    if self.l10n_latam_document_number:
                        # Si se proporcionó manualmente en el wizard, usar ese valor
                        fiscal_fields['l10n_latam_document_number'] = self.l10n_latam_document_number
                    elif original_move.l10n_latam_document_number:
                        # Si no se proporcionó manualmente pero la factura original tiene número, usar ese
                        fiscal_fields['l10n_latam_document_number'] = original_move.l10n_latam_document_number
                
                # Forzar la configuración de manual_document_number para notas de crédito de proveedor
                if original_move.move_type == "in_invoice":
                    fiscal_fields['l10n_latam_manual_document_number'] = True
                
                # Escribir todos los campos fiscales en una sola operación
                credit_move.write(fiscal_fields)
                
                # Log para verificar que los campos se guardaron correctamente
                _logger.info(f"=== CAMPOS FISCALES GUARDADOS EN NOTA DE CRÉDITO ===")
                _logger.info(f"Credit move ID: {credit_move.id}")
                _logger.info(f"l10n_latam_document_number: {credit_move.l10n_latam_document_number}")
                _logger.info(f"l10n_do_ncf_expiration_date: {credit_move.l10n_do_ncf_expiration_date}")
                _logger.info(f"l10n_do_origin_ncf: {credit_move.l10n_do_origin_ncf}")
                _logger.info(f"l10n_do_ecf_modification_code: {credit_move.l10n_do_ecf_modification_code}")
                _logger.info(f"l10n_latam_manual_document_number: {credit_move.l10n_latam_manual_document_number}")
                
                # Log the creation of the credit note
                credit_move.message_post(
                    body=_('Nota de crédito creada desde la factura %s con todos los campos fiscales configurados.') % (
                        original_move.name
                    )
                )
        
        # For full refunds, always validate and reconcile automatically
        # This ensures that full refunds are immediately applied and reconciled
        if isinstance(res, dict) and res.get('res_id'):
            refund = self.env['account.move'].browse(res['res_id'])
            if refund.state == 'draft':
                refund.action_post()
                
                # After posting, reconcile the full credit note with the original invoice
                # to effectively "pay" the invoice with the credit note
                self._reconcile_full_credit_note(refund, original_move)
                
                # Log the automatic posting and reconciliation
                refund.message_post(
                    body=_('Nota de crédito de reembolso completo validada, publicada y reconciliada automáticamente.')
                )
        
        # NOTA: Para notas de crédito de cliente, el número de documento se genera
        # automáticamente en el método _post() cuando se confirma la factura,
        # NO al crearla. Esto es correcto según los requerimientos del usuario.
        if isinstance(res, dict) and res.get('res_id'):
            credit_move = self.env['account.move'].browse(res['res_id'])
            _logger.info(f"=== NOTA DE CRÉDITO CREADA - NCF SE GENERARÁ AL CONFIRMAR ===")
            _logger.info(f"Move: {credit_move.name} (ID: {credit_move.id})")
            _logger.info(f"Current document number: {credit_move.l10n_latam_document_number}")
            _logger.info(f"El NCF se generará automáticamente cuando se confirme la factura (método _post)")
        
        return res

    def _reconcile_partial_credit_note(self, credit_note, original_invoice, credit_amount):
        """
        Reconcile partial credit note with original invoice to affect the invoice's residual amount.
        This ensures that the credit note properly reduces the amount owed on the original invoice.
        """
        try:
            # Get the receivable/payable lines from both moves
            if original_invoice.move_type == 'out_invoice':
                # Customer invoice - reconcile receivable lines
                original_lines = original_invoice.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
                )
                credit_lines = credit_note.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
                )
            else:
                # Vendor bill - reconcile payable lines
                original_lines = original_invoice.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'liability_payable' and not l.reconciled
                )
                credit_lines = credit_note.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'liability_payable' and not l.reconciled
                )
            
            # If we have lines to reconcile, create a reconciliation
            if original_lines and credit_lines:
                # Create a partial reconciliation
                (original_lines + credit_lines).reconcile()
                
                # Log the reconciliation
                credit_note.message_post(
                    body=_('Nota de crédito reconciliada automáticamente con la factura original %s por un monto de %s') % (
                        original_invoice.name, 
                        self.env.company.currency_id.format(credit_amount)
                    )
                )
                original_invoice.message_post(
                    body=_('Factura afectada por nota de crédito %s por un monto de %s') % (
                        credit_note.name, 
                        self.env.company.currency_id.format(credit_amount)
                    )
                )
                
                # Update invoice state if fully paid
                self._update_invoice_state_after_reconciliation(original_invoice)
                
        except Exception as e:
            # Log any reconciliation errors but don't fail the process
            _logger.warning('Error reconciling partial credit note %s with invoice %s: %s', 
                          credit_note.name, original_invoice.name, str(e))

    def _reconcile_full_credit_note(self, credit_note, original_invoice):
        """
        Reconcile full credit note with original invoice to effectively "pay" the invoice.
        This ensures that the credit note completely settles the original invoice.
        """
        try:
            # Get the receivable/payable lines from both moves
            if original_invoice.move_type == 'out_invoice':
                # Customer invoice - reconcile receivable lines
                original_lines = original_invoice.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
                )
                credit_lines = credit_note.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
                )
            else:
                # Vendor bill - reconcile payable lines
                original_lines = original_invoice.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'liability_payable' and not l.reconciled
                )
                credit_lines = credit_note.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'liability_payable' and not l.reconciled
                )
            
            # If we have lines to reconcile, create a reconciliation
            if original_lines and credit_lines:
                # Create a full reconciliation
                (original_lines + credit_lines).reconcile()
                
                # Log the reconciliation
                credit_note.message_post(
                    body=_('Nota de crédito de reembolso completo reconciliada automáticamente con la factura original %s. La factura ha sido pagada completamente.') % (
                        original_invoice.name
                    )
                )
                original_invoice.message_post(
                    body=_('Factura pagada completamente por nota de crédito %s. La factura ha sido saldada.') % (
                        credit_note.name
                    )
                )
                
                # Update invoice state to reflect it's fully paid
                self._update_invoice_state_after_full_reconciliation(original_invoice)
                
        except Exception as e:
            # Log any reconciliation errors but don't fail the process
            _logger.warning('Error reconciling full credit note %s with invoice %s: %s', 
                          credit_note.name, original_invoice.name, str(e))

    def _update_invoice_state_after_reconciliation(self, invoice):
        """
        Update invoice state after reconciliation to reflect if it's fully paid.
        This ensures the invoice shows the correct payment status.
        """
        try:
            # Refresh the invoice to get updated amounts
            invoice.invalidate_recordset(['amount_residual', 'payment_state'])
            invoice._compute_amount()
            
            # Check if invoice is fully paid after reconciliation
            if invoice.currency_id.is_zero(invoice.amount_residual):
                invoice.message_post(
                    body=_('Factura marcada como pagada automáticamente después de la reconciliación con la nota de crédito.')
                )
                
        except Exception as e:
            # Log any errors but don't fail the process
            _logger.warning('Error updating invoice state after reconciliation: %s', str(e))

    def _update_invoice_state_after_full_reconciliation(self, invoice):
        """
        Update invoice state after full reconciliation to reflect it's completely paid.
        This ensures the invoice shows the correct payment status for full refunds.
        """
        try:
            # Refresh the invoice to get updated amounts
            invoice.invalidate_recordset(['amount_residual', 'payment_state'])
            invoice._compute_amount()
            
            # For full refunds, the invoice should be completely paid
            if invoice.currency_id.is_zero(invoice.amount_residual):
                invoice.message_post(
                    body=_('Factura marcada como completamente pagada por la nota de crédito de reembolso completo.')
                )
                
                # Force update payment state if needed
                if hasattr(invoice, 'payment_state') and invoice.payment_state != 'paid':
                    invoice.payment_state = 'paid'
                    
        except Exception as e:
            # Log any errors but don't fail the process
            _logger.warning('Error updating invoice state after full reconciliation: %s', str(e))

    def _create_partial_refund(self):
        """ Create a partial credit note based on percentage or fixed amount """
        # Validar formato NCF antes de crear la nota de crédito parcial
        if (self.l10n_latam_country_code == 'DO' and
            self.l10n_latam_use_documents and
            self.l10n_latam_manual_document_number and
            self.l10n_latam_document_number and
            self.l10n_latam_document_type_id and
            self.move_ids and
            self.move_ids[0].move_type == "in_invoice"):  # Original invoice is vendor invoice
            
            if not self._validate_ncf_format_vendor_notes():
                raise ValidationError(_(
                    'El número de comprobante "%s" no cumple con los requisitos de formato NCF de la DGII para notas de crédito de proveedor.\n\n'
                    'NCF Físicos (serie B): B + 2 dígitos (04) + 9 dígitos = 11 caracteres\n'
                    'NCF Electrónicos (serie E): E + 2 dígitos (34) + 10 dígitos = 13 caracteres\n\n'
                    'Por favor verifique el formato según el tipo de documento fiscal.',
                    self.l10n_latam_document_number
                ))
        
        moves = self.move_ids
        refund_moves = self.env['account.move']
        
        for move in moves:
            if move.state != 'posted':
                raise UserError(_('You can only create credit notes from posted invoices.'))
                
            # Calculate refund amount
            if self.refund_type == 'percentage':
                refund_amount = move.amount_untaxed * (self.percentage / 100)
            else:  # fixed_amount
                refund_amount = self.amount
            
            # Validar que el monto de la nota de crédito no exceda el monto de la factura original (sin impuestos)
            original_amount_untaxed = abs(move.amount_untaxed_signed)
            if refund_amount > original_amount_untaxed:
                raise UserError(_(
                    'El monto de la nota de crédito (%(credit_amount).2f) no puede ser mayor al monto sin impuestos de la factura original (%(original_amount).2f). '
                    'Por favor, ajuste el monto de la nota de crédito.',
                    credit_amount=refund_amount,
                    original_amount=original_amount_untaxed
                ))
            
            # Validar que no exceda el monto residual de la factura (considerando notas de crédito previas)
            existing_credit_notes = move.reversal_move_ids.filtered(
                lambda x: x.move_type in ['out_refund', 'in_refund'] and x.state != 'cancel'
            )
            if existing_credit_notes:
                total_credit_amount = sum(abs(cn.amount_total_signed) for cn in existing_credit_notes)
                available_amount = original_amount_untaxed - total_credit_amount
                if refund_amount > available_amount:
                    raise UserError(_(
                        'El monto de la nota de crédito (%(credit_amount).2f) excede el monto disponible (%(available_amount).2f) '
                        'considerando las notas de crédito previas. Por favor, ajuste el monto.',
                        credit_amount=refund_amount,
                        available_amount=available_amount
                    ))
                
            # Create new refund move
            refund_values = self._prepare_default_reversal(move)
            refund_values.update({
                'move_type': 'out_refund' if move.move_type == 'out_invoice' else 'in_refund',
                'ref': move.name,
                'invoice_origin': move.name,
                'reversed_entry_id': move.id,  # Ensure proper link to original invoice
            })
            
            # Copy lines from original invoice proportionally or create single line
            if self.copy_lines:
                # Copy all lines with adjusted amounts
                invoice_lines = []
                for line in move.invoice_line_ids:
                    if self.refund_type == 'percentage':
                        line_amount = line.price_unit * (self.percentage / 100)
                    else:  # fixed_amount - distribute proportionally
                        total_amount = sum(move.invoice_line_ids.mapped('price_subtotal'))
                        if total_amount:
                            line_proportion = line.price_subtotal / total_amount
                            line_amount = self.amount * line_proportion
                        else:
                            line_amount = self.amount / len(move.invoice_line_ids)
                    
                    invoice_lines.append((0, 0, {
                        'name': line.name,
                        'product_id': line.product_id.id,
                        'account_id': line.account_id.id,
                        'quantity': line.quantity,
                        'price_unit': line_amount / line.quantity if line.quantity else line_amount,
                        'tax_ids': [(6, 0, line.tax_ids.ids)],
                        'analytic_distribution': line.analytic_distribution,
                    }))
                refund_values['invoice_line_ids'] = invoice_lines
            else:
                # Create single line for the refund amount using custom description
                line_description = self.custom_description or self.reason or _('Partial Refund')
                refund_values['invoice_line_ids'] = [(0, 0, {
                    'name': line_description,
                    'account_id': self.account_id.id,
                    'price_unit': refund_amount,
                    'quantity': 1,
                })]
            
            refund_move = self.env['account.move'].create(refund_values)
            refund_moves |= refund_move
            
            # Ensure Dominican fiscal fields are set for partial refunds
            if move.company_id.country_id.code == "DO" and move.l10n_latam_use_documents:
                # Configurar campos fiscales para la nota de crédito parcial
                # Asegurar que se tenga un tipo de documento válido
                document_type_id = False
                if self.l10n_latam_document_type_id:
                    document_type_id = self.l10n_latam_document_type_id._origin.id if hasattr(self.l10n_latam_document_type_id, '_origin') else self.l10n_latam_document_type_id.id
                
                # Si no hay tipo de documento, usar el tipo de documento de crédito por defecto
                if not document_type_id:
                    # MODIFICADO: Arturo Diaz Lora - 2026-03-27
                    # Para facturas de proveedor, siempre usar tipos electrónicos
                    is_purchase = move.move_type in ('in_invoice', 'in_refund')
                    use_electronic_types = is_purchase or move.company_id.l10n_do_ecf_issuer

                    if use_electronic_types:
                        credit_type = self.env['l10n_latam.document.type'].search([
                            ('l10n_do_ncf_type', '=', 'e-credit_note'),
                            ('country_id.code', '=', 'DO')
                        ], limit=1)
                    else:
                        credit_type = self.env['l10n_latam.document.type'].search([
                            ('l10n_do_ncf_type', '=', 'credit_note'),
                            ('country_id.code', '=', 'DO')
                        ], limit=1)

                    if credit_type:
                        document_type_id = credit_type.id
                        _logger.info(f"Usando tipo de documento de crédito por defecto para parcial: {credit_type.name} (ID: {credit_type.id})")
                
                fiscal_fields = {
                    'l10n_latam_document_type_id': document_type_id,  # ¡CRÍTICO! Asegurar que haya un valor válido
                    'l10n_do_origin_ncf': move.l10n_latam_document_number,
                    'l10n_do_income_type': move.l10n_do_income_type,
                    'l10n_do_expense_type': move.l10n_do_expense_type,
                    'l10n_do_ecf_modification_code': self.l10n_do_ecf_modification_code,
                    'l10n_do_ncf_expiration_date': self.l10n_do_ncf_expiration_date,
                }
                
                # Configurar el número de documento
                # Para notas de crédito de cliente, NO usar número manual ni copiar de la factura original
                # El sistema debe generar automáticamente un número de secuencia fiscal
                if move.move_type == "out_invoice":
                    # Nota de crédito de cliente - NO establecer número de documento manualmente
                    # Se generará automáticamente desde la secuencia fiscal durante _post()
                    pass
                else:
                    # Para notas de crédito de proveedor, permitir número manual
                    if self.l10n_latam_document_number:
                        # Si se proporcionó manualmente en el wizard, usar ese valor
                        fiscal_fields['l10n_latam_document_number'] = self.l10n_latam_document_number
                    elif move.l10n_latam_document_number:
                        # Si no se proporcionó manualmente pero la factura original tiene número, usar ese
                        fiscal_fields['l10n_latam_document_number'] = move.l10n_latam_document_number
                
                # Forzar la configuración de manual_document_number para notas de crédito de proveedor
                if move.move_type == "in_invoice":
                    fiscal_fields['l10n_latam_manual_document_number'] = True
                
                # Escribir todos los campos fiscales en una sola operación
                refund_move.write(fiscal_fields)
                
                # Log para verificar que los campos se guardaron correctamente
                _logger.info(f"=== CAMPOS FISCALES GUARDADOS EN NOTA DE CRÉDITO PARCIAL ===")
                _logger.info(f"Refund move ID: {refund_move.id}")
                _logger.info(f"l10n_latam_document_number: {refund_move.l10n_latam_document_number}")
                _logger.info(f"l10n_do_ncf_expiration_date: {refund_move.l10n_do_ncf_expiration_date}")
                _logger.info(f"l10n_do_origin_ncf: {refund_move.l10n_do_origin_ncf}")
                _logger.info(f"l10n_do_ecf_modification_code: {refund_move.l10n_do_ecf_modification_code}")
                _logger.info(f"l10n_latam_manual_document_number: {refund_move.l10n_latam_manual_document_number}")
            
            # Always post partial refunds automatically
            # This ensures that partial refunds are immediately applied
            refund_move.action_post()
            
            # After posting, reconcile the credit note with the original invoice
            # to affect the invoice's residual amount
            self._reconcile_partial_credit_note(refund_move, move, refund_amount)
            
            # Log the automatic posting
            refund_move.message_post(
                body=_('Nota de crédito parcial validada y publicada automáticamente.')
            )
                
        if len(refund_moves) == 1:
            return {
                'name': _('Credit Note'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': refund_moves.id,
                'view_mode': 'form',
                'target': 'current',
            }
        else:
            return {
                'name': _('Credit Notes'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'domain': [('id', 'in', refund_moves.ids)],
                'view_mode': 'tree,form',
                'target': 'current',
            }

    @api.onchange('l10n_latam_document_number', 'l10n_latam_document_type_id')
    def _onchange_l10n_latam_document_number(self):
        if self.l10n_latam_document_type_id:
            l10n_latam_document_number = self.l10n_latam_document_type_id._format_document_number(
                self.l10n_latam_document_number)
            if self.l10n_latam_document_number != l10n_latam_document_number:
                self.l10n_latam_document_number = l10n_latam_document_number

    # def reverse_moves(self, is_modify=False):
    #     active_id = self.env.context.get("active_id", False)
    #     if active_id:
    #         if self.move_type == "in_invoice":
    #             ncf = self.l10n_latam_document_number[0:3]
    #             ncf_digits = len(self.l10n_latam_document_number)
    #             if (
    #                 self.env.context.get("debit_note")
    #                 and ncf not in ("B03", "E33")
    #             ):
    #                 raise UserError(
    #                     _(
    #                         "Debit Notes must be type B03 or E33, this NCF "
    #                         "structure does not comply."
    #                     )
    #                 )
    #
    #             elif ncf not in ("B04", "E34"):
    #                 raise UserError(
    #                     _(
    #                         ("Credit Notes must be type B04 or E34, this NCF (Type %s)"
    #                         " structure does not comply.") % ncf
    #                     )
    #                 )
    #
    #             elif (ncf_digits != 11 and ncf == 'B04') \
    #                     or (ncf_digits != 13 and ncf == 'E34'):
    #                 raise UserError(
    #                     _(
    #                         ("The number of fiscal sequence in this invoice is "
    #                         "incorrect, please double check the fiscal sequence")
    #                         )
    #                 )
    #
    #     return super(AccountMoveReversal, self).reverse_moves(is_modify)
