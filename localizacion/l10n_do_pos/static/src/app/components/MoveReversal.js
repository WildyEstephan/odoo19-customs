/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";

console.log('[L10N_DO_POS] MoveReversal.js loaded');

// Autor: Arturo Diaz Lora
// Fecha: 2025-11-24 05:07
// Razón: Cambiar valor inicial de "1" a "01" para coincidir con formato DGII
export class MoveReversal extends Component {
    static template = "MoveReversal";
    setup() {
        super.setup();
        this.state = useState({
            'modification_code': "01",  // Cambiar de "1" a "01" para coincidir con DGII
        });
        this.pillClicked();
    }
    pillClicked() {
        this.props.toggle(this.state.modification_code);
    }
}

patch(PaymentScreen.prototype, {
    get components() {
        return { ...super.components, MoveReversal };
    }
});
