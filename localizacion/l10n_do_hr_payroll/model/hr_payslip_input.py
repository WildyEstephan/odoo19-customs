# -*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class HrPayslipInput(models.Model):
    _inherit = 'hr.payslip.input'

    @api.onchange('input_type_id')
    def _onchange_input_type_id(self):
        """
        Llenar automáticamente el campo 'name' cuando se selecciona un input_type_id.
        Esto asegura que la descripción del input se muestre correctamente en la interfaz.
        """
        if self.input_type_id:
            self.name = self.input_type_id.name
