/**
 * Workflow list mapping -- snake_case API rows and blank names.
 */

import {
  toWorkflow,
  workflowTitle,
} from "../app/admin/workflows/workflowDisplay";

describe("toWorkflow", () => {
  it("maps snake_case API rows onto the card fields", () => {
    const workflow = toWorkflow({
      id: "demo-wf-080",
      name: null,
      service_id: "11122233",
      service_name: "Lower GI Urgent Suspected Cancer Referral",
      created_at: "2026-06-27T14:06:48.927Z",
      step_count: 2,
      human_count: 1,
    });

    expect(workflow.name).toBe("Lower GI Urgent Suspected Cancer Referral");
    expect(workflow.serviceId).toBe("11122233");
    expect(workflow.serviceName).toBe(
      "Lower GI Urgent Suspected Cancer Referral",
    );
    expect(workflow.createdAt).toBe("2026-06-27T14:06:48.927Z");
    expect(workflow.stepCount).toBe(2);
    expect(workflow.humanCount).toBe(1);
  });

  it("keeps camelCase rows from the Playwright stubs", () => {
    const workflow = toWorkflow({
      id: "wf-001",
      name: "Colorectal Standard",
      serviceId: "svc-1",
      serviceName: "Colorectal Surgery",
      createdAt: "2026-08-01T09:00:00Z",
      stepCount: 6,
      humanCount: 2,
    });

    expect(workflow.name).toBe("Colorectal Standard");
    expect(workflow.stepCount).toBe(6);
  });
});

describe("workflowTitle", () => {
  it("prefers the service name over a technical workflow id", () => {
    expect(
      workflowTitle({
        id: "11122233_referral_workflow",
        name: "11122233_referral_workflow",
        serviceId: "11122233",
        serviceName: "Lower GI Urgent Suspected Cancer Referral",
        createdAt: "",
        stepCount: 2,
        humanCount: 1,
      }),
    ).toBe("Lower GI Urgent Suspected Cancer Referral");
  });

  it("humanises a bare demo id when nothing else is set", () => {
    expect(
      workflowTitle({
        id: "demo-wf-080",
        name: "demo-wf-080",
        serviceId: "",
        createdAt: "",
      }),
    ).toBe("Demo workflow 080");
  });
});
