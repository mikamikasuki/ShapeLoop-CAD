import { describe, expect, it, vi, afterEach } from "vitest";
import {
  api,
  initializeSession,
  normalizeProject,
  revisionChecks,
  parameterValue,
} from "./api";
afterEach(() => vi.unstubAllGlobals());
describe("local API boundary", () => {
  it("sends the local session token on state changes and exposes server conflicts", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ token: "test-session" }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 409,
        json: async () => ({ detail: "Edit base is stale" }),
      });
    vi.stubGlobal("fetch", fetch);
    await initializeSession();
    await expect(
      api("/projects/p/edit", { base_revision: "old" }),
    ).rejects.toThrow("Edit base is stale");
    expect(fetch.mock.calls[1][1].headers["X-ShapeLoop-Token"]).toBe(
      "test-session",
    );
  });
  it("preserves actual verifier measurements and unknown results", () => {
    const p = normalizeProject({
      project: { id: "p", name: "part", active_revision: "r" },
      revisions: [
        {
          id: "r",
          status: "failed",
          design_spec: { parameters: { wall: { value: 2 } }, features: [] },
          report: {
            status: "FAIL",
            measurements: [
              {
                id: "thickness",
                status: "UNKNOWN",
                actual: null,
                method: "BREP ray intersection",
              },
            ],
          },
        },
      ],
    });
    expect(p.active_revision_id).toBe("r");
    expect(revisionChecks(p.revisions[0])[0].status).toBe("UNKNOWN");
    expect(parameterValue(p.revisions[0].spec.parameters.wall)).toBe(2);
  });
});
