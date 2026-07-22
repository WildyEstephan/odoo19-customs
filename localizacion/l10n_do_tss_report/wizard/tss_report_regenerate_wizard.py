#  Copyright (c) 2018 - Indexa SRL. (https://www.indexa.do) <info@indexa.do>
#  See LICENSE file for full licensing details.

from odoo import models, fields, api


class TSSReportRegenerateWizard(models.TransientModel):
    """
    This wizard only objective is to show a warning when a TSS report
    is about to be regenerated.
    """
    _name = 'tss.report.regenerate.wizard'
    _description = "Tss Report Regenerate Wizard"

    report_id = fields.Many2one('tss.report', 'Report')

    def regenerate(self):
        self.report_id._generate_report()
