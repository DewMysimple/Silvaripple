import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useWorkbench } from "../../store";
import type { Settings } from "../../types";
import { SettingsView } from "./SettingsView";
import { MediaSettings } from "./ExportSettings";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
const initialStore = useWorkbench.getState();
const settings: Settings = {
  data_root: "test-data",
  data_root_mode: "auto",
  output_directory: "test-output",
  theme: "light",
  conversation_kind: "all",
  last_account_id: "",
  font_scale: "standard",
  density: "comfortable",
  download_missing_media_default: true,
  allow_legacy_http_media_default: false,
  visual_download_limit_mib: 50,
  audio_download_limit_mib: 100,
  large_download_limit_mib: 500,
  open_result_folder_after_export: false,
  export_folder_layout: "by_type",
};
let root: Root;
let element: HTMLDivElement;
beforeEach(() => {
  useWorkbench.setState({
    ...initialStore,
    settings,
    accounts: [],
    dataRoots: [],
  });
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
});
afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
  useWorkbench.setState(initialStore, true);
});
const clickCategory = async (label: string) => {
  const button = [
    ...element.querySelectorAll<HTMLButtonElement>("nav button"),
  ].find((item) => item.textContent?.includes(label));
  expect(button).toBeDefined();
  await act(async () => button?.click());
};

describe("settings category navigation", () => {
  it("shows one category at a time and keeps every settings group reachable", async () => {
    await act(async () => root.render(createElement(SettingsView)));
    expect(element.querySelector(".data-source-picker")).not.toBeNull();
    expect(element.querySelector('[aria-label="主题"]')).toBeNull();
    await clickCategory("外观与显示");
    expect(element.querySelector(".data-source-picker")).toBeNull();
    expect(element.querySelector('[aria-label="主题"]')).not.toBeNull();
    await clickCategory("归档与存储");
    expect(element.querySelector(".settings-layout-options")).not.toBeNull();
    await clickCategory("媒体恢复");
    expect(element.querySelectorAll('input[type="number"]')).toHaveLength(3);
    await clickCategory("隐私与行为");
    expect(
      element.querySelectorAll(".settings-privacy-list article"),
    ).toHaveLength(3);
    expect(element.querySelectorAll('input[type="number"]')).toHaveLength(0);
  });

  it("reports a failed save without claiming that preferences were saved", async () => {
    useWorkbench.setState({
      saveSettings: vi.fn().mockRejectedValue(new Error("设置文件暂时不可写")),
    });
    await act(async () => root.render(createElement(SettingsView)));
    await clickCategory("外观与显示");
    const select =
      element.querySelector<HTMLSelectElement>('[aria-label="主题"]')!;
    await act(async () => {
      select.value = "dark";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(element.querySelector('[role="alert"]')?.textContent).toContain(
      "设置文件暂时不可写",
    );
    expect(element.querySelector('[role="status"]')?.textContent).toContain(
      "未能保存",
    );
  });
});

describe("download limits", () => {
  it("commits a validated limit after editing, not after each keystroke", async () => {
    const change = vi.fn();
    await act(async () =>
      root.render(
        createElement(MediaSettings, {
          settings,
          saving: false,
          onChange: change,
        }),
      ),
    );
    const input = element.querySelector<HTMLInputElement>(
      '[aria-label="图片 / 表情下载上限"]',
    )!;
    const setValue = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!;
    await act(async () => {
      input.focus();
      setValue.call(input, "9999");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(change).not.toHaveBeenCalled();
    await act(async () => input.blur());
    expect(change).toHaveBeenCalledExactlyOnceWith({
      visual_download_limit_mib: 2048,
    });
    expect(input.value).toBe("2048");
  });
});
