/** @odoo-module */

import { Order } from "@point_of_sale/app/store/models";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async _save_to_server (orders, options) {
        var self = this;
        var server = await super._save_to_server(...arguments);

        let currentOrder = self.get_order();
        if (server.length > 0 && currentOrder){
            if (server[0].pos_reference == currentOrder.name){
                currentOrder.l10n_do_ecf_security_code = server[0].l10n_do_ecf_security_code;
                currentOrder.l10n_do_ecf_sign_date = server[0].l10n_do_ecf_sign_date;
                currentOrder.QR_code = server[0].QR_code;
            }
        }

        return server;
    },
});

patch(Order.prototype, {
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.l10n_do_ecf_security_code = json.l10n_do_ecf_security_code;
        this.l10n_do_ecf_sign_date = json.l10n_do_ecf_sign_date;
        this.QR_code = json.QR_code;
    },
    export_as_JSON() {
        var json = super.export_as_JSON(...arguments);
        json.l10n_do_ecf_security_code = this.l10n_do_ecf_security_code;
        json.l10n_do_ecf_sign_date = this.l10n_do_ecf_sign_date;
        json.QR_code = this.QR_code;
        return json;
    },
    export_for_printing() {
        var self = this;
        var result = super.export_for_printing(...arguments);
        result.l10n_do_ecf_security_code = self.l10n_do_ecf_security_code;
        result.l10n_do_ecf_sign_date = self.l10n_do_ecf_sign_date;
        result.QR_code = self.QR_code;
        return result;
    },
});

