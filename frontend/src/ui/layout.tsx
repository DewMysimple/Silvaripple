import { useId, type ReactNode } from "react";

export function PageIntro({
  title,
  description,
  action,
  eyebrow,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  eyebrow?: string;
}) {
  return (
    <div className="page-intro">
      <div>
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {action && <div className="page-intro-actions">{action}</div>}
    </div>
  );
}

export function Panel({
  title,
  description,
  action,
  children,
  className = "",
  id,
}: {
  title?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  const heading = useId();
  return (
    <section
      id={id}
      className={`panel ${className}`}
      aria-labelledby={title ? heading : undefined}
    >
      {title && (
        <header className="panel-heading">
          <div>
            <h3 id={heading}>{title}</h3>
            {description && <p>{description}</p>}
          </div>
          {action}
        </header>
      )}
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger";
}) {
  return <span className={`status-badge ${tone}`}>{children}</span>;
}

export function SettingRow({
  title,
  description,
  children,
  warning = false,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  warning?: boolean;
}) {
  return (
    <div className={`setting-row ${warning ? "warning" : ""}`}>
      <div>
        <strong>{title}</strong>
        {description && <span>{description}</span>}
      </div>
      {children}
    </div>
  );
}

export function ChipGroup({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: ReadonlyArray<{ value: string; label: string }>;
  value: string[];
  onChange(value: string[]): void;
}) {
  return (
    <fieldset className="chip-field">
      <legend>{label}</legend>
      <div className="choice-chips">
        <button
          type="button"
          aria-pressed={!value.length}
          className={!value.length ? "active" : ""}
          onClick={() => onChange([])}
        >
          全部
        </button>
        {options.map((option) => (
          <button
            type="button"
            key={option.value}
            aria-pressed={value.includes(option.value)}
            className={value.includes(option.value) ? "active" : ""}
            onClick={() =>
              onChange(
                value.includes(option.value)
                  ? value.filter((item) => item !== option.value)
                  : [...value, option.value],
              )
            }
          >
            {option.label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
