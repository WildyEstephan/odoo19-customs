
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class HrEmployeeEmergencyContact(models.Model):
	"""adding emergency contact table"""

	_name = "hr.employee.emergency_contact"
	_description = "HR Emergency Contact"

	name = fields.Char(string="Name", required=True)
	number = fields.Char(string="Number", required=True)
	employee_id = fields.Many2one('hr.employee', invisible=1)
	# MODIFICADO: Arturo Diaz Lora - 2026-03-14 10:00
	# Razón: Agregar company_id related para soporte multi-company
	company_id = fields.Many2one('res.company', related='employee_id.company_id', store=True, index=True)

	def _valid_field_parameter(self, field, name):
		return name == 'invisible' or super(HrEmployeeEmergencyContact, self)._valid_field_parameter(field, name)


class HrEmployeeFamily(models.Model):
	"""Employee family information"""

	_name = "hr.employee.family"
	_description = "HR Employee Family"

	family_name = fields.Char(string="Name", required=True)
	birthdate = fields.Date(string="Fecha de Nacimiento", required=False, )
	cedula = fields.Char(string="Cedula", required=False, )
	relation = fields.Selection(
		[
			("father", "Father"),
			("mother", "Mother"),
			("daughter", "Daughter"),
			("son", "Son"),
			("wife", "Wife"),
			("husband", "Husband"),
		],
		string="Relation",
		required=True,
	)
	is_capita = fields.Boolean(string="Retenter Per Cápita?")
	amount_capita = fields.Float(string="Monto")
	family_contact = fields.Char(string="Contact No")
	employee_id = fields.Many2one(
		string="Employee",
		help="Select corresponding Employee",
		comodel_name="hr.employee",
		invisible=False,
	)
	# MODIFICADO: Arturo Diaz Lora - 2026-03-14 10:00
	# Razón: Agregar company_id related para soporte multi-company
	company_id = fields.Many2one('res.company', related='employee_id.company_id', store=True, index=True)

	def _valid_field_parameter(self, field, name):
		return name == 'invisible' or super(HrEmployeeFamily, self)._valid_field_parameter(field, name)


class HrEmployee(models.Model):
	_inherit = "hr.employee"

	# Campos relacionados con hr.version para acceso desde empleado
	# En Odoo 19, hr.version reemplaza a hr.contract
	income_type = fields.Selection(related='version_id.income_type', string='Income Type', readonly=False, inherited=True)
	payrolltype_id = fields.Many2one(related='version_id.payrolltype_id', string='Payroll Type', readonly=False, inherited=True)
	schedule_form_pay = fields.Selection(related='version_id.schedule_form_pay', string='Schedule Pay', inherited=True)
	deduction_plan = fields.Boolean(related='version_id.deduction_plan', readonly=False, inherited=True)
	scheduled_retentions = fields.Selection(related='version_id.scheduled_retentions', readonly=False, inherited=True)
	is_foreign = fields.Boolean(related='version_id.is_foreign', readonly=False, inherited=True)
	allow_accumulation = fields.Boolean(related='version_id.allow_accumulation', readonly=False, inherited=True)
	retencion_unico = fields.Boolean(related='version_id.retencion_unico', readonly=False, inherited=True)
	rnc_retencion_unico = fields.Many2one(related='version_id.rnc_retencion_unico', readonly=False, inherited=True)
	remuneracion = fields.Float(related='version_id.remuneracion', readonly=False, inherited=True)
	payment_day = fields.Float(related='version_id.payment_day', readonly=False, inherited=True)
	hourly_payment = fields.Boolean(related='version_id.hourly_payment', readonly=False, inherited=True)
	comission_rate = fields.Integer(related='version_id.comission_rate', readonly=False, inherited=True)
	wage_extra_hour = fields.Monetary(related='version_id.wage_extra_hour', readonly=False, inherited=True)
	dieta_amount = fields.Monetary(related='version_id.dieta_amount', readonly=False, inherited=True)
	wage_extra_labol = fields.Monetary(related='version_id.wage_extra_labol', readonly=False, inherited=True)
	free_days = fields.Monetary(related='version_id.free_days', readonly=False, inherited=True)
	wage_holidays_hour = fields.Monetary(related='version_id.wage_holidays_hour', readonly=False, inherited=True)
	fixed_loan = fields.Monetary(related='version_id.fixed_loan', readonly=False, inherited=True)
	amount_saved = fields.Monetary(related='version_id.amount_saved', readonly=False, inherited=True)
	assurance_amount = fields.Float(related='version_id.assurance_amount', readonly=False, inherited=True)

	emergency_contacts = fields.One2many(
		"hr.employee.emergency_contact", "employee_id", string="Contactos de Emergencia",
		invisible=False,
	)
	family_ids = fields.One2many(
		"hr.employee.family", "employee_id", string="Family")

	def _valid_field_parameter(self, field, name):
		return name == 'invisible' or super(HrEmployee, self)._valid_field_parameter(field, name)

	# En Odoo 19, gender fue renombrado a 'sex' en hr.version
	# Campo relacionado para mantener compatibilidad
	sex = fields.Selection(
		related='version_id.sex',
		string='Gender',
		readonly=False,
		inherited=True,
		required=True
	)

	# MODIFICADO: Arturo Diaz Lora - 2026-02-16
	# Cambiado required=True a required=False para evitar warnings en empleados existentes sin datos
	identification_id = fields.Char(string='Identification No', copy=False, required=False)

	is_dominica = fields.Boolean(string="Dominican", compute="_compute_is_dominica_person")

	_identification_id_uniq = models.Constraint(
		'unique(identification_id)',
		'The employee identification number must be unique across the company(s).',
	)

	employee_code = fields.Char(string="Código")

	# TSS INFO
	# MODIFICADO: Arturo Diaz Lora - 2026-03-18 23:15
	# Razón: Restaurar required=True en tss_names y tss_first_lastname por solicitud del administrador
	# Código original: required=False (cambiado 2026-02-16)
	tss_names = fields.Char(string='Nombres', copy=False, required=True)
	tss_first_lastname = fields.Char(string='Primer Apellido', copy=False, required=True)
	tss_second_lastname = fields.Char(string='Segundo Apellido',copy=False)

	loan_ids = fields.One2many(comodel_name='hr.employee.loan', inverse_name='employee_id',
							   string=u"Préstamos")

	# Cuenta analítica a nivel de empleado (opcional)
	analytic_account_id = fields.Many2one(
		'account.analytic.account',
		string='Cuenta Analítica',
		help='Cuenta analítica para asignar a las nóminas de este empleado. '
			 'Si el lote de nómina tiene una cuenta analítica configurada, esta será ignorada.'
	)

	@api.model
	def generate_identification_id(self):
		"""Genera un ID de identificación único para el empleado"""
		sequence = self.env['ir.sequence'].sudo().search([
			('code', '=', 'hr.employee.identification')
		], limit=1)
		if sequence:
			return sequence.next_by_id()
		# Fallback: generar código basado en timestamp
		import time
		return f"EMP-{int(time.time())}"

	@api.model_create_multi
	def create(self, vals_list):
		for vals in vals_list:
			if not vals.get('identification_id'):
				vals['identification_id'] = self.generate_identification_id()
		return super(HrEmployee, self).create(vals_list)

	@api.depends('country_id')
	def _compute_is_dominica_person(self):
		do = self.env.ref('base.do').id
		self.is_dominica = self.country_id.id == do
		
	def get_approved_loans(self):
		return self.loan_ids.filtered(lambda loan: loan.state == 'approved')
	
	@api.model
	def name_search(self, name='', args=None, operator='ilike', limit=100):
		recs = self.search([
			'|', '|',
			('name', operator, name),
			('employee_code', operator, name),
			('identification_id', operator, name)
		], limit=limit)
		res = recs.sudo().name_get()
		return res
	
	@api.model
	def name_get(self):
		res = []
		for rec in self:
			name = rec.name or ''
			res.append((rec.id, name))
		return res



