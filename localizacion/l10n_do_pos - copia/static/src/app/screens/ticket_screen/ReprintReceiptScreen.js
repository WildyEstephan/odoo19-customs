/** @odoo-module */

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";

patch(TicketScreen.prototype, {
    async print(order) {
        // Marcar como copia para el módulo de RD
        if (order) {
            order.is_copy = true;
        }
        await super.print(order);
    }
});