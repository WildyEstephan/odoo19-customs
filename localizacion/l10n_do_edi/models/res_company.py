# -*- coding: utf-8 -*-
from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_do_ecf_activated = fields.Boolean(
        string='Activar e-CF (DGII)',
        default=False
    )
    l10n_do_pkcs12_file = fields.Binary(
        string='Archivo P12/PFX'
    )
    l10n_do_pkcs12_password = fields.Char(
        string='Contraseña P12'
    )
    l10n_do_ecf_environment = fields.Selection(
        [
            ("pre_certification", "Pre-Certificación"),
            ("certification", "Certificación"),
            ("production", "Producción"),
        ],
        default="pre_certification",
        string='Ambiente',
    )
    l10n_do_ecf_send_mode = fields.Selection(
        [
            ("automatic", "Automático (al confirmar factura)"),
            ("manual", "Manual (botón 'Enviar a DGII')"),
        ],
        string="Modo de envío a DGII",
        default="manual",
    )
    l10n_do_ecf_skip_license = fields.Boolean(
        string='Omitir validación de licencia ECF',
        default=False,
        help='Al activar esta opción se omitirá la validación de licencia para emitir ECF. '
             'Use solo si está seguro de que tiene una licencia válida.'
    )
    l10n_do_ecf_pos_auto_send = fields.Boolean(
        string='Envío automático desde POS',
        default=True,
        help='Las facturas generadas desde el POS se enviarán automáticamente a la DGII, '
             'independientemente del modo de envío general.'
    )
