
{
    "name": "Fiscal Accounting (Rep. Dominicana)",
    "summary": """
        Este módulo implementa la administración y gestión de los números de
        comprobantes fiscales para el cumplimento de la norma 06-18 de la
        Dirección de Impuestos Internos en la República Dominicana.""",
    "author": "Adel Networks S,R,L",
    "website": "https://adelnetworks.com.do",
    "category": "Localization",
    "license": "LGPL-3",
    "version": "19.0.1.1.0",
    "depends": ["l10n_do", "account_debit_note", "l10n_latam_invoice_document"],
    "post_init_hook": "post_init_hook",
    "data": [
        "security/res_groups.xml",
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        "data/l10n_latam.document.type.csv",
        "data/ir_cron_data.xml",
        "data/l10n_do_account_journal_config.xml",

        "wizard/account_move_reversal_views.xml",
        # "views/account_move_tax_views.xml",  # TODO: Revisar compatibilidad con Odoo 19
        "views/account_tax_views.xml",
        "wizard/account_debit_note_views.xml",
        "wizard/account_move_cancel_views.xml",
        "wizard/account_fiscal_sequence_validate_wizard_views.xml",
        "views/account_fiscal_sequence_views.xml",
        "views/res_config_settings_view.xml",
        "views/account_move_views.xml",
        "views/account_move_line_view.xml",
        "views/res_partner_views.xml",
        "views/res_company_views.xml",
        "views/account_journal_views.xml",
        "views/l10n_latam_document_type_views.xml",
        "views/report_templates.xml",
        "views/account_report.xml",
        "views/report_invoice.xml",
    ],
}
