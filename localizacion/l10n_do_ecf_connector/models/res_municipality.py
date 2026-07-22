from odoo import api, models, fields


class Municipality(models.Model):
    _name = 'res.municipality'
    _description = 'Municipality'
    _order = 'ecf_code'

    name = fields.Char('Name', required=True)
    ecf_code = fields.Char('Code', help='El código del municipio', size=6, required=True)
    country_id = fields.Many2one('res.country', string='Country', required=True)

    def _valid_field_parameter(self, field, name):
        return name == 'size' or super(Municipality, self)._valid_field_parameter(field, name)
    state_id = fields.Many2one('res.country.state', 'State', domain="[('country_id', '=', country_id)]")

    _name_code_uniq = models.Constraint(
        'unique(state_id, ecf_code)',
        '¡El código del municipio debe ser único por provincia!',
    )

    @api.model
    def _name_search(self, search_value, args=None, operator='ilike', limit=100, order=None):
        """ search in name, code and category"""
        args = args or []
        # search in name and code
        domain = args + ['|', ('name', operator, search_value), ('ecf_code', operator, search_value)]
        return self._search(domain, limit=limit, order=order)
