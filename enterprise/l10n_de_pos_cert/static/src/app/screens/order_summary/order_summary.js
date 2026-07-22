import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";
import { patch } from "@web/core/utils/patch";

patch(OrderSummary.prototype, {
    async updateSelectedOrderline({ buffer, key }) {
        const updatedLine = await super.updateSelectedOrderline({ buffer, key });
        const order = this.pos.getOrder();
        if (this.pos.isCountryGermanyAndFiskaly()) {
            if (!order.lines.length) {
                // cancel the transaction if last line is removed
                await this.pos.transactionMutex.exec(
                    async () => await this.pos.handleFiskalyCancellation(order)
                );
            } else {
                // update the transaction if orderline is updated
                this.pos.transactionMutex.exec(async () => await this.pos.createTransaction(order));
            }
        }
        return updatedLine;
    },
});
