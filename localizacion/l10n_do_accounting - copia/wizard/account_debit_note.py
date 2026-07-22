import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError, ValidationError

_logger = logging.getLogger(__name__)


class AccountDebitNote(models.TransientModel):
    _inherit = "account.debit.note"

    @api.model
    def _get_l10n_do_debit_type_selection(self):
        selection = [
            ("percentage", _("Percentage")),
            ("fixed_amount", _("Amount")),
        ]
        return selection

    @api.model
    def _get_l10n_do_default_debit_type(self):
        return "percentage"

    @api.model
    def _get_l10n_do_debit_action_selection(self):
        return [
            ("draft_debit", _("Draft debit")),
            ("apply_debit", _("Apply debit")),
        ]

    l10n_do_country_code = fields.Char(
        default=lambda self: self.env.company.country_id.code,
        compute='_compute_country_code',
        help="Technical field used to hide/show fields regarding the localization",
    )
    l10n_latam_country_code = fields.Char(
        string="Latam Country Code",
        related="company_id.country_id.code",
        help="Technical field used to hide/show fields regarding the localization",
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
    l10n_do_debit_type = fields.Selection(
        selection=_get_l10n_do_debit_type_selection,
        default=_get_l10n_do_default_debit_type,
        string="Debit Type",
    )
    l10n_do_debit_action = fields.Selection(
        selection=_get_l10n_do_debit_action_selection,
        default="draft_debit",
        string="Action",
    )
    l10n_do_percentage = fields.Float(
        help="Debit Note based on origin invoice percentage",
        string="Percentage",
    )
    l10n_do_amount = fields.Float(
        help="Debit Note based fixed amount",
        string="Amount",
    )
    l10n_do_account_id = fields.Many2one(
        "account.account",
        string="Account",
        domain=[("deprecated", "=", False)],
    )
    l10n_latam_document_number = fields.Char(
        string="Document Number",
    )
    l10n_do_origin_ncf = fields.Char(
        string="NCF modificado",
        help="NCF de la factura original que se modifica",
    )
    l10n_do_ncf_expiration_date = fields.Date(
        string="Válida hasta",
        help="Fecha de vencimiento del NCF",
    )
    l10n_do_ecf_modification_code = fields.Selection(
        selection=lambda self: self.env[
            "account.move"
        ]._get_l10n_do_ecf_modification_code(),
        string="e-CF Modification Code",
        copy=False,
        default="1",  # 01 - Total Cancellation
    )
    is_ecf_invoice = fields.Boolean(
        string="Is Electronic Invoice",
    )
    l10n_do_ecf_issuer = fields.Boolean(
        related='company_id.l10n_do_ecf_issuer',
        string="Is Electronic Issuer",
        readonly=True,
        help="Indicates if the company is an electronic invoice issuer"
    )
    l10n_latam_use_documents = fields.Boolean("Use Documents", readonly=True)
    l10n_latam_available_document_type_ids = fields.Many2many('l10n_latam.document.type',
                                                              compute='_compute_document_type')
    l10n_latam_document_type_id = fields.Many2one(
        "l10n_latam.document.type", "Document Type", ondelete="cascade",
        domain="[('id', 'in', l10n_latam_available_document_type_ids)]",
        readonly=False
    )
    l10n_latam_manual_document_number = fields.Boolean(
        string="Manual Document Number",
        compute="_compute_l10n_latam_manual_document_number",
    )
    
    show_vendor_document_number = fields.Boolean(
        string="Show Vendor Document Number",
        compute="_compute_show_vendor_document_number",
        help="Determines if the document number field should be shown for vendor debit notes"
    )
    
    custom_description = fields.Char(
        string="Custom Description",
        help="Custom description to use when not copying product lines"
    )
    
    # Override copy_lines to set default=True
    copy_lines = fields.Boolean(
        "Copy Lines",
        default=True,
        help="In case you need to do corrections for every line, it can be in handy to copy them. "
             "We won't copy them for debit notes from credit notes."
    )

    @api.depends('l10n_latam_document_type_id', 'move_ids.move_type', 'l10n_do_country_code')
    def _compute_l10n_latam_manual_document_number(self):
        _logger.info("=== COMPUTING MANUAL DOCUMENT NUMBER FOR DEBIT NOTE WIZARD ===")
        for rec in self:
            rec.l10n_latam_manual_document_number = False
            
            if rec.move_ids and rec.l10n_do_country_code == 'DO':
                move = rec.move_ids[0]
                _logger.info(f"Processing move: {move.name} ({move.move_type})")
                
                if move.journal_id and move.journal_id.l10n_latam_use_documents:
                    # Para notas de débito de proveedor, siempre permitir números manuales
                    if move.move_type == "in_invoice":  # Original invoice is vendor invoice
                        rec.l10n_latam_manual_document_number = True
                        _logger.info(f"Vendor invoice -> manual document number = True")
                    else:
                        # Para notas de débito de cliente, usar lógica estándar
                        manual_result = move._is_manual_document_number()
                        rec.l10n_latam_manual_document_number = manual_result
                        _logger.info(f"Customer invoice -> manual document number = {manual_result}")
                else:
                    _logger.info(f"No use documents or no journal -> manual document number = False")
            else:
                _logger.info(f"No move_ids or not Dominican Republic -> manual document number = False")

    @api.depends('move_ids', 'l10n_do_country_code', 'l10n_latam_use_documents')
    def _compute_show_vendor_document_number(self):
        """Determina si se debe mostrar el campo de número de documento para notas de débito de proveedor"""
        _logger.info("=== COMPUTING SHOW VENDOR DOCUMENT NUMBER ===")
        for rec in self:
            rec.show_vendor_document_number = False
            
            # Solo mostrar para República Dominicana con documentos latinoamericanos
            if rec.l10n_do_country_code == 'DO' and rec.move_ids:
                move = rec.move_ids[0]
                _logger.info(f"Checking move: {move.name} ({move.move_type})")
                
                # Solo mostrar para notas de débito de proveedor (factura original es in_invoice)
                if move.move_type == "in_invoice" and move.journal_id and move.journal_id.l10n_latam_use_documents:
                    rec.show_vendor_document_number = True
                    _logger.info(f"Show vendor document number = True")
                else:
                    _logger.info(f"Not vendor invoice or no use documents -> show_vendor_document_number = False")
            else:
                _logger.info(f"Not DO or no move_ids -> show_vendor_document_number = False")

    @api.onchange('move_ids')
    def _onchange_move_ids(self):
        """Recompute document type when move_ids changes"""
        _logger.info("=== ONCHANGE MOVE_IDS FOR DEBIT NOTE WIZARD ===")
        if self.move_ids:
            _logger.info(f"Move IDs changed: {self.move_ids.ids}")
            _logger.info("Recomputing document type and country code...")
            self._compute_document_type()
            self._compute_country_code()
            self._compute_show_vendor_document_number()
            _logger.info("Recomputation completed")
        else:
            _logger.info("No move_ids set")

    @api.depends('move_ids')
    def _compute_country_code(self):
        _logger.info("=== COMPUTING COUNTRY CODE FOR DEBIT NOTE WIZARD ===")
        for record in self:
            if record.move_ids:
                country_code = record.move_ids[0].company_id.country_id.code
                record.l10n_do_country_code = country_code
                _logger.info(f"Move found, country code set to: {country_code}")
            else:
                country_code = record.env.company.country_id.code
                record.l10n_do_country_code = country_code
                _logger.info(f"No move found, using env company country code: {country_code}")

    @api.depends('move_ids')
    def _compute_document_type(self):
        _logger.info("=== COMPUTING DOCUMENT TYPE FOR DEBIT NOTE WIZARD ===")

        # Modificado 2025-11-22 por Arturo Diaz Lora
        # No limpiar los campos si ya están establecidos para evitar parpadeo en la UI
        # self.l10n_latam_available_document_type_ids = False
        # self.l10n_latam_use_documents = False
        
        for record in self:
            _logger.info(f"Processing record ID: {record.id}")
            _logger.info(f"Move IDs: {record.move_ids.ids}")
            
            if len(record.move_ids) > 1:
                _logger.warning("Multiple moves detected, checking for problematic documents")
                move_ids_use_document = record.move_ids._origin.filtered(lambda move: move.l10n_latam_use_documents)
                if move_ids_use_document:
                    _logger.error(f"Problematic documents: {move_ids_use_document.mapped('name')}")
                    raise UserError(
                        _('You can only create debit notes from documents with legal invoicing documents from Latin America one at a time.\nProblematic documents: %s') % ", ".join(
                            move_ids_use_document.mapped('name')))
            else:
                if record.move_ids and record.move_ids.journal_id:
                    use_documents = record.move_ids.journal_id.l10n_latam_use_documents
                    record.l10n_latam_use_documents = use_documents
                    _logger.info(f"Journal: {record.move_ids.journal_id.name}")
                    _logger.info(f"l10n_latam_use_documents set to: {use_documents}")
                else:
                    _logger.warning("No move_ids or journal found")

            if record.l10n_latam_use_documents:
                _logger.info("USE DOCUMENTS = TRUE, processing document types...")
                # Create temporary debit move to get available document types
                original_move = record.move_ids[0]
                _logger.info(f"Original move: {original_move.name} ({original_move.move_type})")
                
                debit_move_type = record._reverse_type_map(original_move.move_type)
                _logger.info(f"Mapped debit move type: {debit_move_type}")
                
                # Create the temporary move with all required fields
                debit_data = {
                    'move_type': debit_move_type,
                    'journal_id': original_move.journal_id.id,
                    'partner_id': original_move.partner_id.id,
                    'company_id': original_move.company_id.id,
                    'debit_origin_id': original_move.id,  # This is crucial for debit note identification
                }
                _logger.info(f"Creating temporary debit move with data: {debit_data}")
                
                debit = record.env['account.move'].with_context(internal_type="debit_note").new(debit_data)
                _logger.info(f"Temporary debit move created: {debit}")
                
                # Force computation of available document types
                _logger.info("Forcing computation of available document types...")
                debit._compute_l10n_latam_available_document_types()
                
                try:
                    available_types = debit.l10n_latam_available_document_type_ids
                    _logger.info(f"Available document types from computed field: {available_types.mapped('name')} (IDs: {available_types.ids})")
                    
                    # If no types found, try direct computation using the domain
                    if not available_types:
                        _logger.warning("No types found with computed field, trying direct domain search")
                        try:
                            domain = debit._get_l10n_latam_documents_domain()
                            _logger.info(f"Domain for document types: {domain}")
                            available_types = record.env['l10n_latam.document.type'].search(domain)
                            _logger.info(f"Domain search result: {available_types.mapped('name')} (IDs: {available_types.ids})")
                        except Exception as domain_error:
                            _logger.error(f"Error getting domain: {domain_error}")
                    
                    # Filter for debit note document types (B03 or E33)
                    # MODIFICADO: Arturo Diaz Lora - 2026-03-27
                    # Para facturas de proveedor, siempre mostrar tipos electrónicos
                    # porque el proveedor puede ser emisor electrónico aunque la compañía no lo sea
                    is_purchase = original_move.move_type in ('in_invoice', 'in_refund')
                    is_ecf = original_move.company_id.l10n_do_ecf_issuer
                    use_electronic_types = is_purchase or is_ecf
                    _logger.info(f"Company is ECF issuer: {is_ecf}, is_purchase: {is_purchase}, use_electronic_types: {use_electronic_types}")

                    if use_electronic_types:
                        b03 = available_types.filtered(lambda d: d.l10n_do_ncf_type == "e-debit_note")
                        _logger.info(f"Using electronic types - looking for e-debit_note, found: {b03.mapped('name')} (IDs: {b03.ids})")
                    else:
                        b03 = available_types.filtered(lambda d: d.l10n_do_ncf_type == "debit_note")
                        _logger.info(f"Using non-electronic types - looking for debit_note, found: {b03.mapped('name')} (IDs: {b03.ids})")
                    
                    # Fallback to any debit note type
                    if not b03:
                        b03 = available_types.filtered(lambda d: d.internal_type == "debit_note")
                        _logger.info(f"Fallback - looking for internal_type=debit_note, found: {b03.mapped('name')} (IDs: {b03.ids})")
                    
                    if b03:
                        _logger.info(f"SELECTED debit note document type: {b03[0].name} (ID: {b03[0].id})")
                    elif available_types:
                        _logger.warning(f"No specific debit type found, using first available: {available_types[0].name}")
                    else:
                        _logger.error("NO DOCUMENT TYPES FOUND AT ALL!")

                    record.l10n_latam_available_document_type_ids = available_types
                    _logger.info(f"SET available document types: {available_types.ids}")

                    # Modificado 2025-11-22 por Arturo Diaz Lora
                    # Establecer el tipo de documento seleccionado para que aparezca en la UI
                    # Sin esto, el campo aparece vacío aunque los tipos disponibles estén establecidos
                    if b03:
                        record.l10n_latam_document_type_id = b03[0]
                        _logger.info(f"SET selected document type: {b03[0].name} (ID: {b03[0].id})")
                    elif available_types:
                        record.l10n_latam_document_type_id = available_types[0]
                        _logger.info(f"SET selected document type (fallback): {available_types[0].name} (ID: {available_types[0].id})")
                    
                except Exception as e:
                    # If there's an error getting document types, try to get them directly
                    _logger.warning(f"Error computing document types in debit note wizard: {e}")

                    # Fallback: search directly for debit note document types
                    debit_types = record.env['l10n_latam.document.type'].search([
                        ('internal_type', '=', 'debit_note')
                    ])

                    record.l10n_latam_available_document_type_ids = debit_types

                    # Modificado 2025-11-22 por Arturo Diaz Lora
                    # También establecer el tipo seleccionado en el fallback
                    if debit_types:
                        record.l10n_latam_document_type_id = debit_types[0]
                        _logger.info(f"SET selected document type (exception fallback): {debit_types[0].name}")

    @api.model
    def _reverse_type_map(self, move_type):
        """Map original move types to debit note move types - in Odoo v18 debit notes use same move_type"""
        # In Odoo v18, debit notes use the same move_type as the original invoice
        # They are identified by the debit_origin_id field, not by the move_type
        match = {
            'entry': 'entry',
            'out_invoice': 'out_invoice',    # Customer invoice -> Customer debit note (same type)
            'in_invoice': 'in_invoice',      # Vendor bill -> Vendor debit note (same type)
            'out_refund': 'out_invoice',     # Create debit note from credit note  
            'in_refund': 'in_invoice',       # Create debit note from vendor credit note
            'out_receipt': 'in_receipt',
            'in_receipt': 'out_receipt'
        }
        return match.get(move_type)

    @api.model
    def default_get(self, fields):
        _logger.info("=== DEFAULT_GET FOR DEBIT NOTE WIZARD ===")
        _logger.info(f"Requested fields: {fields}")
        _logger.info(f"Context: {self.env.context}")
        
        res = super(AccountDebitNote, self).default_get(fields)
        _logger.info(f"Super default_get result: {res}")

        move_ids = (
            self.env["account.move"].browse(self.env.context["active_ids"])
            if self.env.context.get("active_model") == "account.move"
            else self.env["account.move"]
        )
        _logger.info(f"Active move IDs: {move_ids.ids}")

        if not move_ids:
            _logger.error("No invoice found for this operation")
            raise UserError(_("No invoice found for this operation"))

        move_ids_use_document = move_ids.filtered(
            lambda move: move.l10n_latam_use_documents
            and move.company_id.country_id.code == "DO"
        )
        if move_ids_use_document and not self.env.user.has_group(
            "l10n_do_accounting.group_l10n_do_debit_note"
        ):
            raise AccessError(_("You are not allowed to issue Debit Notes"))

        # Setting default account
        journal = move_ids[0].journal_id
        res["l10n_do_account_id"] = journal.default_account_id.id
        res["l10n_latam_use_documents"] = journal.l10n_latam_use_documents
        
        # Fallback account if journal doesn't have default_account_id
        if not res.get("l10n_do_account_id"):
            # Try to get a revenue/expense account based on move type
            if move_ids[0].move_type == 'out_invoice':
                # Customer invoice -> use revenue account
                revenue_account = self.env['account.account'].search([
                    ('account_type', '=', 'income'),
                    ('company_id', '=', move_ids[0].company_id.id)
                ], limit=1)
                if revenue_account:
                    res["l10n_do_account_id"] = revenue_account.id
            else:
                # Vendor bill -> use expense account
                expense_account = self.env['account.account'].search([
                    ('account_type', '=', 'expense'),
                    ('company_id', '=', move_ids[0].company_id.id)
                ], limit=1)
                if expense_account:
                    res["l10n_do_account_id"] = expense_account.id

        # Do not allow Debit Notes if Comprobante de Compra or Gastos Menores
        if move_ids[0].l10n_latam_document_type_id.l10n_do_ncf_type in (
            "informal",
            "minor",
            "e-informal",
            "e-minor",
        ):
            raise UserError(
                _("You cannot issue Credit/Debit Notes for %s document type")
                % move_ids_use_document.l10n_latam_document_type_id.name
            )

        if len(move_ids_use_document) > 1:
            raise UserError(
                _("You cannot create Debit Notes from multiple documents at a time.")
            )
        else:
            res["is_ecf_invoice"] = (
                move_ids_use_document and move_ids_use_document[0].is_ecf_invoice
            )

        # Auto-llenar el campo l10n_do_ncf_expiration_date de la factura original
        if move_ids and move_ids[0].l10n_do_ncf_expiration_date:
            res["l10n_do_ncf_expiration_date"] = move_ids[0].l10n_do_ncf_expiration_date
        
        # Set default document type for Dominican Republic (force B03)
        if move_ids_use_document and move_ids_use_document[0].company_id.country_id.code == "DO":
            move_id = move_ids_use_document[0]
            # Map to correct debit note move type
            debit_move_type = self._reverse_type_map(move_id.move_type)
            
            move = (
                self.env["account.move"]
                .with_context(internal_type="debit_note")
                .new(
                    {
                        "partner_id": move_id.partner_id.id,
                        "move_type": debit_move_type,  # Use correct debit move type
                        "journal_id": move_id.journal_id.id,
                        "debit_origin_id": move_id.id,  # This is crucial for debit note identification
                    }
                )
            )
            
            try:
                domain_ids = (
                    self.env["l10n_latam.document.type"]
                    .search(move._get_l10n_latam_documents_domain())
                )
                # Establecer los tipos de documento disponibles
                res["l10n_latam_available_document_type_ids"] = [(6, 0, domain_ids.ids)]

                # MODIFICADO: Arturo Diaz Lora - 2026-03-27
                # Para facturas de proveedor, siempre mostrar tipos electrónicos
                is_purchase = move_id.move_type in ('in_invoice', 'in_refund')
                use_electronic_types = is_purchase or move_id.company_id.l10n_do_ecf_issuer

                # Filtrar por comprobante B03 (Nota de Débito) o E33 (electrónica)
                if use_electronic_types:
                    b03 = domain_ids.filtered(lambda d: d.l10n_do_ncf_type == "e-debit_note")
                else:
                    b03 = domain_ids.filtered(lambda d: d.l10n_do_ncf_type == "debit_note")
                
                # Fallback to any debit note type
                if not b03:
                    b03 = domain_ids.filtered(lambda d: d.internal_type == "debit_note")
                    
                if b03:
                    res["l10n_latam_document_type_id"] = b03[0]._origin.id if hasattr(b03[0], '_origin') else b03[0].id
                elif domain_ids:
                    res["l10n_latam_document_type_id"] = domain_ids[0]._origin.id if hasattr(domain_ids[0], '_origin') else domain_ids[0].id
                    
            except Exception as e:
                # If there's an error getting document types, try to get them directly
                _logger.warning(f"Error computing document types in debit note default_get: {e}")
                
                # Fallback: search directly for debit note document types
                debit_types = self.env['l10n_latam.document.type'].search([
                    ('internal_type', '=', 'debit_note')
                ])
                
                # Establecer los tipos de documento disponibles como fallback
                res["l10n_latam_available_document_type_ids"] = [(6, 0, debit_types.ids)]

                # MODIFICADO: Arturo Diaz Lora - 2026-03-27
                # Para facturas de proveedor, siempre mostrar tipos electrónicos
                is_purchase = move_id.move_type in ('in_invoice', 'in_refund')
                use_electronic_types = is_purchase or move_id.company_id.l10n_do_ecf_issuer

                if use_electronic_types:
                    b03 = debit_types.filtered(lambda d: d.l10n_do_ncf_type == "e-debit_note")
                else:
                    b03 = debit_types.filtered(lambda d: d.l10n_do_ncf_type == "debit_note")
                
                if b03:
                    res["l10n_latam_document_type_id"] = b03[0]._origin.id if hasattr(b03[0], '_origin') else b03[0].id
                elif debit_types:
                    res["l10n_latam_document_type_id"] = debit_types[0]._origin.id if hasattr(debit_types[0], '_origin') else debit_types[0].id

        # Ensure l10n_do_country_code is set
        if move_ids:
            res["l10n_do_country_code"] = move_ids[0].company_id.country_id.code
        else:
            res["l10n_do_country_code"] = self.env.company.country_id.code

        # Modificado 2025-11-22 por Arturo Diaz Lora
        # Agregar campo l10n_latam_country_code para compatibilidad con vistas
        # Este campo es usado en las condiciones invisible de la vista XML
        # En TransientModels, los campos related no se calculan automáticamente en default_get
        # Por eso debe establecerse explícitamente (mismo patrón usado en wizard de crédito)
        if move_ids and move_ids[0].company_id.country_id.code == "DO":
            res['l10n_latam_country_code'] = 'DO'
            _logger.info("Set l10n_latam_country_code for debit note wizard visibility")
        elif self.env.company.country_id.code == "DO":
            res['l10n_latam_country_code'] = 'DO'
            _logger.info("Set l10n_latam_country_code from env company")

        # Set default debit type if not set
        if "l10n_do_debit_type" not in res:
            res["l10n_do_debit_type"] = "apply_debit"
            
        # Set default debit action if not set  
        if "l10n_do_debit_action" not in res:
            res["l10n_do_debit_action"] = "draft_debit"
            
        # Set default e-CF modification code for Dominican Republic
        if move_ids and move_ids[0].company_id.country_id.code == "DO":
            if "l10n_do_ecf_modification_code" not in res:
                res["l10n_do_ecf_modification_code"] = "1"  # 01 - Total Cancellation

        return res



    def _prepare_default_values(self, move):
        res = super(AccountDebitNote, self)._prepare_default_values(move)

        # Ensure auto_post is set correctly
        if 'auto_post' not in res:
            reverse_date = self.date or move.date
            res['auto_post'] = 'at_date' if reverse_date > fields.Date.context_today(self) else 'no'

        # Include additional info when l10n_do debit note
        if self.l10n_do_country_code == "DO" and move.l10n_latam_use_documents:
            fiscal_data = {
                'l10n_latam_document_type_id': self.l10n_latam_document_type_id._origin.id if self.l10n_latam_document_type_id else False,
                'l10n_do_ecf_modification_code': self.l10n_do_ecf_modification_code,
                'l10n_do_expense_type': move.l10n_do_expense_type,
                'l10n_do_income_type': move.l10n_do_income_type,
                'invoice_origin': move.name,
                # Copy fiscal sequence expiration date to show "Válida hasta"
                'l10n_do_ncf_expiration_date': move.l10n_do_ncf_expiration_date,
                # Ensure debit_origin_id is set to identify this as a debit note
                'debit_origin_id': move.id,
            }
            
            # Para todas las notas de débito, establecer NCF modificado
            fiscal_data['l10n_do_origin_ncf'] = move.l10n_latam_document_number
            if move.move_type == "in_invoice":
                _logger.info(f"Setting l10n_do_origin_ncf for vendor debit note: {move.l10n_latam_document_number}")
            else:
                _logger.info(f"Setting l10n_do_origin_ncf for customer debit note: {move.l10n_latam_document_number}")
            
            # Solo establecer l10n_latam_document_number para notas de débito de proveedor
            # Para notas de débito de cliente, dejarlo vacío para que se genere automáticamente
            if move.move_type == "in_invoice":
                # Nota de débito de proveedor - permitir número manual
                fiscal_data['l10n_latam_document_number'] = self.l10n_latam_document_number
            # Para move.move_type == "out_invoice" (nota de débito de cliente), NO establecer l10n_latam_document_number
            # para que el sistema lo genere automáticamente desde la secuencia fiscal
            
            res.update(fiscal_data)

        return res

    def create_debit(self):
        _logger.info("=== CREATE DEBIT NOTE STARTED ===")
        _logger.info(f"Country code: {self.l10n_do_country_code}")
        _logger.info(f"Use documents: {self.l10n_latam_use_documents}")
        _logger.info(f"Manual document number: {self.l10n_latam_manual_document_number}")
        _logger.info(f"Document number: {self.l10n_latam_document_number}")
        _logger.info(f"Document type: {self.l10n_latam_document_type_id}")
        _logger.info(f"Move IDs: {self.move_ids.ids}")
        
        # Validar formato NCF antes de crear la nota de débito
        if (self.l10n_do_country_code == 'DO' and
            self.l10n_latam_use_documents and
            self.l10n_latam_manual_document_number and
            self.l10n_latam_document_number and
            self.l10n_latam_document_type_id and
            self.move_ids and
            self.move_ids[0].move_type == "in_invoice"):  # Original invoice is vendor invoice
            
            _logger.info("Validating NCF format for vendor debit note...")
            
            if not self._validate_ncf_format_vendor_notes():
                raise ValidationError(_(
                    'El número de comprobante "%s" no cumple con los requisitos de formato NCF de la DGII para notas de débito de proveedor.\n\n'
                    'NCF Físicos (serie B): B + 2 dígitos (03) + 9 dígitos = 11 caracteres\n'
                    'NCF Electrónicos (serie E): E + 2 dígitos (33) + 10 dígitos = 13 caracteres\n\n'
                    'Por favor verifique el formato según el tipo de documento fiscal.',
                    self.l10n_latam_document_number
                ))
        
        if self.l10n_latam_use_documents and self.l10n_do_country_code:
            context_data = {
                'l10n_do_debit_type': self.l10n_do_debit_type,
                'amount': self.l10n_do_amount,
                'percentage': self.l10n_do_percentage,
                'reason': self.reason,
            }
            _logger.info(f"Setting context: {context_data}")
            self = self.with_context(**context_data)

        _logger.info("Calling super create_debit()...")
        action = super(AccountDebitNote, self).create_debit()
        _logger.info(f"Super create_debit result: {action}")
        
        # Ensure lines are copied and fiscal fields are set
        if action.get('res_id'):
            _logger.info(f"Processing created debit move ID: {action['res_id']}")
            debit_move = self.env['account.move'].browse(action['res_id'])
            _logger.info(f"Debit move: {debit_move.name} ({debit_move.move_type})")
            _logger.info(f"Debit move document number before processing: {debit_move.l10n_latam_document_number}")
            _logger.info(f"Debit move document type: {debit_move.l10n_latam_document_type_id}")
            
            # IMPORTANTE: Odoo ya creó las líneas por defecto, ahora las modificamos
            # Primero eliminamos todas las líneas existentes para recrearlas con nuestros cálculos
            debit_move.write({'invoice_line_ids': [(5, 0, 0)]})
            
            # Ahora creamos las líneas con nuestros cálculos personalizados
            if self.copy_lines:
                # Crear líneas individuales con cálculos personalizados
                self._create_custom_lines(debit_move, copy_lines=True)
            else:
                # Crear línea única con cálculo personalizado
                self._create_custom_lines(debit_move, copy_lines=False)
            
            # Ensure fiscal fields are properly set for Dominican Republic
            if self.l10n_do_country_code == "DO" and self.move_ids.l10n_latam_use_documents:
                original_move = self.move_ids[0]
                fiscal_fields = {
                    'l10n_do_income_type': original_move.l10n_do_income_type,
                    'l10n_do_expense_type': original_move.l10n_do_expense_type,
                    'l10n_do_ncf_expiration_date': self.l10n_do_ncf_expiration_date,
                    'l10n_do_ecf_modification_code': self.l10n_do_ecf_modification_code,
                    # Ensure document type is set correctly
                    'l10n_latam_document_type_id': self.l10n_latam_document_type_id._origin.id if self.l10n_latam_document_type_id else False,
                }
                
                # Para todas las notas de débito, establecer NCF modificado
                fiscal_fields['l10n_do_origin_ncf'] = original_move.l10n_latam_document_number
                if original_move.move_type == "in_invoice":
                    _logger.info(f"Setting l10n_do_origin_ncf in fiscal_fields for vendor debit note: {original_move.l10n_latam_document_number}")
                else:
                    _logger.info(f"Setting l10n_do_origin_ncf in fiscal_fields for customer debit note: {original_move.l10n_latam_document_number}")
                
                # Configurar el número de documento
                # Para notas de débito de cliente, NO establecer número de documento
                # Para que el sistema lo genere automáticamente desde la secuencia fiscal durante _post()
                if original_move.move_type == "out_invoice":
                    # Nota de débito de cliente - asegurar que el campo esté vacío para generación automática
                    # NO agregar l10n_latam_document_number a fiscal_fields
                    pass
                else:
                    # Para notas de débito de proveedor, permitir número manual
                    if self.l10n_latam_document_number:
                        # Si se proporcionó manualmente en el wizard, usar ese valor
                        fiscal_fields['l10n_latam_document_number'] = self.l10n_latam_document_number
                    elif original_move.l10n_latam_document_number:
                        # Si no se proporcionó manualmente pero la factura original tiene número, usar ese
                        fiscal_fields['l10n_latam_document_number'] = original_move.l10n_latam_document_number
                
                # Forzar la configuración de manual_document_number para notas de débito de proveedor
                if original_move.move_type == "in_invoice":
                    fiscal_fields['l10n_latam_manual_document_number'] = True
                
                # Escribir todos los campos fiscales en una sola operación
                debit_move.write(fiscal_fields)
                
                # Log para verificar que los campos se guardaron correctamente
                _logger.info(f"=== CAMPOS FISCALES GUARDADOS EN NOTA DE DÉBITO ===")
                _logger.info(f"Debit move ID: {debit_move.id}")
                _logger.info(f"l10n_latam_document_number: {debit_move.l10n_latam_document_number}")
                _logger.info(f"l10n_do_ncf_expiration_date: {debit_move.l10n_do_ncf_expiration_date}")
                _logger.info(f"l10n_do_origin_ncf: {debit_move.l10n_do_origin_ncf}")
                _logger.info(f"l10n_do_ecf_modification_code: {debit_move.l10n_do_ecf_modification_code}")
                _logger.info(f"l10n_latam_manual_document_number: {debit_move.l10n_latam_manual_document_number}")
                
                # Force recomputation of document type
                debit_move._compute_l10n_latam_document_type()
                
                # If still no document type, force set it manually
                if not debit_move.l10n_latam_document_type_id:
                    self._force_set_document_type(debit_move)
                
                # Log final results for verification

                _logger.info(f"=== RESULTADO FINAL DE LA NOTA DE DÉBITO ===")
                _logger.info(f"Debit move ID: {debit_move.id}")
                _logger.info(f"Debit move name: {debit_move.name}")
                _logger.info(f"Debit move amount_total: {debit_move.amount_total}")
                _logger.info(f"Debit move amount_untaxed: {debit_move.amount_untaxed}")
                _logger.info(f"Number of lines: {len(debit_move.invoice_line_ids)}")
                
                for i, line in enumerate(debit_move.invoice_line_ids):
                    _logger.info(f"Line {i+1}: {line.name}")
                    _logger.info(f"  Quantity: {line.quantity}")
                    _logger.info(f"  Price unit: {line.price_unit}")
                    _logger.info(f"  Price subtotal: {line.price_subtotal}")
                    if line.tax_ids:
                        _logger.info(f"  Tax IDs: {line.tax_ids.mapped('name')}")
                    else:
                        _logger.info(f"  No taxes applied")
        
        # NOTA: Para notas de débito de cliente, el número de documento se genera
        # automáticamente en el método _post() cuando se confirma la factura,
        # NO al crearla. Esto es correcto según los requerimientos del usuario.
        if action.get('res_id'):
            debit_move = self.env['account.move'].browse(action['res_id'])
            _logger.info(f"=== NOTA DE DÉBITO CREADA - NCF SE GENERARÁ AL CONFIRMAR ===")
            _logger.info(f"Move: {debit_move.name} (ID: {debit_move.id})")
            _logger.info(f"Current document number: {debit_move.l10n_latam_document_number}")
            _logger.info(f"El NCF se generará automáticamente cuando se confirme la factura (método _post)")
        
        if self.l10n_do_debit_action == "apply_debit":
            # Post Debit Note
            move_id = self.env["account.move"].browse(action.get("res_id", False))
            move_id._post()

        return action

    def _create_custom_lines(self, debit_move, copy_lines=False):
        """
        Create custom lines with our calculation logic
        """
        original_move = self.move_ids[0]
        
        if copy_lines:
            _logger.info(f"=== CREANDO NOTA DE DÉBITO CON LÍNEAS INDIVIDUALES ===")
            _logger.info(f"Original move: {original_move.name}")
            _logger.info(f"Original amount_total: {original_move.amount_total}")
            _logger.info(f"Original amount_untaxed: {original_move.amount_untaxed}")
            _logger.info(f"Debit type: {self.l10n_do_debit_type}")
            _logger.info(f"Debit percentage: {self.l10n_do_percentage}")
            _logger.info(f"Debit amount: {self.l10n_do_amount}")
            
            for line in original_move.invoice_line_ids:
                _logger.info(f"Processing line: {line.name}")
                _logger.info(f"Line price_subtotal: {line.price_subtotal}")
                _logger.info(f"Line price_unit: {line.price_unit}")
                _logger.info(f"Line quantity: {line.quantity}")
                
                # Calculate amount based on debit type - use subtotal (without taxes) for calculations
                if self.l10n_do_debit_type == 'percentage':
                    # Calculate percentage over the subtotal (without taxes) of the line
                    line_amount = line.price_subtotal * (self.l10n_do_percentage / 100)
                    _logger.info(f"Percentage calculation: {line.price_subtotal} * ({self.l10n_do_percentage} / 100) = {line_amount}")
                else:  # fixed_amount - distribute proportionally
                    # Use subtotal (without taxes) for proportional distribution
                    total_amount = original_move.amount_untaxed
                    if total_amount:
                        line_proportion = line.price_subtotal / total_amount
                        line_amount = self.l10n_do_amount * line_proportion
                        _logger.info(f"Proportional calculation: {line.price_subtotal} / {total_amount} = {line_proportion}, then {self.l10n_do_amount} * {line_proportion} = {line_amount}")
                    else:
                        line_amount = self.l10n_do_amount / len(original_move.invoice_line_ids)
                        _logger.info(f"Equal distribution: {self.l10n_do_amount} / {len(original_move.invoice_line_ids)} = {line_amount}")
                
                # Calculate price_unit correctly
                if line.quantity and line.quantity > 0:
                    price_unit = line_amount / line.quantity
                    _logger.info(f"Price unit calculation: {line_amount} / {line.quantity} = {price_unit}")
                else:
                    price_unit = line_amount
                    _logger.info(f"Price unit (no quantity): {price_unit}")
                
                # Create new line
                debit_move.write({
                    'invoice_line_ids': [(0, 0, {
                        'name': line.name,
                        'product_id': line.product_id.id,
                        'account_id': line.account_id.id,
                        'quantity': line.quantity,
                        'price_unit': price_unit,
                        'tax_ids': [(6, 0, line.tax_ids.ids)],
                        'analytic_distribution': line.analytic_distribution,
                    })]
                })
                _logger.info(f"Created line with amount: {line_amount}, price_unit: {price_unit}")
        else:
            _logger.info(f"=== CREANDO NOTA DE DÉBITO CON LÍNEA ÚNICA ===")
            _logger.info(f"Original move: {original_move.name}")
            _logger.info(f"Original amount_total: {original_move.amount_total}")
            _logger.info(f"Original amount_untaxed: {original_move.amount_untaxed}")
            _logger.info(f"Debit type: {self.l10n_do_debit_type}")
            _logger.info(f"Debit percentage: {self.l10n_do_percentage}")
            _logger.info(f"Debit amount: {self.l10n_do_amount}")
            
            # Calculate debit amount based on type - CORREGIDO: usar amount_untaxed para cálculos
            if self.l10n_do_debit_type == 'percentage':
                # Calculate percentage over the total amount WITHOUT taxes (amount_untaxed)
                debit_amount = original_move.amount_untaxed * (self.l10n_do_percentage / 100)
                _logger.info(f"Percentage calculation: {original_move.amount_untaxed} * ({self.l10n_do_percentage} / 100) = {debit_amount}")
            else:  # fixed_amount
                debit_amount = self.l10n_do_amount
                _logger.info(f"Fixed amount: {debit_amount}")
            
            # Use custom description or fallback to reason
            line_description = self.custom_description or self.reason or _('Debit Note')
            _logger.info(f"Line description: {line_description}")
            
            debit_move.write({
                'invoice_line_ids': [(0, 0, {
                    'name': line_description,
                    'account_id': self.l10n_do_account_id.id,
                    'quantity': 1,
                    'price_unit': debit_amount,
                })]
            })
            _logger.info(f"Created single line with amount: {debit_amount}")

    def _force_set_document_type(self, debit_move):
        """
        Force set the document type for debit notes when automatic computation fails
        """

        
        _logger.info("=== FORZANDO ESTABLECIMIENTO DE TIPO DE DOCUMENTO ===")
        
        try:
            # MODIFICADO: Arturo Diaz Lora - 2026-03-27
            # Para facturas de proveedor, siempre mostrar tipos electrónicos
            # porque el proveedor puede ser emisor electrónico aunque la compañía no lo sea
            original_move = self.move_ids[0] if self.move_ids else debit_move
            is_purchase = original_move.move_type in ('in_invoice', 'in_refund')
            use_electronic_types = is_purchase or debit_move.company_id.l10n_do_ecf_issuer

            # Search for debit note document types
            if use_electronic_types:
                # ECF or purchase - look for E33
                document_type = self.env['l10n_latam.document.type'].search([
                    ('l10n_do_ncf_type', '=', 'e-debit_note'),
                    ('country_id.code', '=', 'DO')
                ], limit=1)
                _logger.info(f"Electronic types (ECF or purchase) - found document type: {document_type.name if document_type else 'None'}")
            else:
                # Non-ECF customer invoice - look for B03
                document_type = self.env['l10n_latam.document.type'].search([
                    ('l10n_do_ncf_type', '=', 'debit_note'),
                    ('country_id.code', '=', 'DO')
                ], limit=1)
                _logger.info(f"Non-electronic types - found document type: {document_type.name if document_type else 'None'}")
            
            # Fallback to any debit note type
            if not document_type:
                document_type = self.env['l10n_latam.document.type'].search([
                    ('internal_type', '=', 'debit_note'),
                    ('country_id.code', '=', 'DO')
                ], limit=1)
                _logger.info(f"Fallback - found document type: {document_type.name if document_type else 'None'}")
            
            if document_type:
                debit_move.write({
                    'l10n_latam_document_type_id': document_type._origin.id if hasattr(document_type, '_origin') else document_type.id
                })
                _logger.info(f"Successfully set document type to: {document_type.name} (ID: {document_type.id})")
            else:
                _logger.error("No debit note document type found!")
                
        except Exception as e:
            _logger.error(f"Error forcing document type: {e}")

    @api.onchange('l10n_latam_document_number', 'l10n_latam_document_type_id')
    def _onchange_l10n_latam_document_number(self):
        """Validar formato NCF en tiempo real para notas de débito de proveedor"""
        if (self.l10n_do_country_code == 'DO' and
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
                            'El número de comprobante "%s" no cumple con los requisitos de formato NCF de la DGII para notas de débito de proveedor.\n\n'
                            'NCF Físicos (serie B): B + 2 dígitos (03) + 9 dígitos = 11 caracteres\n'
                            'NCF Electrónicos (serie E): E + 2 dígitos (33) + 10 dígitos = 13 caracteres\n\n'
                            'Por favor verifique el formato según el tipo de documento fiscal.',
                            self.l10n_latam_document_number
                        )
                    }
                }
        else:
            # Formatear el número según el tipo de documento
            if self.l10n_latam_document_type_id:
                l10n_latam_document_number = self.l10n_latam_document_type_id._format_document_number(
                    self.l10n_latam_document_number)
                if self.l10n_latam_document_number != l10n_latam_document_number:
                    self.l10n_latam_document_number = l10n_latam_document_number

    def _validate_ncf_format_vendor_notes(self):
        """Validar formato NCF específicamente para notas de débito de proveedor"""
        if not self.l10n_latam_document_number or not self.l10n_latam_document_type_id:
            return True

        ncf = self.l10n_latam_document_number.strip()
        doc_type = self.l10n_latam_document_type_id

        # Para notas de débito de proveedor, validar según el tipo de documento
        # Notas de débito (B03) físicas
        if doc_type.l10n_do_ncf_type in ['debit_note']:
            # Formato: B + 2 dígitos (03) + 8 dígitos = 11 caracteres
            if len(ncf) != 11:
                return False
            if not ncf.startswith('B'):
                return False
            if not ncf[1:3].isdigit():
                return False
            if not ncf[3:].isdigit():
                return False
            # Validar tipo de código (03 para débito)
            type_code = int(ncf[1:3])
            if type_code != 3:
                return False

        # Notas de débito (E33) electrónicas
        elif doc_type.l10n_do_ncf_type in ['e-debit_note']:
            # Formato: E + 2 dígitos (33) + 10 dígitos = 13 caracteres
            if len(ncf) != 13:
                return False
            if not ncf.startswith('E'):
                return False
            if not ncf[1:3].isdigit():
                return False
            if not ncf[3:].isdigit():
                return False
            # Validar tipo de código (33 para débito)
            type_code = int(ncf[1:3])
            if type_code != 33:
                return False

        return True
