import { test, expect, type Page } from "@playwright/test";

const username = process.env.WEB_TEST_USER;
const password = process.env.WEB_TEST_PASSWORD;
test.skip(
  !username || !password,
  "请设置专用测试账号 WEB_TEST_USER / WEB_TEST_PASSWORD",
);

async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("账号", { exact: true }).fill(username!);
  await page.getByLabel("密码", { exact: true }).fill(password!);
  await page.getByRole("button", { name: "进入工作台" }).click();
  await expect(
    page.getByRole("heading", { name: "反应器选型与模拟分析" }),
  ).toBeVisible();
}

test("登录、工作台、模式说明与退出", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.screenshot({ path: "test-results/login.png", fullPage: true });
  await login(page);
  await expect(page.getByRole("button", { name: /载入示例/ })).toHaveCount(3);
  await page.screenshot({ path: "test-results/workspace.png", fullPage: true });
  await page.getByRole("button", { name: "查看运行模式说明" }).click();
  await expect(page.getByRole("dialog")).toContainText("当前运行模式：Mock");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page.getByRole("heading", { name: "欢迎回来" })).toBeVisible();
  expect((await page.request.get("/api/tasks")).status()).toBe(401);
});

for (const [label, reactor] of [
  ["可逆反应 · 平衡控制", "平衡反应器"],
  ["明确给定转化率", "转化反应器"],
  ["复杂体系 · 路径未知", "吉布斯反应器"],
]) {
  test(`真实页面端到端：${reactor}`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await login(page);
    await page.getByRole("button", { name: new RegExp(label) }).click();
    await page.getByRole("button", { name: "开始分析" }).click();
    await expect(page.locator(".status-pill")).toHaveText("待确认参数", {
      timeout: 15000,
    });
    await expect(page.locator(".recommendation h2")).toHaveText(reactor);
    if (reactor === "转化反应器") {
      await page.getByLabel("温度", { exact: false }).fill("");
      await page.getByRole("button", { name: "确认参数并运行" }).click();
      await expect(page.locator(".status-pill")).toHaveText("待补充参数", {
        timeout: 15000,
      });
      await expect(page.locator(".missing-list")).toContainText("温度");
      await expect(page.locator(".progress-steps li").nth(2)).toContainText(
        "发现缺项",
      );
      await page.locator(".execution-details summary").click();
      await expect(page.locator(".execution-details")).toContainText(
        "等待补充参数",
      );
      await expect(page.locator(".execution-details")).not.toContainText(
        "流程结束",
      );
      await page.getByLabel("温度", { exact: false }).fill("873.15");
    }
    await page.getByRole("button", { name: "确认参数并运行" }).click();
    await expect(page.locator(".status-pill")).toHaveText("已完成", {
      timeout: 15000,
    });
    await expect(page.locator(".task-lineage")).toContainText("修订");
    await expect(page.locator(".result-card")).toContainText("Mock");
    await expect(page.locator(".result-card")).toContainText(
      "未进行真实 HYSYS 计算",
    );
    const url = page.url();
    await page.reload();
    await expect(page.locator(".status-pill")).toHaveText("已完成");
    expect(page.url()).toBe(url);
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出记录" }).click();
    expect((await download).suggestedFilename()).toMatch(/^hysys-.+\.json$/);
    await page.screenshot({
      path: `test-results/${reactor}.png`,
      fullPage: true,
    });
    expect(errors).toEqual([]);
  });
}

test("窄屏导航与表单无横向溢出", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await expect(
    page.getByRole("button", { name: "打开任务列表" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "打开任务列表" }).click();
  await page.getByRole("button", { name: "新建分析" }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/mobile.png",
    fullPage: true,
    animations: "disabled",
  });
});

test("修改条件立即显示专用参数，表格式方程与后端一致", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: /复杂体系 · 路径未知/ }).click();
  await page.getByRole("button", { name: "开始分析" }).click();
  await expect(page.locator(".status-pill")).toHaveText("待确认参数");
  const originalUrl = page.url();
  await page.locator(".condition-details summary").click();
  await page
    .getByRole("combobox", { name: /是否明确给定转化率/ })
    .selectOption("true");
  await page.getByLabel("转化率 %", { exact: false }).fill("80");
  await expect(page.getByLabel("转化基准组分")).toBeVisible();
  await expect(page.locator(".selection-preview")).toContainText("转化反应器");
  expect(page.url()).toBe(originalUrl);
  await page
    .getByRole("combobox", { name: /是否明确给定转化率/ })
    .selectOption("false");
  await page
    .getByRole("combobox", { name: /是否为可逆反应/ })
    .selectOption("true");
  await page
    .getByRole("combobox", { name: /是否受平衡控制/ })
    .selectOption("true");
  await page
    .getByRole("combobox", { name: /反应路径是否明确/ })
    .selectOption("true");
  await expect(page.getByLabel("平衡数据来源 / 方法")).toBeVisible();
  await expect(page.getByLabel("转化基准组分")).toHaveCount(0);
  await page
    .getByRole("combobox", { name: /是否明确给定转化率/ })
    .selectOption("true");
  await page.getByLabel("转化基准组分").fill("CH4");
  await page.getByRole("button", { name: "添加反应方程" }).click();
  await page.getByLabel("反应 1 第 1 项组分").fill("CH4");
  await page.getByLabel("反应 1 第 2 项组分").fill("H2O");
  await page.getByLabel("反应 1 第 2 项方向").selectOption("reactant");
  await page.getByRole("button", { name: "添加组分项" }).click();
  await page.getByLabel("反应 1 第 3 项组分").fill("CO");
  await page.getByRole("button", { name: "添加组分项" }).click();
  await page.getByLabel("反应 1 第 4 项组分").fill("H2");
  await page.getByLabel("反应 1 第 4 项系数").fill("3");
  await page.getByRole("button", { name: "添加组分项" }).click();
  await page.getByRole("button", { name: "删除反应 1 第 5 项" }).click();
  await page.getByRole("button", { name: "确认参数并运行" }).click();
  await expect(page.locator(".status-pill")).toHaveText("已完成");
  await expect(page.locator(".recommendation h2")).toHaveText("转化反应器");
  const response = await page.request.get(
    "/api/tasks/" + page.url().split("#")[1],
  );
  const task = await response.json();
  expect(task.state.simulation_inputs.reactions).toEqual([
    { CH4: -1, H2O: -1, CO: 1, H2: 3 },
  ]);
  expect(task.revision).toBe(1);
  await page.getByRole("button", { name: "查看上一版本" }).click();
  await expect(page).toHaveURL(originalUrl);
  await expect(page.locator(".task-lineage")).toContainText("原始分析");
});

test("历史翻页与服务端搜索", async ({ page }) => {
  await login(page);
  const session = await (await page.request.get("/api/session")).json();
  const history = await (await page.request.get("/api/task-history")).json();
  if (history.total <= 20) {
    const examples = await (await page.request.get("/api/examples")).json();
    for (let index = history.total; index <= 20; index++) {
      const response = await page.request.post("/api/tasks", {
        headers: {
          Origin: new URL(page.url()).origin,
          "X-CSRF-Token": session.csrf,
        },
        data: {
          query: `分页测试 ${index}`,
          idempotency_key: crypto.randomUUID(),
          reaction_info: examples[0].reaction_info,
          simulation_inputs: examples[0].simulation_inputs,
        },
      });
      expect(response.status()).toBe(202);
    }
  }
  await expect(page.getByRole("button", { name: "下一页" })).toBeEnabled();
  await page.getByRole("button", { name: "下一页" }).click();
  await expect(page.locator(".history-pagination")).toContainText("2 /");
  await page.getByRole("button", { name: "上一页" }).click();
  await expect(page.locator(".history-pagination")).toContainText("1 /");
  await page.getByLabel("搜索任务").fill("甲烷、水和二氧化碳");
  await expect(page.locator(".task-item").first()).toContainText(
    "甲烷、水和二氧化碳",
  );
  await expect(page.locator(".revision-label").first()).toBeVisible();
  await page.getByLabel("搜索任务").fill("不存在的历史xyz");
  await expect(page.locator(".history-empty")).toHaveText("没有匹配的任务");
});
