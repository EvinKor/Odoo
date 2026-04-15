/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";

export class EventPointsSystray extends Component {
    static template = "event_application.EventPointsSystray";
    static props = {};

    setup() {
        this.state = useState({ balance: 0 });
        onWillStart(async () => {
            try {
                const result = await rpc("/event/points/balance", {});
                this.state.balance = Number(result?.balance || 0);
            } catch {
                this.state.balance = 0;
            }
        });
    }
}

export const eventPointsSystrayItem = {
    Component: EventPointsSystray,
};

registry.category("systray").add("event_application.EventPointsSystray", eventPointsSystrayItem, {
    sequence: 30,
});
