/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Layout } from "@web/search/layout";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const DEFAULT_OPERATIONS = ["connection", "product", "customer", "order", "all"];
const DEFAULT_STATES = ["success", "warning", "failed"];

function toISODate(date) {
    return date.toISOString().slice(0, 10);
}

function minusDays(days) {
    const date = new Date();
    date.setDate(date.getDate() - days);
    return toISODate(date);
}

export class SmShopifyDashboard extends Component {
    static template = "sm_shopify_connector.Dashboard";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            cards: [],
            recent: [],
            activity: { labels: [], total: [], success: [], failed: [], max: 1 },
            summary: { stores: 0, connected: 0, products: 0, customers: 0, orders: 0, success: 0, failed: 0, total_logs: 0 },
            options: { instances: [], operations: [], states: [] },
            filters: {
                date_from: minusDays(29),
                date_to: toISODate(new Date()),
                instance_id: "",
                operations: [...DEFAULT_OPERATIONS],
                states: [...DEFAULT_STATES],
            },
        });

        onWillStart(async () => {
            await this.loadOptions();
            await this.loadData();
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    get title() {
        return this.props.action.name || _t("Shopify Dashboard");
    }

    get payload() {
        const { filters } = this.state;
        return {
            date_from: filters.date_from,
            date_to: filters.date_to,
            instance_ids: filters.instance_id ? [Number(filters.instance_id)] : [],
            operations: [...filters.operations],
            states: [...filters.states],
        };
    }

    async loadOptions() {
        this.state.options = await this.orm.call("shopify.instance", "sm_shopify_dashboard_filters", []);
    }

    async loadData() {
        this.state.loading = true;
        const data = await this.orm.call("shopify.instance", "sm_shopify_dashboard_data", [], { filters: this.payload });
        this.state.cards = data.cards || [];
        this.state.recent = data.recent || [];
        this.state.activity = data.activity || { labels: [], total: [], success: [], failed: [], max: 1 };
        this.state.summary = data.summary || this.state.summary;
        this.state.loading = false;
    }

    setPreset(days) {
        this.state.filters.date_from = minusDays(days - 1);
        this.state.filters.date_to = toISODate(new Date());
        this.loadData();
    }

    onDateChange(field, ev) {
        this.state.filters[field] = ev.target.value;
    }

    onInstanceChange(ev) {
        this.state.filters.instance_id = ev.target.value;
    }

    toggleOperation(code) {
        this.toggleListValue("operations", code);
    }

    toggleState(code) {
        this.toggleListValue("states", code);
    }

    toggleListValue(field, code) {
        const values = new Set(this.state.filters[field]);
        if (values.has(code) && values.size > 1) {
            values.delete(code);
        } else {
            values.add(code);
        }
        this.state.filters[field] = [...values];
        this.loadData();
    }

    isOperationActive(code) {
        return this.state.filters.operations.includes(code);
    }

    isStateActive(code) {
        return this.state.filters.states.includes(code);
    }

    resetFilters() {
        this.state.filters.date_from = minusDays(29);
        this.state.filters.date_to = toISODate(new Date());
        this.state.filters.instance_id = "";
        this.state.filters.operations = [...DEFAULT_OPERATIONS];
        this.state.filters.states = [...DEFAULT_STATES];
        this.loadData();
    }

    async openAction(xmlid, domain = []) {
        const action = await this.action.loadAction(xmlid);
        action.domain = domain;
        this.action.doAction(action);
    }

    openStores() {
        this.openAction("sm_shopify_connector.action_shopify_instance");
    }

    openProducts() {
        this.openAction("sm_shopify_connector.action_shopify_products", [["shopify_instance_id", "!=", false]]);
    }

    openCustomers() {
        this.openAction("sm_shopify_connector.action_shopify_customers", [["shopify_instance_id", "!=", false]]);
    }

    openOrders() {
        this.openAction("sm_shopify_connector.action_shopify_orders", [["shopify_instance_id", "!=", false]]);
    }

    openLogs(domain = []) {
        this.openAction("sm_shopify_connector.action_shopify_sync_log", domain);
    }

    openStore(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "shopify.instance",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openLog(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "shopify.sync.log",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    barHeight(value, maxValue) {
        return `height: ${Math.max(6, Math.round((value / Math.max(maxValue, 1)) * 100))}%`;
    }

    stateClass(value) {
        return value === "connected" || value === "success" ? "success" : value === "failed" || value === "error" ? "danger" : "warning";
    }
}

registry.category("actions").add("sm_shopify_dashboard", SmShopifyDashboard);
