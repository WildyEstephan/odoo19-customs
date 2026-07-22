
{
    'name': "Autodeterminacion TSS",

    'summary': """
        Autodeterminacion TSS
        """,

    'description': """

    """,

    'author': 'Astra Tech SRL',
    'website': 'https://astratech.com.do',
    'category': 'Localization',
    'version': "19.0.1.0.0",
    'license': 'LGPL-3',
    'depends': ['hr_payroll', 'l10n_do_hr_payroll', 'hr_work_entry_enterprise'],

    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'views/tss_report_views.xml',
        'wizard/tss_report_regenerate_wizard_views.xml'

    ],

}
