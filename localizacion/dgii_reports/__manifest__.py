# Part of Domincana Premium.
# See LICENSE file for full copyright and licensing details.
# © 2022-Adel Beltran <adelbeltran03@gamil.com>

{
    "name": "Declaraciones DGII",
    "summary": """
        Este módulo extiende las funcionalidades del l10n_do_accounting,
        integrando los reportes de declaraciones fiscales""",
    "author": "Adel Networks S,R,L",
    "license": "LGPL-3",
    "category": "Accounting",
    "version": "19.0.1.2.0",

    "depends": ["l10n_do_accounting"],
    
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    
    "data": [
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        "data/account_tax_dgii_configuration.xml",
        "views/res_partner_views.xml",
        "views/account_account_views.xml",
        "views/account_invoice_views.xml",
        "views/dgii_report_views.xml",
        "wizard/dgii_report_regenerate_wizard_views.xml",
    ],

    'assets': {
        'web.assets_backend': [
            'dgii_reports/static/src/less/dgii_reports.css',
    #         'dgii_reports/static/src/js/widget.js',
        ]
    }
}
