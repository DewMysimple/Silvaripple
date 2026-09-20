import { invoke as invokeTauri } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import type { Envelope } from "./bridge/envelope";

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

const hasTauriBridge = () => Boolean(window.__TAURI_INTERNALS__);

export async function invoke<T>(
  method: string,
  ...args: unknown[]
): Promise<T> {
  let envelope: Envelope<T>;
  if (hasTauriBridge()) {
    if (method === "choose_folder") {
      const path = await open({ directory: true, multiple: false });
      envelope = { ok: true, data: { path } as T };
    } else {
      envelope = await invokeTauri<Envelope<T>>("bridge_invoke", {
        method,
        args,
      });
    }
  } else if (import.meta.env.DEV) {
    const { mockApi } = await import("./bridge/mock");
    const fn = mockApi[method];
    if (!fn) throw new Error(`桌面接口不可用：${method}`);
    envelope = (await fn(...args)) as Envelope<T>;
  } else {
    throw new Error("Tauri 桌面服务尚未就绪。请重新启动 ChatWechat。");
  }
  if (!envelope.ok) throw new Error(envelope.error || "操作失败");
  return envelope.data;
}

export const isMockBridge = () => !hasTauriBridge();
