/** @odoo-module */

import { PartnerLine } from "@point_of_sale/app/screens/partner_list/partner_line/partner_line";
import { patch } from "@web/core/utils/patch";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";

console.log('[L10N_DO_POS] PartnerLine.js loaded');

patch(PartnerLine.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
    },
    
    getPayerTypeName(partner) {
        if (!partner.l10n_do_dgii_tax_payer_type || !this.pos.payer_types_selection) {
            return '';
        }
        return this.pos.payer_types_selection[partner.l10n_do_dgii_tax_payer_type] || '';
    }
}); 