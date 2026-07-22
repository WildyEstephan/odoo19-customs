/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

// Patch para usar nuestra vista personalizada de partner con DGII
patch(PosStore.prototype, {
    editPartnerContext(partner) {
        const context = super.editPartnerContext(partner);
        // Usar nuestra vista personalizada que incluye el botón DGII
        return {
            ...context,
            view_id: 'l10n_do_pos.view_partner_form_pos_dgii',
        };
    }
});