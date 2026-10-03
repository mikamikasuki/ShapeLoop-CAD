import { test, expect } from "@playwright/test";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
const artifacts =
  process.env.SHAPELOOP_BROWSER_ARTIFACTS ||
  path.join(os.homedir(), ".local/share/shapeloop/browser-tests");
test("creates and repeatedly edits real geometry, retains failed candidate, compares and reimports STEP", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByRole("link", { name: "ShapeLoop-CAD project library" }).click();
  await page.getByLabel("Project name").fill("Browser enclosure " + Date.now());
  const creationPromise = page.waitForResponse(
    (r) => r.url().endsWith("/api/projects") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Create design", exact: true })
    .click();
  const creation = await (await creationPromise).json();
  const id = creation.project.id;
  await expect
    .poll(
      async () => {
        const p = await (await request.get(`/api/projects/${id}`)).json();
        return p.revisions.find((r: any) => r.id === creation.revision.id)
          ?.status;
      },
      { timeout: 90000 },
    )
    .toBe("accepted");
  await expect(page.locator(".acceptance-footer")).toContainText(
    "Accepted revision",
    { timeout: 15000 },
  );
  await expect(page.locator("canvas")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Propose natural-language edit" }),
  ).toBeDisabled();
  await page.getByLabel("Height", { exact: true }).fill("27");
  const editPromise = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/api/projects/${id}/edit`) &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: /Build changes/ }).click();
  const edit = await (await editPromise).json();
  await expect
    .poll(
      async () => {
        const p = await (await request.get(`/api/projects/${id}`)).json();
        return p.revisions.find((r: any) => r.id === edit.revision.id)?.status;
      },
      { timeout: 90000 },
    )
    .toBe("candidate");
  await expect(
    page.getByRole("button", { name: "Accept revision" }),
  ).toBeEnabled({ timeout: 15000 });
  await page.getByRole("button", { name: "Accept revision" }).click();
  await expect(page.locator(".acceptance-footer")).toContainText(
    "Accepted revision",
  );
  await page.getByRole("button", { name: /Requirements/ }).click();
  await expect(
    page.locator(".constraint-card").filter({ hasText: "Mounting Pattern" }),
  ).toContainText("4 holes · ⌀3 mm · Z axis");
  await expect(
    page.locator(".constraint-card").filter({ hasText: "Envelope" }).first(),
  ).toContainText("80 × 50 × 27 mm");
  await page.getByRole("button", { name: "Parameters", exact: true }).click();
  await page.getByLabel("Width", { exact: true }).fill("30");
  const failPromise = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/api/projects/${id}/edit`) &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: /Build changes/ }).click();
  const failed = await (await failPromise).json();
  await expect
    .poll(
      async () => {
        const p = await (await request.get(`/api/projects/${id}`)).json();
        return p.revisions.find((r: any) => r.id === failed.revision.id)
          ?.status;
      },
      { timeout: 90000 },
    )
    .toBe("failed");
  await expect(page.locator(".viewport-crumb")).toContainText(
    "Last accepted revision",
    { timeout: 15000 },
  );
  await expect(
    page.getByRole("button", { name: "Accept revision" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Reject", exact: true }).click();
  await expect(page.getByLabel("Width", { exact: true })).toHaveValue("80");
  await page.getByRole("button", { name: /Revision history/ }).click();
  await page.getByLabel("Compare revision").selectOption(creation.revision.id);
  await expect(page.locator(".compare-badge")).toContainText(
    "Overlay comparison",
  );
  await page.getByRole("button", { name: "Close comparison" }).click();
  await page
    .getByRole("button", { name: "Explode preview", exact: true })
    .click();
  await page.getByRole("button", { name: /Requirements/ }).click();
  await fs.mkdir(artifacts, { recursive: true });
  await page.screenshot({
    path: path.join(artifacts, "workbench-enclosure.png"),
  });
  await page.getByRole("button", { name: /Export/ }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: /STEP assembly/ }).click();
  const download = await downloadPromise;
  const step = path.join(artifacts, "browser-enclosure.step");
  await download.saveAs(step);
  const python =
    process.env.SHAPELOOP_PYTHON || path.resolve("../.venv/bin/python");
  const measured = JSON.parse(
    execFileSync(
      python,
      [
        "-c",
        'import cadquery as cq,json,sys; s=cq.importers.importStep(sys.argv[1]).val(); b=s.BoundingBox(); print(json.dumps({"valid":s.isValid(),"solids":len(s.Solids()),"size":[b.xlen,b.ylen,b.zlen]}))',
        step,
      ],
      { encoding: "utf8" },
    ),
  );
  expect(measured.valid).toBe(true);
  expect(measured.solids).toBe(2);
  expect(measured.size[0]).toBeCloseTo(80, 2);
  expect(measured.size[2]).toBeCloseTo(27, 2);
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Parameters", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Parameters", exact: true }).click();
  await expect(page.getByLabel("Height", { exact: true })).toHaveValue("30");
  await page.reload();
  await expect(page.getByLabel("Height", { exact: true })).toHaveValue("30");
  await page.getByRole("button", { name: "Redo", exact: true }).click();
  await expect(page.getByLabel("Height", { exact: true })).toHaveValue("27");
  expect(errors).toEqual([]);
});
test("measures a real BREP face and imports a stored STL reference without claiming feature history", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await page.locator("canvas").waitFor();
  await page
    .getByRole("button", { name: "Measure geometry", exact: true })
    .click();
  await page.getByLabel("Measurement kind").selectOption("area");
  const bounds = (await page.locator("canvas").boundingBox())!;
  await page.mouse.click(
    bounds.x + bounds.width / 2,
    bounds.y + bounds.height * 0.45,
  );
  await expect(page.locator(".measurement-hint")).toContainText("mm²", {
    timeout: 30000,
  });
  await expect(page.locator(".measurement-hint")).toContainText(
    "reopened STEP face",
  );
  await page.getByRole("button", { name: "Close measurement" }).click();
  const projects = await (await request.get("/api/projects")).json();
  const project = await (
    await request.get("/api/projects/" + projects[0].id)
  ).json();
  const stl = await request.get(
    `/api/artifacts/${project.active_revision_id}/assembly.stl`,
  );
  expect(stl.ok()).toBe(true);
  await fs.mkdir(artifacts, { recursive: true });
  const source = path.join(artifacts, "browser-mesh.stl");
  await fs.writeFile(source, await stl.body());
  await page.getByRole("button", { name: "Import reference geometry" }).click();
  await page.getByLabel("Reference geometry file").setInputFiles(source);
  await page
    .getByRole("button", { name: "Import reference", exact: true })
    .click();
  await page
    .locator(".reference-row")
    .filter({ hasText: "browser-mesh" })
    .last()
    .click();
  await expect(page.getByText(/no recovered feature history/)).toBeVisible();
  await expect(page.locator(".reference-preview canvas")).toBeVisible();
  await page
    .getByRole("link", { name: "Download original reference" })
    .isVisible();
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page.reload();
  await expect(
    page.locator(".reference-row").filter({ hasText: "browser-mesh" }).last(),
  ).toBeVisible();
});
