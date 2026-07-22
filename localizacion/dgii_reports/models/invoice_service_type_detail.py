# Part of Domincana Premium.
# See LICENSE file for full copyright and licensing details.

import json

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class InvoiceServiceTypeDetail(models.Model):
    _name = "invoice.service.type.detail"
    _description = "Invoice Service Type Detail"

    name = fields.Char()
    code = fields.Char(size=2)
    parent_code = fields.Char()

    def _valid_field_parameter(self, field, name):
        return name == 'size' or super(InvoiceServiceTypeDetail, self)._valid_field_parameter(field, name)

    _code_unique = models.Constraint(
        'unique(code)',
        'Code must be unique',
    )

