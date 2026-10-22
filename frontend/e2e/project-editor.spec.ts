import { expect, test, type Page } from "@playwright/test";
import type { ExportRecord, Project, RallyEvent } from "../src/types";

const PROJECT_ID = "e2e-project";

function createRallies(): RallyEvent[] {
  let scoreA = 0;
  let scoreB = 0;
  return Array.from({ length: 47 }, (_, index) => {
    const winner = index % 2 === 0 ? "A" : "B";
    const scoreBefore = { A: scoreA, B: scoreB };
    if (winner === "A") scoreA += 1;
    else scoreB += 1;
    const start = index * 10;
    const end = start + 5;
    return {
      id: `rally-${index + 1}`,
      order_index: index,
      start_time: start,
      end_time: end,
      score_update_time: end,
      winner,
      is_valid: true,
      is_let: false,
      let_confirmed: true,
      let_candidate: false,
      confidence: 0.9,
      verified: true,
      unresolved: false,
      source: "ai",
      note: null,
      score_before: scoreBefore,
      score_after: { A: scoreA, B: scoreB },
      server_before: winner,
      server_after: winner,
      serve_court_before: scoreBefore[winner] % 2 === 0 ? "right" : "left",
      serve_court_after: { A: scoreA, B: scoreB }[winner] % 2 === 0 ? "right" : "left",
    };
  });
}

const rallies = createRallies();
const project: Project = {
  id: PROJECT_ID,
  title: "自动化测试比赛",
  source_path: "test.mp4",
  preview_path: null,
  thumbnail_path: null,
  source_size: 1024,
  duration: 500,
  width: 1280,
  height: 720,
  fps: 30,
  video_codec: "h264",
  audio_codec: "aac",
  player_a_name: "测试球员 A",
  player_b_name: "测试球员 B",
  initial_a_score: 0,
  initial_b_score: 0,
  first_server: "A",
  first_server_court: "right",
  initial_a_side: "bottom",
  court_points: null,
  status: "ready",
  stage: "分析完成",
  progress: 1,
  error: null,
  timeline: rallies,
  final_score: { A: 24, B: 23 },
  unresolved_count: 0,
  let_count: 0,
  invalid_count: 0,
  side_swaps: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const exports: ExportRecord[] = [
  {
    id: "export-1",
    project_id: PROJECT_ID,
    kind: "highlights",
    status: "ready",
    progress: 1,
    output_path: "highlights.mp4",
    error: null,
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "export-2",
    project_id: PROJECT_ID,
    kind: "full",
    status: "failed",
    progress: 1,
    output_path: "full.mp4",
    error: "导出比分牌对齐已更新，请重新导出",
    created_at: "2026-01-01T00:00:00Z",
  },
];

async function mockProjectApi(page: Page, exportRecords: ExportRecord[] = exports, autoCompleteExports = false) {
  let currentExports = [...exportRecords];
  let exportCounter = 0;
  await page.route("**/api/exports/*/file", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "video/mp4",
      headers: { "content-disposition": 'attachment; filename="export.mp4"' },
      body: "fake video content",
    });
  });
  await page.addInitScript(() => {
    Object.defineProperty(HTMLMediaElement.prototype, "duration", {
      configurable: true,
      get: () => 500,
    });
    Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
      configurable: true,
      get(this: HTMLMediaElement & { __e2eTime?: number }) {
        return this.__e2eTime ?? 0;
      },
      set(this: HTMLMediaElement & { __e2eTime?: number }, value: number) {
        this.__e2eTime = value;
        this.dispatchEvent(new Event("timeupdate"));
      },
    });
    HTMLMediaElement.prototype.play = () => Promise.resolve();
    HTMLMediaElement.prototype.pause = () => undefined;
  });

  await page.route("**/api/projects/e2e-project**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === `/api/projects/${PROJECT_ID}/exports`) {
      if (route.request().method() === "POST" && autoCompleteExports) {
        const body = route.request().postDataJSON() as { kind?: "full" | "highlights" };
        exportCounter += 1;
        const created: ExportRecord = {
          id: `auto-export-${exportCounter}`,
          project_id: PROJECT_ID,
          kind: body.kind ?? "highlights",
          status: "ready",
          progress: 1,
          output_path: `auto-${exportCounter}.mp4`,
          error: null,
          created_at: new Date().toISOString(),
        };
        currentExports = [created, ...currentExports];
        await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(created) });
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(currentExports) });
      return;
    }
    if (url.pathname === `/api/projects/${PROJECT_ID}/video`) {
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    if (url.pathname === `/api/projects/${PROJECT_ID}`) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(project) });
      return;
    }
    await route.fulfill({ status: 404, body: "not found" });
  });
}

async function openEditor(page: Page, width: number, height = 1000, exportRecords: ExportRecord[] = exports, autoCompleteExports = false) {
  await page.setViewportSize({ width, height });
  await mockProjectApi(page, exportRecords, autoCompleteExports);
  await page.goto(`/#/project/${PROJECT_ID}`);
  await expect(page.locator(".score-card")).toBeVisible();
  await expect(page.locator(".timeline-card")).toBeVisible();
  await expect(page.locator(".rally-row")).toHaveCount(47);
}

test.describe("Project editor layout", () => {
  test("keeps the desktop card order, widths, and RALLY LOG bottom alignment", async ({ page }) => {
    await openEditor(page, 1912, 1000);

    await expect
      .poll(() =>
        page.evaluate(() => {
          const log = document.querySelector(".timeline-card")!.getBoundingClientRect();
          const inspector = document.querySelector(".rally-inspector")!.getBoundingClientRect();
          return Math.abs(log.bottom - inspector.bottom);
        }),
      )
      .toBeLessThan(2);
    const order = await page.locator(".review-sidebar > *").evaluateAll((nodes) =>
      nodes.map((node) => node.className),
    );
    expect(order).toEqual([
      "side-card score-card",
      "side-card match-stats-card",
      "side-tools-grid",
      "side-card timeline-card",
    ]);

    const geometry = await page.evaluate(() => {
      const rect = (selector: string) => document.querySelector(selector)!.getBoundingClientRect();
      const sidebar = rect(".review-sidebar");
      const court = rect(".side-events-card");
      const maintenance = rect(".danger-card");
      const exportCard = rect(".export-card");
      const log = rect(".timeline-card");
      const inspector = rect(".rally-inspector");
      const list = document.querySelector(".rally-list") as HTMLElement;
      return {
        sidebarWidth: sidebar.width,
        court: { x: court.x, y: court.y },
        maintenance: { x: maintenance.x, y: maintenance.y },
        exportTop: exportCard.top,
        exportWidth: exportCard.width,
        logBottom: log.bottom,
        inspectorBottom: inspector.bottom,
        listClientHeight: list.clientHeight,
        listScrollHeight: list.scrollHeight,
        scoreFontSize: getComputedStyle(document.querySelector(".side-score strong")!).fontSize,
      };
    });

    expect(Math.abs(geometry.court.y - geometry.maintenance.y)).toBeLessThan(2);
    expect(geometry.maintenance.x).toBeGreaterThan(geometry.court.x);
    expect(geometry.exportTop).toBeGreaterThan(geometry.court.y);
    expect(Math.abs(geometry.exportWidth - geometry.sidebarWidth)).toBeLessThan(2);
    expect(Math.abs(geometry.logBottom - geometry.inspectorBottom)).toBeLessThan(2);
    expect(geometry.listScrollHeight).toBeGreaterThan(geometry.listClientHeight);
    expect(parseFloat(geometry.scoreFontSize)).toBeLessThanOrEqual(40);
  });

  test("keeps RALLY LOG aligned at a narrower desktop width", async ({ page }) => {
    await openEditor(page, 1106, 900);

    await expect
      .poll(() =>
        page.evaluate(() => {
          const log = document.querySelector(".timeline-card")!.getBoundingClientRect();
          const inspector = document.querySelector(".rally-inspector")!.getBoundingClientRect();
          return Math.abs(log.bottom - inspector.bottom);
        }),
      )
      .toBeLessThan(2);

    const list = page.locator(".rally-list");
    expect(await list.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);
  });

  test("selecting rally 47 after rally 46 keeps the final row visible", async ({ page }) => {
    await openEditor(page, 1106, 900);
    const list = page.locator(".rally-list");
    const rows = page.locator(".rally-row-main");

    await list.evaluate((element) => element.scrollTo(0, element.scrollHeight));
    await rows.nth(45).click();
    await expect(page.locator(".rally-inspector .section-kicker")).toContainText("RALLY #46");
    await rows.nth(46).click();
    await expect(page.locator(".rally-inspector .section-kicker")).toContainText("RALLY #47");

    await expect
      .poll(() =>
        page.evaluate(() => {
          const listElement = document.querySelector(".rally-list")!;
          const row = document.querySelectorAll(".rally-row-main")[46];
          const listRect = listElement.getBoundingClientRect();
          const rowRect = row.getBoundingClientRect();
          return rowRect.top >= listRect.top && rowRect.bottom <= listRect.bottom;
        }),
      )
      .toBe(true);
  });

  test("shows before and after scores for each rally", async ({ page }) => {
    await openEditor(page, 1106, 900);
    const score = page.locator(".rally-score").first();
    await expect(score).toContainText("0:0");
    await expect(score).toContainText("→");
    await expect(score).toContainText("1:0");
    await expect(score).toHaveAttribute(
      "aria-label",
      "本回合前 0 比 0，本回合后 1 比 0",
    );
    expect(await score.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  });
  test("shows the export failure reason and retry guidance on hover", async ({ page }) => {
    await openEditor(page, 1106, 900);
    const errorIndicator = page.locator(".export-error-indicator");
    await expect(errorIndicator).toHaveCount(1);
    await errorIndicator.hover();

    const tooltip = page.getByRole("tooltip");
    await expect(tooltip).toBeVisible();
    await expect(tooltip).toContainText("导出比分牌对齐已更新，请重新导出");
    await expect(tooltip).toContainText("请重新导出完整比赛");
  });
  test("hides an older failed export after the same kind succeeds", async ({ page }) => {
    const successfulRetry: ExportRecord[] = [
      {
        ...exports[1],
        id: "export-3",
        status: "ready",
        output_path: "full-retry.mp4",
        error: null,
        created_at: "2026-01-02T00:00:00Z",
      },
      ...exports,
    ];
    await openEditor(page, 1106, 900, successfulRetry);

    await expect(page.locator(".export-error-indicator")).toHaveCount(0);
    const fullRow = page.locator(".export-job").filter({ hasText: "完整比赛" });
    await expect(fullRow).toHaveCount(1);
    await expect(fullRow.locator(".download-link")).toBeVisible();
  });
  test("keeps both export actions visually consistent with hover motion", async ({ page }) => {
    await openEditor(page, 1106, 900);
    const highlights = page.getByRole("button", { name: "导出精彩集锦" });
    const full = page.getByRole("button", { name: "导出完整比赛" });

    const baseStyles = await Promise.all(
      [highlights, full].map((button) =>
        button.evaluate((element) => {
          const style = getComputedStyle(element);
          return {
            background: style.backgroundImage,
            border: style.borderColor,
            color: style.color,
            fontSize: style.fontSize,
            height: style.height,
            icon: element.querySelector("svg")?.innerHTML ?? "",
          };
        }),
      ),
    );
    expect(baseStyles[0]).toEqual(baseStyles[1]);

    const hoverStyles = [];
    for (const button of [highlights, full]) {
      await button.hover();
      await page.waitForTimeout(220);
      hoverStyles.push(
        await button.evaluate((element) => {
          const style = getComputedStyle(element);
          return { transform: style.transform, shadow: style.boxShadow };
        }),
      );
    }
    expect(hoverStyles[0].transform).not.toBe("none");
    expect(hoverStyles[0]).toEqual(hoverStyles[1]);
  });
  test("automatically downloads newly completed exports", async ({ page }) => {
    await openEditor(page, 1106, 900, [], true);
    const highlights = page.getByRole("button", { name: "导出精彩集锦" });
    const full = page.getByRole("button", { name: "导出完整比赛" });

    const highlightsDownload = page.waitForEvent("download");
    await highlights.click();
    expect((await highlightsDownload).suggestedFilename()).toBe("精彩集锦.mp4");

    const fullDownload = page.waitForEvent("download");
    await full.click();
    expect((await fullDownload).suggestedFilename()).toBe("完整比赛.mp4");
  });

  test("stacks the two utility cards on narrow screens", async ({ page }) => {
    await openEditor(page, 640, 900);
    const layout = await page.evaluate(() => {
      const court = document.querySelector(".side-events-card")!.getBoundingClientRect();
      const maintenance = document.querySelector(".danger-card")!.getBoundingClientRect();
      return { courtBottom: court.bottom, maintenanceTop: maintenance.top };
    });
    expect(layout.maintenanceTop).toBeGreaterThan(layout.courtBottom);
  });
});
