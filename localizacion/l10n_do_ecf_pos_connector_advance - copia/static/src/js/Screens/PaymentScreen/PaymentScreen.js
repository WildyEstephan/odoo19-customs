/** @odoo-module */

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { TextInputPopup } from "@point_of_sale/app/utils/input_popups/text_input_popup";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { _t } from "@web/core/l10n/translation";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.popup = useService("popup");
    },

    async validateOrder(isForceValidate) {
        const order = this.currentOrder;
        const partner = order.get_partner();

        if (partner.l10n_do_dgii_tax_payer_type == 'non_payer'){
            const amount_total = order.get_total_with_tax();
            if (amount_total >= 250000){
                let partner = this.currentOrder.get_partner()

                if (!partner.vat) {
                    this.env.services.popup.add(ErrorPopup, {
                        title: _t("Invoice amount is greater than RD$250,000"),
                        body: _t("If the invoice amount is greater than RD$250,000.00 the customer should have a VAT to validate the invoice."),
                    });
                    return;
                }
            }
        }

        return await super.validateOrder(...arguments);
    },
});
