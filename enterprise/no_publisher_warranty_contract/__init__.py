def _set_expiration_date(env, *, months=0, years=0):
	from datetime import datetime
	from dateutil.relativedelta import relativedelta
	expiration_date = datetime.now() + relativedelta(months=months, years=years)
	expiration_value = expiration_date.strftime('%Y-%m-%d %H:%M:%S')
	config = env['ir.config_parameter'].sudo()
	config.set_param('database.expiration_date', expiration_value)


def run_post_init_hook(env):
	cron = env.ref("mail.ir_cron_module_update_notification", raise_if_not_found=False)
	if cron:
		cron_id = cron.id
		domain = [('model', '=', 'ir.cron'), ('res_id', '=', cron_id), ('module', '=', 'mail')]
		model = env['ir.model.data'].search(domain, limit=1)
		if model:
			model.write({'noupdate': True})
	_set_expiration_date(env, years=1)


def run_uninstall_hook(env):
	_set_expiration_date(env, months=1)


