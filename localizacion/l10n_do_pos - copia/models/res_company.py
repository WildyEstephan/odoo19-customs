# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = "res.company"

    company_address = fields.Char(compute='_compute_company_address', string='Complete Address')

    @api.depends("street", "street2", "city", "state_id", "country_id")
    def _compute_company_address(self):
        for company in self:
            company.company_address = company._display_address_company()

    def _display_address_company(self):
        address_company = ""
        address_company += self.street and self.street + ', ' or ''
        address_company += self.street2 and self.street2 + ', ' or ''
        address_company += self.city and self.city + ', ' or ''
        address_company += self.state_id and self.state_id.name + ', ' or ''
        address_company += self.country_id and self.country_id.name + ', ' or ''
        return address_company
    
    def _get_pos_ui_res_company(self, company_ids):
        """Override to include additional Dominican fields in POS UI"""
        result = super()._get_pos_ui_res_company(company_ids)
        
        # Agregar campos adicionales necesarios para el recibo dominicano
        for company_data in result:
            company = self.browse(company_data['id'])
            company_data.update({
                'company_address': company.company_address,
                'street': company.street,
                'street2': company.street2,
                'city': company.city,
                'state_id': company.state_id.name if company.state_id else '',
                'country_id': company.country_id.name if company.country_id else '',
                'phone': company.phone,
                'email': company.email,
                'website': company.website,
                'vat': company.vat,
            })
        
        return result