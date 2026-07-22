# -*- coding: utf-8 -*-
# © 2019 Kolushov Alexandr <https://it-projects.info/team/KolushovAlexandr>

from odoo.addons.point_of_sale.wizard.pos_box import PosBox
from odoo import api


class PosBoxOut(PosBox):
    _inherit = "cash.box.out"

    @api.model
    def default_get(self, fields):
        res = super(PosBoxOut, self).default_get(fields)
        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')

        if active_model == 'pos.session' and active_id:
            pos_session = self.env[active_model].browse(active_id)
            date = pos_session.start_at
            res.update({
                'name': pos_session.config_id.name + ' ' + str(date)
            })
        return res