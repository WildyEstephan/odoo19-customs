# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_do_ecf_activated = fields.Boolean(
        related='company_id.l10n_do_ecf_activated',
        readonly=False
    )
    l10n_do_pkcs12_file = fields.Binary(
        related='company_id.l10n_do_pkcs12_file',
        readonly=False
    )
    l10n_do_pkcs12_password = fields.Char(
        related='company_id.l10n_do_pkcs12_password',
        readonly=False
    )
    l10n_do_ecf_environment = fields.Selection(
        related="company_id.l10n_do_ecf_environment",
        readonly=False,
    )
    l10n_do_ecf_send_mode = fields.Selection(
        string="Modo de envío a DGII",
        related="company_id.l10n_do_ecf_send_mode",
        readonly=False,
    )
    l10n_do_ecf_skip_license = fields.Boolean(
        string='Omitir validación de licencia ECF',
        related='company_id.l10n_do_ecf_skip_license',
        readonly=False,
        help='Al activar esta opción se omitirá la validación de licencia para emitir ECF. '
             'Use solo si está seguro de que tiene una licencia válida.'
    )

    def debug_company_config(self):
        """Método para debuggear la configuración de la compañía"""
        company = self.env.company

        _logger.info("=== DEBUG CONFIGURACIÓN COMPAÑÍA ===")
        _logger.info(f"Compañía: {company.id} - {company.name}")
        _logger.info(f"País: {company.country_id.name if company.country_id else 'No definido'}")
        _logger.info(f"Código país: {company.country_id.code if company.country_id else 'No definido'}")
        _logger.info(f"l10n_do_ecf_activated: {company.l10n_do_ecf_activated}")
        _logger.info(f"l10n_do_ecf_send_mode: {company.l10n_do_ecf_send_mode}")
        _logger.info(f"l10n_do_ecf_environment: {company.l10n_do_ecf_environment}")
        _logger.info("====================================")

        # También verificar los valores en este objeto de configuración
        _logger.info("=== VALORES EN RES.CONFIG.SETTINGS ===")
        _logger.info(f"l10n_do_ecf_activated: {self.l10n_do_ecf_activated}")
        _logger.info(f"l10n_do_ecf_send_mode: {self.l10n_do_ecf_send_mode}")
        _logger.info(f"l10n_do_ecf_environment: {self.l10n_do_ecf_environment}")
        _logger.info("=====================================")

        # Verificar directamente en la base de datos
        self.env.cr.execute("SELECT l10n_do_ecf_send_mode, l10n_do_ecf_activated FROM res_company WHERE id = %s", (company.id,))
        db_result = self.env.cr.fetchone()
        _logger.info("=== VALORES EN BASE DE DATOS ===")
        _logger.info(f"DB l10n_do_ecf_send_mode: {db_result[0] if db_result else 'No encontrado'}")
        _logger.info(f"DB l10n_do_ecf_activated: {db_result[1] if db_result else 'No encontrado'}")
        _logger.info("================================")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Debug completado',
                'message': f'Config: {company.l10n_do_ecf_send_mode} | DB: {db_result[0] if db_result else "N/A"}',
                'type': 'success',
            }
        }

    def force_manual_mode(self):
        """Método para forzar manualmente el modo a 'manual'"""
        company = self.env.company
        _logger.info("=== FORZANDO MODO MANUAL ===")

        # Forzar directamente en la base de datos
        self.env.cr.execute("UPDATE res_company SET l10n_do_ecf_send_mode = 'manual' WHERE id = %s", (company.id,))
        self.env.cr.commit()

        # Limpiar caché
        company.invalidate_recordset()

        _logger.info(f"Modo forzado a manual para compañía {company.id}")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Modo forzado',
                'message': 'El modo se ha forzado a "Manual". Recarga la página.',
                'type': 'success',
            }
        }

    def setup_edi_formats(self):
        """Método para configurar manualmente los formatos EDI"""
        journal_model = self.env['account.journal']
        count = journal_model._setup_l10n_do_edi_formats()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Configuración EDI completada',
                'message': f'Se configuraron {count} journals con el formato EDI de DGII.',
                'type': 'success',
            }
        }

    def set_values(self):
        """Override para debuggear cuando se guardan los valores"""
        _logger.info("=== DEBUG GUARDANDO CONFIGURACIÓN ===")
        _logger.info(f"l10n_do_ecf_send_mode antes de guardar: {self.l10n_do_ecf_send_mode}")
        _logger.info(f"l10n_do_ecf_activated antes de guardar: {self.l10n_do_ecf_activated}")

        # Llamar al método padre primero
        result = super().set_values()

        # Forzar el guardado de los valores relacionados después del super()
        company = self.env.company

        # Verificar y forzar guardado si hay discrepancias
        if hasattr(self, 'l10n_do_ecf_send_mode') and company.l10n_do_ecf_send_mode != self.l10n_do_ecf_send_mode:
            company.write({'l10n_do_ecf_send_mode': self.l10n_do_ecf_send_mode})
            _logger.info(f"Forzado guardado l10n_do_ecf_send_mode: {self.l10n_do_ecf_send_mode}")

        if hasattr(self, 'l10n_do_ecf_activated') and company.l10n_do_ecf_activated != self.l10n_do_ecf_activated:
            company.write({'l10n_do_ecf_activated': self.l10n_do_ecf_activated})
            _logger.info(f"Forzado guardado l10n_do_ecf_activated: {self.l10n_do_ecf_activated}")

        if hasattr(self, 'l10n_do_ecf_environment') and company.l10n_do_ecf_environment != self.l10n_do_ecf_environment:
            company.write({'l10n_do_ecf_environment': self.l10n_do_ecf_environment})
            _logger.info(f"Forzado guardado l10n_do_ecf_environment: {self.l10n_do_ecf_environment}")

        if hasattr(self, 'l10n_do_pkcs12_file') and company.l10n_do_pkcs12_file != self.l10n_do_pkcs12_file:
            company.write({'l10n_do_pkcs12_file': self.l10n_do_pkcs12_file})
            _logger.info(f"Forzado guardado l10n_do_pkcs12_file: {'Sí' if self.l10n_do_pkcs12_file else 'No'}")

        if hasattr(self, 'l10n_do_pkcs12_password') and company.l10n_do_pkcs12_password != self.l10n_do_pkcs12_password:
            company.write({'l10n_do_pkcs12_password': self.l10n_do_pkcs12_password})
            _logger.info(f"Forzado guardado l10n_do_pkcs12_password: {'Sí' if self.l10n_do_pkcs12_password else 'No'}")

        if hasattr(self, 'l10n_do_ecf_skip_license') and company.l10n_do_ecf_skip_license != self.l10n_do_ecf_skip_license:
            company.write({'l10n_do_ecf_skip_license': self.l10n_do_ecf_skip_license})
            _logger.info(f"Forzado guardado l10n_do_ecf_skip_license: {self.l10n_do_ecf_skip_license}")

        # Configurar automáticamente formatos EDI si se activó ECF
        if hasattr(self, 'l10n_do_ecf_activated') and self.l10n_do_ecf_activated:
            self._setup_edi_formats_after_activation()

        # Verificar después de guardar
        company.invalidate_recordset()
        _logger.info(f"l10n_do_ecf_send_mode después de guardar: {company.l10n_do_ecf_send_mode}")
        _logger.info(f"l10n_do_ecf_activated después de guardar: {company.l10n_do_ecf_activated}")
        _logger.info("====================================")

        return result

    def _setup_edi_formats_after_activation(self):
        """Configurar formatos EDI después de activar ECF"""
        try:
            journal_model = self.env['account.journal']
            count = journal_model._setup_l10n_do_edi_formats()
            _logger.info(f"Configuración EDI completada tras activación: {count} journals configurados")
        except Exception as e:
            _logger.error(f"Error configurando formatos EDI tras activación: {e}")

    @api.model
    def get_values(self):
        """Override para asegurar valores correctos"""
        res = super().get_values()
        company = self.env.company

        # Asegurar que los valores están sincronizados
        res.update({
            'l10n_do_ecf_activated': company.l10n_do_ecf_activated,
            'l10n_do_ecf_send_mode': company.l10n_do_ecf_send_mode,
            'l10n_do_ecf_environment': company.l10n_do_ecf_environment,
            'l10n_do_pkcs12_file': company.l10n_do_pkcs12_file,
            'l10n_do_pkcs12_password': company.l10n_do_pkcs12_password,
            'l10n_do_ecf_skip_license': company.l10n_do_ecf_skip_license,
        })

        return res
