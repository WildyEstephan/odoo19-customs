{
    'name': "Dominican Banks Currency Update",
    'summary': """
    Updates company secondary currency rates from dominican banks
    """,

    'author': "Overload Solutions",
    'website': "https://www.overloadsolutions.com.do/",
    'category': 'Accounting',
    'version': "19.0.1.0.0",
    # Arturo Diaz Lora - 2025-12-07 15:45 - Agregada licencia faltante para evitar warning
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'data/ir_cron_data.xml',
        'data/ir_config_parameter_data.xml',
        'views/res_config_settings_views.xml',
    ],
}
