import type { Settings } from "../types";

export function applyTheme(settings?: Settings) {
  if (!settings) return () => undefined;
  const media = matchMedia("(prefers-color-scheme: dark)");
  const update = () => {
    const dark =
      settings.theme === "dark" ||
      (settings.theme === "system" && media.matches);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    document.documentElement.dataset.fontScale = settings.font_scale;
    document.documentElement.dataset.density = settings.density;
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", dark ? "#191919" : "#ffffff");
  };
  update();
  media.addEventListener("change", update);
  return () => media.removeEventListener("change", update);
}
