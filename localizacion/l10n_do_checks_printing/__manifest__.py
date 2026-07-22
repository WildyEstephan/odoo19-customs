# noinspection PyStatementEffect
###############################################################################
{
    'name': 'Impresion de cheques bancos Dominicanos',
    'version': "19.0.1.0.0",
    'author': 'Jeffry J. De La Rosa - Astra Tech SRL',
    'website': "http://astratech.com.do",
    'category': 'Localization',
    'summary': """
    Localizacion Para Republica Dominicana
    Permite configurar desde los diarios las plantillas para impresion de
    chques.""",
    'description': """
        Este módulo permite configurar sus cheques de pagos en el papel de
        verificación pre-impreso.
        Puede configurar la salida (distribución, información trozos, etc.)
        en los entornos de la empresa, y gestionar el cheques de numeración
        (si utiliza cheques preimpresos sin números) en la configuración de
        diario.
    """,
    'depends': ['account_check_printing', 'l10n_do_accounting'],
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/cheque_attribute_data.xml',
        'report/paper_data.xml',
        'report/report_data.xml',
        'report/report_template.xml',
        'views/account_view.xml',
        'views/check_report_config_view.xml',
        'views/bank_cheque_views.xml',
        'views/website_template_view.xml',
        'views/cheque_report.xml',
    ],

    "assets": {
        # Bundle específico para la funcionalidad de cheques - No carga automáticamente
        "l10n_do_checks_printing.assets_cheque": [
            "l10n_do_checks_printing/static/src/js/jquery_Jcrop.js",
            "l10n_do_checks_printing/static/src/js/bank_cheque.js",
        ]
    },

    "pre_init_hook": "_pre_init_check_config_company",
    'installable': True,
    'license': 'LGPL-3',
}
