# -*- coding: utf-8 -*-
{
    'name': "Bypass publisher Warranty Contract",

    'summary': """Bypass publisher Warranty Contract""",

    'description': """
        This module will enable you to use Odoo enterprise for free.
    """,

    'author': "Babatope Ajepe",
    'website': "https://ajepe.github.io",

    'category': 'Hidden',
    'version': '0.1',

    'depends': ['base', 'mail'],

    'auto_install': False,
    'license': 'GPL-2',

    # always loaded
    'data': [
        'data/ir_cron_data.xml',
    ],

    "post_init_hook": "run_post_init_hook",
    "uninstall_hook": "run_uninstall_hook",
}

