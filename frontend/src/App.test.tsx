import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, afterEach } from "vitest";
import App from "./App";
vi.mock("./Viewport", () => ({
  default: ({ revisionLabel }: any) => (
    <div data-testid="viewport-state">{revisionLabel}</div>
  ),
}));
const spec = {
  name: "Test enclosure",
  units: "mm",
  parameters: { height: { value: 30, dimension: "length" } },
  parts: [{ id: "body", name: "Body", feature: "blank" }],
  features: [
    {
      id: "blank",
      name: "Blank",
      type: "box",
      part: "body",
      inputs: [],
      parameters: { size: [80, 50, 28] },
    },
  ],
  constraints: [
    {
      id: "envelope",
      name: "Envelope",
      type: "envelope",
      required: true,
      parameters: { size: [80, 50, 30] },
    },
  ],
  assumptions: [],
};
const accepted = {
  id: "a",
  status: "accepted",
  branch: "main",
  spec,
  artifacts: ["mesh.json"],
  report: {
    status: "PASS",
    measurements: [
      {
        id: "envelope",
        name: "Envelope",
        status: "PASS",
        actual: [80, 50, 30],
        unit: "mm",
        tolerance: 0.01,
        method: "Reimported STEP envelope",
      },
    ],
  },
};
function setup(extra: any[] = []) {
  const p = {
    id: "p",
    name: "Test enclosure",
    active_revision_id: "a",
    revisions: [accepted, ...extra],
  };
  const fetch = vi.fn(async (url: string) => ({
    ok: true,
    status: 200,
    json: async () =>
      url === "/api/session"
        ? { token: "t" }
        : url === "/api/settings"
          ? { provider: { endpoint: "", model: "" } }
          : url === "/api/projects"
            ? [{ id: "p", name: "Test enclosure" }]
            : url === "/api/projects/p"
              ? p
              : url.includes("mesh.json")
                ? { parts: [] }
                : {},
  }));
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  return fetch;
}
afterEach(() => vi.unstubAllGlobals());
describe("workbench acceptance behavior", () => {
  it("makes missing-provider mode explicit while structured dimensions remain editable", async () => {
    setup();
    await screen.findByLabelText("Height");
    expect(
      screen.getByRole("button", { name: "Propose natural-language edit" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Height"), {
      target: { value: "27" },
    });
    expect(screen.getByRole("button", { name: /Build changes/ })).toBeEnabled();
  });
  it("displays actual measured results and method", async () => {
    setup();
    await screen.findByLabelText("Height");
    fireEvent.click(screen.getByRole("button", { name: /Requirements/ }));
    expect(
      await screen.findByText("Reimported STEP envelope"),
    ).toBeInTheDocument();
    expect(screen.getByText(/80 × 50 × 30 mm/)).toBeInTheDocument();
  });
  it("retains accepted preview for a failed candidate and blocks acceptance", async () => {
    setup([
      {
        ...accepted,
        id: "f",
        status: "failed",
        error: "Keep-out overlap",
        report: {
          status: "FAIL",
          measurements: [
            { id: "envelope", status: "FAIL", actual: [80, 50, 10] },
          ],
        },
      },
    ]);
    await screen.findByLabelText("Height");
    fireEvent.click(screen.getByRole("button", { name: /Revision history/ }));
    fireEvent.click(screen.getByRole("button", { name: /r02/ }));
    await waitFor(() =>
      expect(screen.getByTestId("viewport-state")).toHaveTextContent(
        "Last accepted revision",
      ),
    );
    expect(
      screen.getByRole("button", { name: "Accept revision" }),
    ).toBeDisabled();
  });
});
