# -*- coding: utf-8 -*-
from odoo import models, api, fields, _


class PosSession(models.Model):
    _inherit = 'pos.session'

    # ==========================================
    # Arturo Diaz Lora - 2025-12-01 21:35
    # Corrección: Las líneas de efectivo del POS deben usar la fecha de inicio
    # de la sesión, no la fecha del cierre, para que coincidan con las ventas
    # ==========================================

    def _get_combine_statement_line_vals(self, journal, amount, payment_method):
        """
        Override para usar la fecha de inicio de la sesión POS en lugar de la fecha actual.

        Esto corrige el problema donde los movimientos de efectivo aparecen con la fecha
        de cierre de la sesión en lugar de la fecha de las ventas.

        Autor: Arturo Diaz Lora
        Fecha: 2025-12-01 21:35
        Razón: Las líneas de efectivo deben coincidir con la fecha de la sesión POS

        MODIFICADO: Arturo Diaz Lora - 2026-01-23
        Razón: Corregido error 'can't adapt type account.journal' - el parámetro
               journal es un objeto, debe usarse journal.id
        """
        # Usar la fecha de inicio de la sesión si existe, sino la fecha actual
        session_date = self.start_at.date() if self.start_at else fields.Date.context_today(self)

        # Obtener valores de monto del método original
        amount_values = self._prepare_statement_line_amount_values(journal, amount)

        return {
            'date': session_date,
            'payment_ref': self.name,
            'pos_session_id': self.id,
            'journal_id': journal.id,
            'counterpart_account_id': self._get_receivable_account(payment_method).id,
            **amount_values
        }

    def _loader_params_custom_data(self):
        """
        Agrega datos personalizados de República Dominicana al POS.
        Incluye alertas de secuencias fiscales.

        Autor: Claude - Fecha: 2025-11-28
        Razón: Enviar alertas de secuencias fiscales al POS al cargar
        """
        result = {}

        # Obtener alertas de secuencias fiscales
        FiscalSequence = self.env['account.fiscal.sequence']
        warnings = FiscalSequence.get_sequences_warnings(self.config_id.company_id.id)

        result['fiscal_sequence_warnings'] = warnings
        result['has_fiscal_warnings'] = len(warnings) > 0

        return result

    def _pos_ui_models_data(self):
        """Override to add fiscal sequence warnings to POS data"""
        result = super()._pos_ui_models_data()

        # Agregar datos personalizados de RD
        custom_data = self._loader_params_custom_data()
        result['l10n_do_data'] = custom_data

        return result

    def _get_pos_ui_res_company(self, company_ids):
        """Override to include Dominican Republic specific fields for POS UI

        Autor: Arturo Diaz Lora
        Fecha: 2025-11-24 09:25
        Razón: Agregar l10n_do_ecf_activated para que el POS sepa si la facturación
               electrónica está activada y mostrar/ocultar el popup de código de modificación
        """
        result = super()._get_pos_ui_res_company(company_ids)

        # Extend with Dominican specific fields
        for company_data in result:
            company = self.env['res.company'].browse(company_data['id'])
            company_data.update({
                'company_address': company.company_address if hasattr(company, 'company_address') else '',
                'l10n_do_ncf_exp_date': company.l10n_do_ncf_exp_date if hasattr(company, 'l10n_do_ncf_exp_date') else False,
                'l10n_do_ecf_activated': company.l10n_do_ecf_activated if hasattr(company, 'l10n_do_ecf_activated') else False,
            })

        return result

    def _get_pos_ui_res_partner(self, partner_ids):
        """Override to include Dominican Republic specific fields for POS UI"""
        result = super()._get_pos_ui_res_partner(partner_ids)

        # Extend with Dominican specific fields
        for partner_data in result:
            partner = self.env['res.partner'].browse(partner_data['id'])
            partner_data.update({
                'l10n_do_dgii_tax_payer_type': partner.l10n_do_dgii_tax_payer_type if hasattr(partner, 'l10n_do_dgii_tax_payer_type') else 'non_payer'
            })

        return result
