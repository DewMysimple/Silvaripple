import { expect, test, type Locator, type Page } from "@playwright/test";

const workspaces = [
  "首页",
  "会话浏览",
  "全局搜索",
  "导出工作台",
  "媒体完整性",
  "任务与记录",
  "设置",
];

const navigate = (page: Page, name: string) =>
  page
    .getByRole("navigation", { name: "主导航" })
    .getByRole("button", { name, exact: true })
    .click();

// Inspect rendered colors, not stylesheet text: this also catches local overrides.
async function expectNeutralSurfaces(locator: Locator) {
  const surfaces = await locator.evaluateAll((elements) =>
    elements.map((element) => {
      const style = getComputedStyle(element);
      return {
        element: element.className,
        background: style.backgroundColor,
        image: style.backgroundImage,
      };
    }),
  );
  expect(surfaces.length).toBeGreaterThan(0);
  for (const surface of surfaces) {
    const channels = surface.background.match(/[\d.]+/g)?.map(Number) ?? [];
    if (channels[3] !== 0) {
      expect(channels[0], `${surface.element}: red/green`).toBe(channels[1]);
      expect(channels[1], `${surface.element}: green/blue`).toBe(channels[2]);
    }
    expect(surface.image, `${surface.element}: no decorative gradient`).toBe(
      "none",
    );
  }
}

for (const theme of ["light", "dark"]) {
  test(`${theme}: neutral workspaces and readable primary actions`, async ({
    page,
  }, testInfo) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto(`/?theme=${theme}`);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    if (theme === "light") {
      await expect(page.locator(".main-canvas")).toHaveCSS(
        "background-color",
        "rgb(255, 255, 255)",
      );
    }
    for (const name of workspaces) {
      await navigate(page, name);
      await expectNeutralSurfaces(
        page.locator(
          ".main-canvas, .sidebar, .topbar, .panel, .stat, .home-welcome, .preview-panel, .settings-navigation",
        ),
      );
      const textColors = await page
        .locator(".topbar h1, .topbar-subtitle, .page-intro h2, .page-intro p")
        .evaluateAll((elements) =>
          elements.map((element) =>
            getComputedStyle(element).color.match(/\d+/g)!.map(Number),
          ),
        );
      for (const [red, green, blue] of textColors) {
        expect(red, `${name}: neutral heading and supporting text`).toBe(green);
        expect(green).toBe(blue);
      }
      const contrast = await page
        .locator(".primary:enabled")
        .evaluateAll((buttons) => {
          const luminance = (color: string) => {
            const rgb = (color.match(/[\d.]+/g) ?? [])
              .slice(0, 3)
              .map(Number)
              .map((value) => {
                const channel = value / 255;
                return channel <= 0.04045
                  ? channel / 12.92
                  : ((channel + 0.055) / 1.055) ** 2.4;
              });
            return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
          };
          return buttons.map((button) => {
            const style = getComputedStyle(button);
            const text = luminance(style.color);
            const background = luminance(style.backgroundColor);
            return (
              (Math.max(text, background) + 0.05) /
              (Math.min(text, background) + 0.05)
            );
          });
        });
      for (const ratio of contrast) expect(ratio).toBeGreaterThanOrEqual(4.5);
      await testInfo.attach(`${theme}-${name}`, {
        body: await page.screenshot(),
        contentType: "image/png",
      });
    }
  });
}

test("neutral selections retain checkmarks, state and keyboard focus", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/?theme=light");
  await navigate(page, "导出工作台");
  const format = page.locator(".export-format-option").first();
  const checkbox = format.getByRole("checkbox");
  await expect(checkbox).toBeChecked();
  await expectNeutralSurfaces(format);
  await format.click();
  await expect(checkbox).not.toBeChecked();
  await checkbox.focus();
  await page.keyboard.press("Space");
  await expect(checkbox).toBeChecked();
  expect(
    await format.evaluate((element) => element.matches(":focus-within")),
  ).toBe(true);
  expect(
    await format.evaluate((element) => getComputedStyle(element).outlineStyle),
  ).toBe("solid");
  const check = format.locator(".export-format-check");
  await expect(check.locator("svg")).toBeVisible();
  expect(
    await check.evaluate((element) => {
      const rgb = getComputedStyle(element)
        .backgroundColor.match(/\d+/g)!
        .map(Number);
      return rgb[1] > rgb[0] && rgb[1] > rgb[2];
    }),
  ).toBe(true);
  await navigate(page, "设置");
  await page.getByRole("button", { name: /归档与存储/ }).click();
  await expectNeutralSurfaces(
    page.locator(".settings-layout-options > button.selected"),
  );
  await expect(
    page.locator(
      ".settings-layout-options .selected .settings-layout-check svg",
    ),
  ).toBeVisible();
});
