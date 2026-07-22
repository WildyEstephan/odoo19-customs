# -*- coding: utf-8 -*-
from odoo import models, fields

# CAMPOS ESPECIALES DESHABILITADOS - 2025-09-14
# Funcionalidad comentada a solicitud del usuario
"""
class CustomFields(models.Model):
    _name = 'l10n_do.custom.fields'
    _description = 'Campos personalizados para facturación electrónica DGII'

    move_id = fields.Many2one(
        'account.move',
        string=u'Movimiento',
    )
    move_line_id = fields.Many2one(
        'account.move.line',
        string=u'Línea de movimiento',
    )
    section = fields.Selection(
        [
            ("IdDoc", "IdDoc"),
            ("Emisor", "Emisor"),
            ("Comprador", "Comprador"),
            ("Totales", "Totales"),
            ("Item", "Item"),
            ("ItemRetencion", "Item / Retencion"),
            ("ItemDescuento", "Item / Descuento"),
            ("ItemRecargo", "Item / Subrecargo"),
            ("DescuentoORecargo", "DescuentoORecargo"),
        ],
        string='Sección',
    )
    name = fields.Char(
        string=u'Nombre en el XML'
    )
    value = fields.Char(
        string=u'Valor en el XML'
    )
    delete = fields.Boolean(
        string=u"Eliminar",
        default=False,
    )
"""

# Modelo stub para mantener compatibilidad
class CustomFields(models.Model):
    _name = 'l10n_do.custom.fields'
    _description = 'Campos personalizados deshabilitados'

    # Campos mínimos para evitar errores
    move_id = fields.Many2one('account.move', string='Movimiento')
    name = fields.Char(string='Nombre')
    value = fields.Char(string='Valor')

    def read(self, fields=None, load='_classic_read'):
        # Siempre retornar lista vacía
        return []

    def search(self, args, offset=0, limit=None, order=None, count=False):
        # Siempre retornar recordset vacío
        if count:
            return 0
        return self.browse()