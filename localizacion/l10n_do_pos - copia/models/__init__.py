# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

# Autor: Arturo Diaz Lora
# Fecha: 2025-11-23 01:20
# Razón: Log de verificación de carga del módulo l10n_do_pos
_logger.info("="*80)
_logger.info("[L10N_DO_POS] 🚀 MÓDULO l10n_do_pos/models CARGÁNDOSE...")
_logger.info("="*80)

from . import pos_config
from . import pos_order
from . import pos_payment
from . import pos_payment_method
from . import pos_session
from . import res_company
from . import res_partner
from . import search_criteria

_logger.info("[L10N_DO_POS] ✅ MÓDULO l10n_do_pos/models CARGADO COMPLETAMENTE")
_logger.info("="*80)

