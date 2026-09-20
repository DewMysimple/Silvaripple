import { expect, test, type Page } from "@playwright/test";

const navigate = (page: Page, name: string) =>
  page
    .getByRole("navigation", { name: "主导航" })
    .getByRole("button", { name, exact: true })
    .click();

test("selecting, filtering and exporting keeps the selection usable", async ({
  page,
}) => {
  await page.goto("/");
  await navigate(page, "会话浏览");
  await page
    .getByRole("button", { name: "选择会话 设计讨论群", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "搜索会话名称", exact: true })
    .fill("家人");
  await expect(
    page.getByRole("button", { name: "预览 家人群", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "导出已选 1 个会话" }).click();
  await expect(page.getByText("设计讨论群", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "开始导出", exact: true }).click();
  await expect(page.getByRole("heading", { name: "归档已完成" })).toBeVisible();
});

test("search and media checks expose real results and consistent scope", async ({
  page,
}) => {
  await page.goto("/");
  await navigate(page, "全局搜索");
  await page.getByRole("textbox", { name: "搜索聊天内容" }).fill("记录");
  await page.getByRole("button", { name: "搜索聊天", exact: true }).click();
  await expect(page.locator(".search-result").first()).toBeVisible();
  await page.locator(".search-result").first().click();
  await expect(page.locator(".preview-header strong")).toBeVisible();
  await navigate(page, "媒体完整性");
  await expect(
    page.getByRole("button", { name: "整个账号 当前账号的全部会话" }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "开始检查", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "按媒体类型查看" }),
  ).toBeVisible();
});

for (const width of [1080, 1440, 1920]) {
  test(`all workspaces remain usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/");
    for (const name of [
      "首页",
      "会话浏览",
      "全局搜索",
      "导出工作台",
      "媒体完整性",
      "任务与记录",
      "设置",
    ]) {
      await navigate(page, name);
      await expect(page.locator(".view-content")).toBeVisible();
      const overflow = await page
        .locator(".view-content")
        .evaluate((element) => element.scrollWidth > element.clientWidth + 2);
      expect(overflow, `${name} must fit the ${width}px window`).toBe(false);
    }
    expect(errors).toEqual([]);
  });
}

test("dark appearance and large text work throughout the application", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1080, height: 900 });
  await page.goto("/?theme=dark");
  await navigate(page, "设置");
  await page.getByRole("button", { name: /外观与显示/ }).click();
  await page.getByLabel("字体大小").selectOption("large");
  await expect(page.locator("html")).toHaveAttribute(
    "data-font-scale",
    "large",
  );
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  for (const name of [
    "首页",
    "会话浏览",
    "全局搜索",
    "导出工作台",
    "媒体完整性",
    "任务与记录",
    "设置",
  ]) {
    await navigate(page, name);
    expect(
      await page
        .locator(".view-content")
        .evaluate((element) => element.scrollWidth > element.clientWidth + 2),
      name,
    ).toBe(false);
  }
});
