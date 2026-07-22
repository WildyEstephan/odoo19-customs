import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    # Campo para búsqueda directa de RNC en la factura
    l10n_do_rnc_search = fields.Char(
        string="Buscar RNC/Cédula",
        help="Ingrese el RNC o Cédula para buscar el contribuyente en la DGII"
    )

    # Campo para mostrar información del RNC consultado
    l10n_do_rnc_preview_name = fields.Char(
        string="Nombre (DGII)",
        readonly=True,
        help="Nombre del contribuyente según la DGII"
    )
    l10n_do_rnc_preview_status = fields.Char(
        string="Estado (DGII)",
        readonly=True,
        help="Estado del contribuyente en la DGII"
    )
    l10n_do_rnc_preview_activity = fields.Char(
        string="Actividad (DGII)",
        readonly=True,
        help="Actividad económica del contribuyente"
    )

    # Campo para indicar si hay datos DGII disponibles para crear contacto
    l10n_do_rnc_data_ready = fields.Boolean(
        string="Datos DGII Listos",
        default=False,
        help="Indica si hay datos de la DGII listos para crear un contacto"
    )

    # Campos temporales para almacenar datos de DGII
    l10n_do_rnc_temp_commercial_name = fields.Char(string="Nombre Comercial Temp")
    l10n_do_rnc_temp_payment_regime = fields.Char(string="Régimen Pagos Temp")
    l10n_do_rnc_temp_category = fields.Char(string="Categoría Temp")
    l10n_do_rnc_temp_local_admin = fields.Char(string="Admin Local Temp")
    l10n_do_rnc_temp_vat_type = fields.Char(string="Tipo VAT Temp")

    @api.onchange('l10n_do_rnc_search')
    def _onchange_rnc_search(self):
        """
        Cuando se ingresa un RNC/Cédula, consulta la DGII y muestra la información.
        También busca si ya existe un contacto con ese RNC.
        """
        # Limpiar campos de preview
        self.l10n_do_rnc_preview_name = False
        self.l10n_do_rnc_preview_status = False
        self.l10n_do_rnc_preview_activity = False
        self.l10n_do_rnc_data_ready = False
        self.l10n_do_rnc_temp_commercial_name = False
        self.l10n_do_rnc_temp_payment_regime = False
        self.l10n_do_rnc_temp_category = False
        self.l10n_do_rnc_temp_local_admin = False
        self.l10n_do_rnc_temp_vat_type = False

        if not self.l10n_do_rnc_search:
            return

        # Verificar que sea una compañía dominicana
        do_country = self.env.ref("base.do", raise_if_not_found=False)
        if not do_country or self.company_id.country_id != do_country:
            return

        # Limpiar el RNC
        Partner = self.env['res.partner']
        clean_vat = Partner._clean_vat(self.l10n_do_rnc_search)

        if not clean_vat:
            return

        # Validar formato
        validated_vat, vat_type = Partner._validate_rnc_format(clean_vat)
        if not validated_vat:
            return {
                'warning': {
                    'title': _('Formato Inválido'),
                    'message': _(
                        'El RNC/Cédula ingresado no tiene un formato válido. '
                        'Debe ser un RNC de 9 dígitos o una Cédula de 11 dígitos.'
                    )
                }
            }

        # Buscar si ya existe un contacto con este RNC
        existing_partner = self.env['res.partner'].search([
            ('vat', '=', validated_vat),
            ('country_id', '=', do_country.id),
        ], limit=1)

        if existing_partner:
            # Si existe, seleccionarlo automáticamente
            self.partner_id = existing_partner
            self.l10n_do_rnc_preview_name = existing_partner.name
            self.l10n_do_rnc_preview_status = existing_partner.l10n_do_dgii_status or 'Contacto existente'
            self.l10n_do_rnc_preview_activity = existing_partner.l10n_do_dgii_activity
            self.l10n_do_rnc_search = False  # Limpiar el campo de búsqueda
            return {
                'warning': {
                    'title': _('Contacto Encontrado'),
                    'message': _(
                        'Se encontró el contacto "%s" con RNC %s. '
                        'Ha sido seleccionado automáticamente.'
                    ) % (existing_partner.name, validated_vat),
                    'type': 'notification',
                }
            }

        # Si no existe, consultar la DGII
        _logger.debug(f"Consultando DGII para RNC: {validated_vat}")
        dgii_data = Partner._query_dgii_rnc(validated_vat)

        if dgii_data:
            # Mostrar información en los campos de preview
            self.l10n_do_rnc_preview_name = dgii_data.get('name', '')
            self.l10n_do_rnc_preview_status = dgii_data.get('l10n_do_dgii_status', '')
            self.l10n_do_rnc_preview_activity = dgii_data.get('l10n_do_dgii_activity', '')
            self.l10n_do_rnc_data_ready = True

            # Guardar datos temporales para creación
            self.l10n_do_rnc_temp_commercial_name = dgii_data.get('l10n_do_dgii_commercial_name', '')
            self.l10n_do_rnc_temp_payment_regime = dgii_data.get('l10n_do_dgii_payment_regime', '')
            self.l10n_do_rnc_temp_category = dgii_data.get('l10n_do_dgii_category', '')
            self.l10n_do_rnc_temp_local_admin = dgii_data.get('l10n_do_dgii_local_admin', '')
            self.l10n_do_rnc_temp_vat_type = vat_type

            _logger.debug(f"Datos DGII obtenidos para RNC {validated_vat}: {dgii_data}")

            return {
                'warning': {
                    'title': _('RNC Encontrado en DGII'),
                    'message': _(
                        'Contribuyente: %s\n'
                        'Estado: %s\n'
                        'Actividad: %s\n\n'
                        'Use los botones para crear el contacto.'
                    ) % (
                        dgii_data.get('name', 'N/A'),
                        dgii_data.get('l10n_do_dgii_status', 'N/A'),
                        dgii_data.get('l10n_do_dgii_activity', 'N/A')
                    ),
                    'type': 'notification',
                }
            }
        else:
            return {
                'warning': {
                    'title': _('RNC No Encontrado'),
                    'message': _(
                        'No se encontró información en la DGII para el RNC/Cédula: %s. '
                        'Verifique que el número sea correcto.'
                    ) % validated_vat
                }
            }

    def action_create_partner_quick(self):
        """
        Crea el contacto rápidamente con los datos de la DGII y lo asigna a la factura.
        """
        self.ensure_one()

        if not self.l10n_do_rnc_search or not self.l10n_do_rnc_preview_name:
            raise UserError(_('Primero debe buscar un RNC/Cédula válido.'))

        # Limpiar y validar el RNC
        Partner = self.env['res.partner']
        clean_vat = Partner._clean_vat(self.l10n_do_rnc_search)
        validated_vat, vat_type = Partner._validate_rnc_format(clean_vat)

        if not validated_vat:
            raise UserError(_(
                'El RNC/Cédula ingresado no tiene un formato válido.'
            ))

        do_country = self.env.ref("base.do")

        # Verificar si ya existe
        existing_partner = self.env['res.partner'].search([
            ('vat', '=', validated_vat),
            ('country_id', '=', do_country.id),
        ], limit=1)

        if existing_partner:
            self.partner_id = existing_partner
            self._clear_rnc_search_fields()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Contacto Existente'),
                    'message': _('El contacto "%s" ya existe y ha sido seleccionado.') % existing_partner.name,
                    'type': 'info',
                    'sticky': False,
                }
            }

        # Determinar tipo de contribuyente basado en el tipo de VAT
        vat_type = self.l10n_do_rnc_temp_vat_type or vat_type
        if vat_type == 'cedula':
            company_type = 'person'
            is_company = False
            tax_payer_type = 'non_payer'
        else:
            company_type = 'company'
            is_company = True
            tax_payer_type = 'taxpayer'

        # Crear el contacto
        partner_vals = {
            'name': self.l10n_do_rnc_preview_name,
            'vat': validated_vat,
            'country_id': do_country.id,
            'company_type': company_type,
            'is_company': is_company,
            'l10n_do_dgii_tax_payer_type': tax_payer_type,
            'l10n_do_dgii_name': self.l10n_do_rnc_preview_name,
            'l10n_do_dgii_status': self.l10n_do_rnc_preview_status,
            'l10n_do_dgii_activity': self.l10n_do_rnc_preview_activity,
            'l10n_do_dgii_commercial_name': self.l10n_do_rnc_temp_commercial_name,
            'l10n_do_dgii_payment_regime': self.l10n_do_rnc_temp_payment_regime,
            'l10n_do_dgii_category': self.l10n_do_rnc_temp_category,
            'l10n_do_dgii_local_admin': self.l10n_do_rnc_temp_local_admin,
            'l10n_do_dgii_last_update': fields.Datetime.now(),
        }

        partner = self.env['res.partner'].create(partner_vals)
        _logger.debug(f"Contacto creado desde factura: {partner.name} (ID: {partner.id})")

        # Asignar a la factura
        self.partner_id = partner
        self._clear_rnc_search_fields()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Contacto Creado'),
                'message': _('El contacto "%s" ha sido creado y asignado.') % partner.name,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_create_partner_and_edit(self):
        """
        Crea el contacto con los datos de la DGII y abre el formulario para editar.
        """
        self.ensure_one()

        if not self.l10n_do_rnc_search or not self.l10n_do_rnc_preview_name:
            raise UserError(_('Primero debe buscar un RNC/Cédula válido.'))

        # Limpiar y validar el RNC
        Partner = self.env['res.partner']
        clean_vat = Partner._clean_vat(self.l10n_do_rnc_search)
        validated_vat, vat_type = Partner._validate_rnc_format(clean_vat)

        if not validated_vat:
            raise UserError(_(
                'El RNC/Cédula ingresado no tiene un formato válido.'
            ))

        do_country = self.env.ref("base.do")

        # Verificar si ya existe
        existing_partner = self.env['res.partner'].search([
            ('vat', '=', validated_vat),
            ('country_id', '=', do_country.id),
        ], limit=1)

        if existing_partner:
            self.partner_id = existing_partner
            self._clear_rnc_search_fields()
            # Abrir formulario del contacto existente
            return {
                'name': _('Editar Contacto'),
                'type': 'ir.actions.act_window',
                'res_model': 'res.partner',
                'res_id': existing_partner.id,
                'view_mode': 'form',
                'target': 'new',
            }

        # Determinar tipo de contribuyente basado en el tipo de VAT
        vat_type = self.l10n_do_rnc_temp_vat_type or vat_type
        if vat_type == 'cedula':
            company_type = 'person'
            is_company = False
            tax_payer_type = 'non_payer'
        else:
            company_type = 'company'
            is_company = True
            tax_payer_type = 'taxpayer'

        # Crear el contacto
        partner_vals = {
            'name': self.l10n_do_rnc_preview_name,
            'vat': validated_vat,
            'country_id': do_country.id,
            'company_type': company_type,
            'is_company': is_company,
            'l10n_do_dgii_tax_payer_type': tax_payer_type,
            'l10n_do_dgii_name': self.l10n_do_rnc_preview_name,
            'l10n_do_dgii_status': self.l10n_do_rnc_preview_status,
            'l10n_do_dgii_activity': self.l10n_do_rnc_preview_activity,
            'l10n_do_dgii_commercial_name': self.l10n_do_rnc_temp_commercial_name,
            'l10n_do_dgii_payment_regime': self.l10n_do_rnc_temp_payment_regime,
            'l10n_do_dgii_category': self.l10n_do_rnc_temp_category,
            'l10n_do_dgii_local_admin': self.l10n_do_rnc_temp_local_admin,
            'l10n_do_dgii_last_update': fields.Datetime.now(),
        }

        partner = self.env['res.partner'].create(partner_vals)
        _logger.debug(f"Contacto creado desde factura (editar): {partner.name} (ID: {partner.id})")

        # Asignar a la factura
        self.partner_id = partner
        self._clear_rnc_search_fields()

        # Abrir el formulario del contacto para editar
        return {
            'name': _('Editar Contacto'),
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'res_id': partner.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_create_partner_from_rnc(self):
        """
        Acción para abrir el wizard de creación de contacto desde RNC (modo completo).
        """
        self.ensure_one()

        if not self.l10n_do_rnc_search:
            raise UserError(_('Primero debe ingresar un RNC/Cédula en el campo de búsqueda.'))

        # Limpiar y validar el RNC
        Partner = self.env['res.partner']
        clean_vat = Partner._clean_vat(self.l10n_do_rnc_search)
        validated_vat, vat_type = Partner._validate_rnc_format(clean_vat)

        if not validated_vat:
            raise UserError(_(
                'El RNC/Cédula ingresado no tiene un formato válido. '
                'Debe ser un RNC de 9 dígitos o una Cédula de 11 dígitos.'
            ))

        do_country = self.env.ref("base.do")

        # Verificar si ya existe
        existing_partner = self.env['res.partner'].search([
            ('vat', '=', validated_vat),
            ('country_id', '=', do_country.id),
        ], limit=1)

        if existing_partner:
            self.partner_id = existing_partner
            self._clear_rnc_search_fields()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Contacto Existente'),
                    'message': _('El contacto "%s" ya existe y ha sido seleccionado.') % existing_partner.name,
                    'type': 'info',
                    'sticky': False,
                }
            }

        # Usar datos ya consultados o consultar de nuevo
        if self.l10n_do_rnc_preview_name:
            dgii_data = {
                'name': self.l10n_do_rnc_preview_name,
                'l10n_do_dgii_status': self.l10n_do_rnc_preview_status,
                'l10n_do_dgii_activity': self.l10n_do_rnc_preview_activity,
                'l10n_do_dgii_commercial_name': self.l10n_do_rnc_temp_commercial_name,
                'l10n_do_dgii_payment_regime': self.l10n_do_rnc_temp_payment_regime,
                'l10n_do_dgii_category': self.l10n_do_rnc_temp_category,
                'l10n_do_dgii_local_admin': self.l10n_do_rnc_temp_local_admin,
            }
            vat_type = self.l10n_do_rnc_temp_vat_type or vat_type
        else:
            # Consultar la DGII
            dgii_data = Partner._query_dgii_rnc(validated_vat)
            if not dgii_data or not dgii_data.get('name'):
                raise UserError(_(
                    'No se pudo obtener información de la DGII para el RNC/Cédula: %s. '
                    'Puede crear el contacto manualmente.'
                ) % validated_vat)

        # Abrir wizard con los datos
        return {
            'name': _('Crear Contacto desde RNC'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_do.partner.from.rnc.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_vat': validated_vat,
                'default_name': dgii_data.get('name', ''),
                'default_l10n_do_dgii_name': dgii_data.get('name', ''),
                'default_l10n_do_dgii_commercial_name': dgii_data.get('l10n_do_dgii_commercial_name', ''),
                'default_l10n_do_dgii_status': dgii_data.get('l10n_do_dgii_status', ''),
                'default_l10n_do_dgii_payment_regime': dgii_data.get('l10n_do_dgii_payment_regime', ''),
                'default_l10n_do_dgii_activity': dgii_data.get('l10n_do_dgii_activity', ''),
                'default_l10n_do_dgii_category': dgii_data.get('l10n_do_dgii_category', ''),
                'default_l10n_do_dgii_local_admin': dgii_data.get('l10n_do_dgii_local_admin', ''),
                'default_move_id': self.id,
                'default_vat_type': vat_type,
            },
        }

    def _clear_rnc_search_fields(self):
        """Limpia los campos de búsqueda de RNC."""
        self.l10n_do_rnc_search = False
        self.l10n_do_rnc_preview_name = False
        self.l10n_do_rnc_preview_status = False
        self.l10n_do_rnc_preview_activity = False
        self.l10n_do_rnc_data_ready = False
        self.l10n_do_rnc_temp_commercial_name = False
        self.l10n_do_rnc_temp_payment_regime = False
        self.l10n_do_rnc_temp_category = False
        self.l10n_do_rnc_temp_local_admin = False
        self.l10n_do_rnc_temp_vat_type = False

    def action_search_rnc_dgii(self):
        """
        Acción para buscar RNC en la DGII (botón alternativo).
        """
        self.ensure_one()

        if not self.l10n_do_rnc_search:
            raise UserError(_('Primero debe ingresar un RNC/Cédula en el campo de búsqueda.'))

        # Disparar el onchange manualmente
        result = self._onchange_rnc_search()

        if self.l10n_do_rnc_preview_name:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Consulta DGII'),
                    'message': _(
                        'Contribuyente: %s\nEstado: %s'
                    ) % (self.l10n_do_rnc_preview_name, self.l10n_do_rnc_preview_status or 'N/A'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        return result
