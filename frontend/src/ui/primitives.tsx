import type { ComponentType, ReactNode } from "react";
import type { Operation } from "../types";

type IconComponent = ComponentType<{ size?: number }>;

export function GreenSwitch({
  checked,
  disabled = false,
  onChange,
  label,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange(value: boolean): void;
  label: string;
}) {
  return (
    <input
      className="green-switch"
      type="checkbox"
      checked={checked}
      disabled={disabled}
      onChange={(event) => onChange(event.target.checked)}
      aria-label={label}
    />
  );
}

export function BrandMark() {
  return (
    <div className="brand-mark" aria-hidden="true">
      <span />
      <span />
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  text,
  action,
}: {
  icon: IconComponent;
  title: string;
  text: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <Icon size={26} />
      </div>
      <strong>{title}</strong>
      <p>{text}</p>
      {action}
    </div>
  );
}

export function Stat({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: ReactNode;
  detail: string;
  icon: IconComponent;
}) {
  return (
    <article className="stat">
      <div className="stat-icon">
        <Icon size={18} />
      </div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

export function Progress({ operation }: { operation: Operation }) {
  return (
    <div className="progress-card">
      <div>
        <strong>{operation.message}</strong>
        <span>{Math.round(operation.progress * 100)}%</span>
      </div>
      <div className="progress-track">
        <i style={{ width: `${Math.max(2, operation.progress * 100)}%` }} />
      </div>
      {operation.error && <p className="error-text">{operation.error}</p>}
    </div>
  );
}
