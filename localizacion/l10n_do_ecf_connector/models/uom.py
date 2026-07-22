from odoo import api, fields, models, _


class UOM(models.Model):
    _inherit = "uom.uom"
    # _sql_constraints = [
    #     (
    #         'ecf_code_unique', 'unique (ecf_code)',
    #         'ECF Code must be unique')
    # ]

    ecf_code = fields.Char(string="e-CF Code", size=2, help="DGII Code")

    def _valid_field_parameter(self, field, name):
        return name == 'size' or super(UOM, self)._valid_field_parameter(field, name)
