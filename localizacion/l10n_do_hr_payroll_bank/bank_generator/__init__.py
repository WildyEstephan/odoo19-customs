# -*- encoding: utf-8 -*-
import io
import base64

import importlib

from .interface import GeneratorType

from . import interface


def generate_data_for_bank(code, obj):
    
    # Intenta importar el módulo basado en el código
    try:
        module_name = f"odoo.addons.l10n_do_hr_payroll_bank.bank_generator.{code.lower()}_generator"
        importlib.import_module(module_name)
    except ImportError:
        raise ValueError(f"No generator found for code {code}")
    
    generator_instance = GeneratorType.get(code)
    return generator_instance.generate_txt(obj)

