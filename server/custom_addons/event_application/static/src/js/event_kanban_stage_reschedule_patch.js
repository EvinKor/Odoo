/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";

const STAGES_REQUIRING_REVIEW = new Set(["new", "booked", "announced"]);
const CANCELLED_STAGE = "cancelled";
const ENDED_STAGE = "ended";

patch(KanbanRenderer.prototype, {
    setup() {
        super.setup();
        this.action = useService("action");
        this.orm = useService("orm");
    },

    async sortRecordDrop(dataRecordId, dataGroupId, { element, parent, previous }) {
        if (
            this.props.list.resModel === "event.event" &&
            this.props.list.isGrouped &&
            this.props.list.groupByField?.name === "stage_id"
        ) {
            while (previous && !previous.dataset.id) {
                previous = previous.previousElementSibling;
            }
            const targetGroupId = parent?.dataset.id;
            if (targetGroupId && dataGroupId !== targetGroupId) {
                const targetGroup = this.props.list.groups.find((group) => group.id === targetGroupId);
                const sourceGroup = this.props.list.groups.find((group) => group.id === dataGroupId);
                const record = sourceGroup?.list.records.find((item) => item.id === dataRecordId);
                const eventResId = record?.resId;
                const targetStageId = targetGroup?.value;
                if (targetStageId && eventResId) {
                    const [stage] = await this.orm.read("event.stage", [targetStageId], ["name"]);
                    const stageName = (stage?.name || "").trim().toLowerCase();
                    const [event] = await this.orm.read("event.event", [eventResId], [
                        "active",
                        "date_end",
                        "website_published",
                        "is_published",
                    ]);
                    if (stageName === CANCELLED_STAGE) {
                        const attendeeCount = await this.orm.searchCount("event.registration", [
                            ["event_id", "=", eventResId],
                        ], {
                            context: { active_test: false },
                        });
                        if (attendeeCount > 0) {
                            return this.action.doAction(
                                {
                                    type: "ir.actions.act_window",
                                    res_model: "event.cancel.wizard",
                                    views: [[false, "form"]],
                                    target: "new",
                                    context: {
                                        default_event_id: eventResId,
                                        default_target_stage_id: targetStageId,
                                    },
                                },
                                {
                                    onClose: async (closeInfo) => {
                                        if (closeInfo?.stage_updated) {
                                            await this.props.list.model.load();
                                        }
                                    },
                                }
                            );
                        }
                    }
                    if (STAGES_REQUIRING_REVIEW.has(stageName)) {
                        const endMs = event?.date_end ? Date.parse(event.date_end.replace(" ", "T")) : NaN;
                        const isPast = Number.isFinite(endMs) && endMs < Date.now();
                        const isHidden = !event?.active || !(event?.website_published || event?.is_published);
                        if (isPast || isHidden) {
                            return this.action.doAction(
                                {
                                    type: "ir.actions.act_window",
                                    res_model: "event.stage.reschedule.wizard",
                                    views: [[false, "form"]],
                                    target: "new",
                                    context: {
                                        default_event_id: eventResId,
                                        default_target_stage_id: targetStageId,
                                    },
                                },
                                {
                                    onClose: async (closeInfo) => {
                                        if (closeInfo?.stage_updated) {
                                            await this.props.list.model.load();
                                        }
                                    },
                                }
                            );
                        }
                    }
                    if (stageName === ENDED_STAGE) {
                        const endMs = event?.date_end ? Date.parse(event.date_end.replace(" ", "T")) : NaN;
                        const isCurrentOrFuture = !Number.isFinite(endMs) || endMs >= Date.now();
                        if (isCurrentOrFuture) {
                            return this.action.doAction(
                                {
                                    type: "ir.actions.act_window",
                                    res_model: "event.stage.reschedule.wizard",
                                    views: [[false, "form"]],
                                    target: "new",
                                    context: {
                                        default_event_id: eventResId,
                                        default_target_stage_id: targetStageId,
                                    },
                                },
                                {
                                    onClose: async (closeInfo) => {
                                        if (closeInfo?.stage_updated) {
                                            await this.props.list.model.load();
                                        }
                                    },
                                }
                            );
                        }
                    }
                }
            }
        }
        return super.sortRecordDrop(...arguments);
    },
});
