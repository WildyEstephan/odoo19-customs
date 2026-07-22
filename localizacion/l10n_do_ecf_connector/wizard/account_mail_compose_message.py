
from odoo import models, fields, api, _


class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'

    @api.model
    def generate_email_for_composer(self, template_id, res_ids, fields=None):
        res_values = super(MailComposeMessage, self).generate_email_for_composer(template_id, res_ids, fields=fields)
        template = self.env['mail.template'].with_context(tpl_partners_only=True).browse(template_id)
        if template.model_id.model == 'account.move':
            invoice_ids = self.env[template.model_id.model].browse(res_ids)
            for i in invoice_ids:
                if not 'attachments' in res_values[i.id]:
                    res_values[i.id]['attachments'] = []
                if i.ecf_id and i.ecf_id.xml_file and not i.ecf_id.is_rfce:
                    name = i.ecf_id.xml_file_name
                    res_values[i.id]['attachments'].append((name, i.ecf_id.xml_file))
                if i.ecf_id and i.ecf_id.xml_dgii_file and not i.ecf_id.is_rfce:
                    name = i.ecf_id.xml_dgii_file_name
                    res_values[i.id]['attachments'].append((name, i.ecf_id.xml_dgii_file))

        return res_values
