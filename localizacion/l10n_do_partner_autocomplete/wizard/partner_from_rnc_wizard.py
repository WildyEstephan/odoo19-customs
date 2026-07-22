import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PartnerFromRNCWizard(models.TransientModel):
    _name = 'l10n_do.partner.from.rnc.wizard'
    _description = 'Crear Contacto desde RNC'

    # Campos básicos
    vat = fields.Char(
        string="RNC/Cédula",
        required=True,
        readonly=True,
    )
    vat_type = fields.Selection(
        selection=[
            ('rnc', 'RNC (Empresa)'),
            ('cedula', 'Cédula (Persona)'),
        ],
        string="Tipo",
        readonly=True,
    )
    name = fields.Char(
        string="Nombre",
        required=True,
    )
    company_type = fields.Selection(
        selection=[
            ('company', 'Empresa'),
            ('person', 'Persona'),
        ],
        string="Tipo de Contacto",
        default='company',
        required=True,
    )

    # Campos de la DGII
    l10n_do_dgii_name = fields.Char(
        string="Nombre/Razón Social (DGII)",
        readonly=True,
    )
    l10n_do_dgii_commercial_name = fields.Char(
        string="Nombre Comercial",
    )
    l10n_do_dgii_status = fields.Char(
        string="Estado (DGII)",
        readonly=True,
    )
    l10n_do_dgii_payment_regime = fields.Char(
        string="Régimen de Pagos",
        readonly=True,
    )
    l10n_do_dgii_activity = fields.Char(
        string="Actividad Económica",
        readonly=True,
    )
    l10n_do_dgii_category = fields.Char(
        string="Categoría",
        readonly=True,
    )
    l10n_do_dgii_local_admin = fields.Char(
        string="Administración Local",
        readonly=True,
    )

    # Campos adicionales opcionales
    email = fields.Char(string="Correo Electrónico")
    phone = fields.Char(string="Teléfono")
    mobile = fields.Char(string="Móvil")
    street = fields.Char(string="Dirección")
    city = fields.Char(string="Ciudad")

    # Tipo de contribuyente DGII
    l10n_do_dgii_tax_payer_type = fields.Selection(
        selection=[
            ('taxpayer', 'Contribuyente'),
            ('non_payer', 'No Contribuyente'),
            ('nonprofit', 'Sin fines de lucro'),
            ('special', 'Régimen Especial'),
            ('governmental', 'Gubernamental'),
            ('foreigner', 'Extranjero'),
        ],
        string="Tipo de Contribuyente",
        default='taxpayer',
        required=True,
    )

    # Referencia a la factura (opcional)
    move_id = fields.Many2one(
        'account.move',
        string="Factura",
    )

    @api.onchange('vat_type')
    def _onchange_vat_type(self):
        """Establece el tipo de contacto basado en el tipo de VAT."""
        if self.vat_type == 'cedula':
            self.company_type = 'person'
        else:
            self.company_type = 'company'

    @api.model
    def default_get(self, fields_list):
        """Establece valores por defecto basados en el contexto."""
        res = super().default_get(fields_list)

        # Si el tipo de VAT es cédula, es persona
        if res.get('vat_type') == 'cedula':
            res['company_type'] = 'person'
            res['l10n_do_dgii_tax_payer_type'] = 'non_payer'
        else:
            res['company_type'] = 'company'
            res['l10n_do_dgii_tax_payer_type'] = 'taxpayer'

        return res

    def action_create_partner(self):
        """
        Crea el contacto con los datos de la DGII y lo asigna a la factura.
        """
        self.ensure_one()

        # Verificar que no exista ya
        existing_partner = self.env['res.partner'].search([
            ('vat', '=', self.vat),
            ('country_id', '=', self.env.ref("base.do").id),
        ], limit=1)

        if existing_partner:
            # Si existe, usarlo
            partner = existing_partner
            _logger.debug(f"Usando contacto existente: {partner.name} (ID: {partner.id})")
        else:
            # Crear el contacto
            partner_vals = {
                'name': self.name,
                'vat': self.vat,
                'country_id': self.env.ref("base.do").id,
                'company_type': self.company_type,
                'is_company': self.company_type == 'company',
                'l10n_do_dgii_tax_payer_type': self.l10n_do_dgii_tax_payer_type,
                # Campos de la DGII
                'l10n_do_dgii_name': self.l10n_do_dgii_name,
                'l10n_do_dgii_commercial_name': self.l10n_do_dgii_commercial_name,
                'l10n_do_dgii_status': self.l10n_do_dgii_status,
                'l10n_do_dgii_payment_regime': self.l10n_do_dgii_payment_regime,
                'l10n_do_dgii_activity': self.l10n_do_dgii_activity,
                'l10n_do_dgii_category': self.l10n_do_dgii_category,
                'l10n_do_dgii_local_admin': self.l10n_do_dgii_local_admin,
                'l10n_do_dgii_last_update': fields.Datetime.now(),
            }

            # Agregar campos opcionales si están llenos
            if self.email:
                partner_vals['email'] = self.email
            if self.phone:
                partner_vals['phone'] = self.phone
            if self.mobile:
                partner_vals['mobile'] = self.mobile
            if self.street:
                partner_vals['street'] = self.street
            if self.city:
                partner_vals['city'] = self.city

            partner = self.env['res.partner'].create(partner_vals)
            _logger.debug(f"Contacto creado: {partner.name} (ID: {partner.id})")

        # Asignar a la factura si existe
        if self.move_id:
            self.move_id.write({
                'partner_id': partner.id,
                'l10n_do_rnc_search': False,
                'l10n_do_rnc_preview_name': False,
                'l10n_do_rnc_preview_status': False,
                'l10n_do_rnc_preview_activity': False,
            })
            _logger.debug(f"Contacto {partner.name} asignado a factura {self.move_id.name}")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Contacto Creado'),
                'message': _('El contacto "%s" ha sido creado y asignado a la factura.') % partner.name,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

    def action_create_and_edit_partner(self):
        """
        Crea el contacto y abre el formulario para editar.
        """
        self.ensure_one()

        # Verificar que no exista ya
        existing_partner = self.env['res.partner'].search([
            ('vat', '=', self.vat),
            ('country_id', '=', self.env.ref("base.do").id),
        ], limit=1)

        if existing_partner:
            partner = existing_partner
        else:
            # Crear el contacto
            partner_vals = {
                'name': self.name,
                'vat': self.vat,
                'country_id': self.env.ref("base.do").id,
                'company_type': self.company_type,
                'is_company': self.company_type == 'company',
                'l10n_do_dgii_tax_payer_type': self.l10n_do_dgii_tax_payer_type,
                # Campos de la DGII
                'l10n_do_dgii_name': self.l10n_do_dgii_name,
                'l10n_do_dgii_commercial_name': self.l10n_do_dgii_commercial_name,
                'l10n_do_dgii_status': self.l10n_do_dgii_status,
                'l10n_do_dgii_payment_regime': self.l10n_do_dgii_payment_regime,
                'l10n_do_dgii_activity': self.l10n_do_dgii_activity,
                'l10n_do_dgii_category': self.l10n_do_dgii_category,
                'l10n_do_dgii_local_admin': self.l10n_do_dgii_local_admin,
                'l10n_do_dgii_last_update': fields.Datetime.now(),
            }

            # Agregar campos opcionales si están llenos
            if self.email:
                partner_vals['email'] = self.email
            if self.phone:
                partner_vals['phone'] = self.phone
            if self.mobile:
                partner_vals['mobile'] = self.mobile
            if self.street:
                partner_vals['street'] = self.street
            if self.city:
                partner_vals['city'] = self.city

            partner = self.env['res.partner'].create(partner_vals)

        # Asignar a la factura si existe
        if self.move_id:
            self.move_id.write({
                'partner_id': partner.id,
                'l10n_do_rnc_search': False,
                'l10n_do_rnc_preview_name': False,
                'l10n_do_rnc_preview_status': False,
                'l10n_do_rnc_preview_activity': False,
            })

        # Abrir el formulario del contacto para editar
        return {
            'name': _('Editar Contacto'),
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'res_id': partner.id,
            'view_mode': 'form',
            'target': 'current',
        }
