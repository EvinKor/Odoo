/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";

const STAGES_REQUIRING_RESCHEDULE = new Set(["new", "announced"]);

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
                const targetStageId = targetGroup?.value;
                if (targetStageId) {
                    const [stage] = await this.orm.read("event.stage", [targetStageId], ["name"]);
                    const stageName = (stage?.name || "").trim().toLowerCase();
                    if (STAGES_REQUIRING_RESCHEDULE.has(stageName)) {
                        return this.action.doAction(
                            {
                                type: "ir.actions.act_window",
                                res_model: "event.stage.reschedule.wizard",
                                views: [[false, "form"]],
                                target: "new",
                                context: {
                                    default_event_id: parseInt(dataRecordId, 10),
                                    default_target_stage_id: targetStageId,
                                },
                            },
                            {
                                onClose: async (closeInfo) => {
                                    if (closeInfo?.rescheduled) {
                                        await this.props.list.model.load();
                                    }
                                },
                            }
                        );
                    }
                }
            }
        }
        return super.sortRecordDrop(...arguments);
    },
});
