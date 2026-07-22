from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrPayrollStructureType(models.Model):
    _inherit = 'hr.payroll.structure.type'

    is_main_type = fields.Boolean(
        string='Principal',
        help='Marcar como tipo principal. Este será seleccionado automáticamente en contratos nuevos.'
    )

    @api.constrains('is_main_type')
    def _check_single_main_type(self):
        """Asegurar que solo haya un tipo de estructura salarial principal"""
        for record in self:
            if record.is_main_type:
                other_main = self.search([
                    ('is_main_type', '=', True),
                    ('id', '!=', record.id)
                ])
                if other_main:
                    raise ValidationError(_(
                        'Solo puede haber un tipo de estructura salarial principal. '
                        'El tipo "%s" ya está marcado como principal.'
                    ) % other_main[0].name)

    @api.model_create_multi
    def create(self, vals_list):
        """Override create para manejar el tipo principal"""
        records = super().create(vals_list)
        for record in records:
            if record.is_main_type:
                record._ensure_single_main_type()
        return records

    def write(self, vals):
        """Override write para manejar el tipo principal"""
        result = super().write(vals)
        if 'is_main_type' in vals and vals['is_main_type']:
            for record in self:
                record._ensure_single_main_type()
        return result

    def _ensure_single_main_type(self):
        """Asegurar que solo haya un tipo principal"""
        if self.is_main_type:
            other_main = self.search([
                ('is_main_type', '=', True),
                ('id', '!=', self.id)
            ])
            if other_main:
                other_main.write({'is_main_type': False})

    @api.model
    def get_main_structure_type(self):
        """Obtener el tipo de estructura salarial principal"""
        main_type = self.search([('is_main_type', '=', True)], limit=1)
        return main_type if main_type else self.search([], limit=1)