# -*- encoding: utf-8 -*-
# © 2019 Jeffry Jesus De La Rosa <jeffryjesus@gmail.com>
# This file is part of Dominincan Republic - HR Payroll

# Dominincan Republic - HR Payroll is free software: you can redistribute
# it and/or modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.

# Dominincan Republic - HR Payroll is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Dominincan Republic - HR Payroll.  If not,
# see <https://www.gnu.org/licenses/>.

{
    "name": "HR Payroll Electronic Pay",
    "summary": u"""
          This Module Will Add the electronic Payment
      """,
    "category": "Localization",
    "author": u"""Jeffry Jesus De La Rosa""",
    "depends": ["l10n_do_hr_payroll"],
    "license": "GPL-3",
    "version": "19.0.1.0.0",
    "description": """
Dominincan Republic - HR Payroll.
=================================

    This Module Will Add:
    """,
    "active": True,
    "data": [
        "data/sequence.xml",
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        'views/views_elec_empl.xml',
        'views/res_partner_bank_views.xml',
        'views/hr_employee_views.xml'
    ],
    "installable": True,
    "auto_install": False,
}
