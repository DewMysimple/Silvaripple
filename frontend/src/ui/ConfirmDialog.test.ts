import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { deferred } from "../test/fixtures";
import { ConfirmDialog, type ConfirmRequest } from "./ConfirmDialog";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let root: Root;
let element: HTMLDivElement;
const onClose = vi.fn();
beforeEach(() => {
  onClose.mockReset();
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
});
afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
});
const show = (onConfirm: ConfirmRequest["onConfirm"]) =>
  act(async () => {
    root.render(
      createElement(ConfirmDialog, {
        request: {
          title: "清理记录",
          description: "删除已完成任务的历史记录。",
          confirmLabel: "确认清理",
          onConfirm,
        },
        onClose,
      }),
    );
  });
const buttons = () =>
  Array.from(element.querySelectorAll<HTMLButtonElement>("button"));
const keyboard = (key: string, shiftKey = false) =>
  document.dispatchEvent(
    new KeyboardEvent("keydown", {
      key,
      shiftKey,
      bubbles: true,
      cancelable: true,
    }),
  );

describe("shared confirmation dialog", () => {
  it("submits only once even when clicked twice before React renders the busy state", async () => {
    const pending = deferred<void>();
    const confirm = vi.fn(() => pending.promise);
    await show(confirm);
    await act(async () => {
      buttons()[1].click();
      buttons()[1].click();
    });
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(buttons().every((button) => button.disabled)).toBe(true);
    expect(
      element.querySelector('[role="alertdialog"]')?.getAttribute("aria-busy"),
    ).toBe("true");
    await act(async () => pending.resolve());
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("keeps a failed operation open with an accessible error and permits retry", async () => {
    const confirm = vi
      .fn()
      .mockRejectedValueOnce(new Error("记录正在使用，请稍后重试"))
      .mockResolvedValueOnce(undefined);
    await show(confirm);
    await act(async () => buttons()[1].click());
    expect(onClose).not.toHaveBeenCalled();
    expect(element.querySelector('[role="alert"]')?.textContent).toBe(
      "记录正在使用，请稍后重试",
    );
    expect(buttons()[1].disabled).toBe(false);
    await act(async () => buttons()[1].click());
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("starts at the non-destructive action and traps Tab navigation inside the dialog", async () => {
    await show(async () => {});
    const [cancel, confirm] = buttons();
    expect(document.activeElement).toBe(cancel);
    await act(async () => {
      keyboard("Tab", true);
    });
    expect(document.activeElement).toBe(confirm);
    await act(async () => {
      keyboard("Tab");
    });
    expect(document.activeElement).toBe(cancel);
  });

  it("does not close on Escape or backdrop clicks while submission is pending", async () => {
    const pending = deferred<void>();
    await show(() => pending.promise);
    await act(async () => buttons()[1].click());
    await act(async () => {
      keyboard("Escape");
      element
        .querySelector(".dialog-backdrop")
        ?.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    });
    expect(onClose).not.toHaveBeenCalled();
    await act(async () => pending.resolve());
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("allows Escape before submission without invoking the destructive action", async () => {
    const confirm = vi.fn();
    await show(confirm);
    await act(async () => {
      keyboard("Escape");
    });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(confirm).not.toHaveBeenCalled();
  });
});
