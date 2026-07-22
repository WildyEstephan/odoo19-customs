from . import models
from . import wizard


def _pre_init_ecf_settings_company(env):
    cr = env.cr
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'ecf_settings' AND column_name = 'company_id'
    """)
    if not cr.fetchone():
        cr.execute("ALTER TABLE ecf_settings ADD COLUMN company_id INTEGER")
    cr.execute("""
        UPDATE ecf_settings SET company_id = (SELECT id FROM res_company ORDER BY id LIMIT 1)
        WHERE company_id IS NULL
    """)
    cr.execute("""
        SELECT conname FROM pg_constraint
        WHERE conname = 'ecf_settings__environment_unique'
    """)
    if cr.fetchone():
        cr.execute("ALTER TABLE ecf_settings DROP CONSTRAINT ecf_settings__environment_unique")


def _l10n_do_edi_post_init(env):
    for company in env['res.company'].search([('chart_template', '=', 'do')]):
        Template = env['account.chart.template'].with_company(company)
        Template._load_data({'account.tax': Template._get_do_edi_account_tax()})
