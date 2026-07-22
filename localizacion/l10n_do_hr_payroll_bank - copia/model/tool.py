# -*- encoding: utf-8 -*-
import io
import logging

from odoo import fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SPECIALS = {
    u'á': 'a', u'Á': 'A',
    u'é': 'e', u'É': 'E',
    u'í': 'i', u'Í': 'I',
    u'ó': 'o', u'Ó': 'O',
    u'ú': 'u', u'Ú': 'U',
    u'ñ': 'n', u'Ñ': 'N',
}


class AbstractMethodError(Exception):
    def __str__(self):
        return 'Abstract Method'

    def __repr__(self):
        return 'Abstract Method'


class GeneratorType(type):
    """ Meta class for Electronic Payroll getters.
        Automaticaly registers new Electronic Payroll getter on class definition
    """
    getters = {}

    def __new__(mcs, name, bases, attrs):
        cls = super(GeneratorType, mcs).__new__(mcs, name, bases, attrs)

        if getattr(cls, 'code', None):
            mcs.getters[cls.code] = cls

        return cls

    @classmethod
    def get(mcs, code, *args, **kwargs):
        """ Get getter by code
        """
        return mcs.getters[code](*args, **kwargs)


class GeneratorInterface(object, metaclass=GeneratorType):
    # attributes required for currency getters
    code = None  # code for service selection
    name = None  # displayed name
    description = 'Pago Nomina'

    def remove_accent(self, word):
        # Si el nombre contienes unos de los caracteres especiales
        # lo remplaza con su semejante sin asento.
        for letter in SPECIALS.keys():
            if letter in word:
                word = word.replace(letter, SPECIALS[letter])

        return word

    def generate_txt(self, obj):
        """Interface method that will retrieve the currency
           This function has to be reinplemented in child
        """
        raise AbstractMethodError
