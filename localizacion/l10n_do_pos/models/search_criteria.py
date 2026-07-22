# -*- coding: utf-8 -*-
# © 2018 Kevin Jiménez <kevinjimenezlorenzo@gmail.com>

from odoo import models, fields


class PosSearchCriteria(models.Model):
    _name = "pos.search_criteria"
    _description = "Criterias used to search invoices"

    name = fields.Char()
    criteria = fields.Char()
    # MODIFICADO: Arturo Diaz Lora - 2026-03-14 10:00
    # Razón: Agregar company_id para soporte multi-company (opcional para datos precargados)
    company_id = fields.Many2one('res.company')