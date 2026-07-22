# -*- coding: utf-8 -*-
from odoo import models, fields, api

class DgiiResultWizard(models.TransientModel):
    _name = 'dgii.result.wizard'
    _description = 'Resultado del envío a DGII'

    message = fields.Text(string='Resultado', readonly=True)
    move_id = fields.Many2one('account.move', string='Factura', readonly=True)

    def action_close(self):
        """Cierra el wizard"""
        return {'type': 'ir.actions.act_window_close'}
    
    def action_download_xml(self):
        """Descarga el archivo XML si existe"""
        if self.move_id:
            # Buscar archivos adjuntos XML
            attachment = self.env['ir.attachment'].search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', self.move_id.id),
                ('name', 'ilike', '%.xml')
            ], limit=1)
            
            if attachment:
                return {
                    'type': 'ir.actions.act_url',
                    'url': f'/web/content/{attachment.id}?download=true',
                    'target': 'self',
                }
        return self.action_close()