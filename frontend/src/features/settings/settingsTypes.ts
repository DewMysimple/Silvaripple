import type { Settings } from "../../types";

export interface SettingsSectionProps {
  settings: Settings;
  saving: boolean;
  onChange(value: Partial<Settings>): void;
}
