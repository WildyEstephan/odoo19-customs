# -*- coding: utf-8 -*-
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class AccountJournal(models.Model):
    _inherit = 'account.journal'

    @api.model
    def _setup_l10n_do_edi_formats(self):
        """Configurar automáticamente formatos EDI para República Dominicana"""
        edi_format = self.env['account.edi.format'].search([
            ('code', '=', 'dgii_ecf')
        ], limit=1)
        
        if not edi_format:
            _logger.warning("No se encontró el formato EDI 'dgii_ecf'")
            return
        
        # Buscar journals de ventas y compras en compañías de RD con ECF activado y modo automático
        journals = self.search([
            ('type', 'in', ['sale', 'purchase']),
            ('company_id.country_id.code', '=', 'DO'),
            ('company_id.l10n_do_ecf_activated', '=', True),
            ('company_id.l10n_do_ecf_send_mode', '=', 'automatic')
        ])
        
        count = 0
        for journal in journals:
            if edi_format not in journal.edi_format_ids:
                journal.write({
                    'edi_format_ids': [(4, edi_format.id)]
                })
                count += 1
                _logger.info(f"Formato EDI 'dgii_ecf' agregado al journal {journal.name} (ID: {journal.id})")
        
        _logger.info(f"Configuración EDI completada: {count} journals actualizados")
        return count

    @api.model
    def _cleanup_edi_formats_for_manual_mode(self):
        """Remover formatos EDI de journals cuando el modo es manual"""
        edi_format = self.env['account.edi.format'].search([
            ('code', '=', 'dgii_ecf')
        ], limit=1)

        if not edi_format:
            return 0

        # Buscar journals con ECF activado pero en modo manual
        journals = self.search([
            ('type', 'in', ['sale', 'purchase']),
            ('company_id.country_id.code', '=', 'DO'),
            ('company_id.l10n_do_ecf_activated', '=', True),
            ('company_id.l10n_do_ecf_send_mode', '=', 'manual'),
            ('edi_format_ids', 'in', [edi_format.id])
        ])

        count = 0
        for journal in journals:
            journal.edi_format_ids = [(3, edi_format.id)]
            count += 1
            _logger.info(f"Formato EDI 'dgii_ecf' removido de journal {journal.name} (modo manual)")

        _logger.info(f"Limpieza EDI completada: {count} journals actualizados a modo manual")
        return count

    @api.model_create_multi
    def create(self, vals_list):
        """Override create para configurar automáticamente EDI en journals nuevos"""
        journals = super().create(vals_list)

        # Procesar cada journal creado
        for journal in journals:
            # Si es un journal de ventas/compras para RD con ECF activado y modo automático, configurar EDI
            if (journal.type in ['sale', 'purchase'] and
                journal.company_id.country_id.code == 'DO' and
                journal.company_id.l10n_do_ecf_activated and
                getattr(journal.company_id, 'l10n_do_ecf_send_mode', 'manual') == 'automatic'):

                edi_format = self.env['account.edi.format'].search([
                    ('code', '=', 'dgii_ecf')
                ], limit=1)

                if edi_format and edi_format not in journal.edi_format_ids:
                    journal.write({
                        'edi_format_ids': [(4, edi_format.id)]
                    })
                    _logger.info(f"Formato EDI 'dgii_ecf' auto-configurado en nuevo journal {journal.name}")

        return journals

    def write(self, vals):
        """Override write para reconfigurar EDI si cambia la configuración de ECF"""
        result = super().write(vals)
        
        # Si se activó ECF en la compañía, configurar EDI
        if ('company_id' in vals or any(key.startswith('l10n_do_ecf') for key in vals.keys())):
            for journal in self:
                if (journal.type in ['sale', 'purchase'] and
                    journal.company_id.country_id.code == 'DO' and
                    journal.company_id.l10n_do_ecf_activated and
                    journal.company_id.l10n_do_ecf_send_mode == 'automatic'):
                    
                    edi_format = self.env['account.edi.format'].search([
                        ('code', '=', 'dgii_ecf')
                    ], limit=1)
                    
                    if edi_format and edi_format not in journal.edi_format_ids:
                        journal.edi_format_ids = [(4, edi_format.id)]
                        _logger.info(f"Formato EDI 'dgii_ecf' reconfigurado en journal {journal.name}")

                # Si el modo cambió a manual, remover el formato EDI automático
                elif (journal.type in ['sale', 'purchase'] and
                      journal.company_id.country_id.code == 'DO' and
                      journal.company_id.l10n_do_ecf_activated and
                      journal.company_id.l10n_do_ecf_send_mode == 'manual'):

                    edi_format = self.env['account.edi.format'].search([
                        ('code', '=', 'dgii_ecf')
                    ], limit=1)

                    if edi_format and edi_format in journal.edi_format_ids:
                        journal.edi_format_ids = [(3, edi_format.id)]
                        _logger.info(f"Formato EDI 'dgii_ecf' removido del journal {journal.name} (modo manual)")
        
        return result
