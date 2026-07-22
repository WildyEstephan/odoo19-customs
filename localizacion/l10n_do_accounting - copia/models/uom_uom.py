# -*- coding: utf-8 -*-

from odoo import models, fields


class Uom(models.Model):
    _inherit = "uom.uom"

    code = fields.Char(string='Código')