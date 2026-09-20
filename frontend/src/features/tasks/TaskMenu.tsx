import {
  useEffect,
  useId,
  useRef,
  useState,
  type ComponentType,
  type KeyboardEvent,
  type ReactNode,
} from "react";

type MenuAction = {
  label: string;
  description?: string;
  icon: ComponentType<{ size?: number }>;
  disabled?: boolean;
  danger?: boolean;
  onSelect(): void;
};

export function TaskMenu({
  label,
  children,
  actions,
  disabled,
  compact = false,
}: {
  label: string;
  children: ReactNode;
  actions: MenuAction[];
  disabled?: boolean;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const anchor = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const id = useId();
  const buttons = () =>
    Array.from(
      menu.current?.querySelectorAll<HTMLButtonElement>(
        "button:not(:disabled)",
      ) ?? [],
    );
  useEffect(() => {
    if (!open) return;
    buttons()[0]?.focus();
    const dismiss = (event: PointerEvent) => {
      if (!anchor.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, [open]);

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "Tab") {
      setOpen(false);
      trigger.current?.focus();
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
      trigger.current?.focus();
      return;
    }
    const items = buttons();
    if (
      !items.length ||
      !["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)
    )
      return;
    event.preventDefault();
    const current = items.indexOf(document.activeElement as HTMLButtonElement);
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? items.length - 1
          : (current + (event.key === "ArrowDown" ? 1 : -1) + items.length) %
            items.length;
    items[next]?.focus();
  }

  return (
    <div
      className={`task-menu-anchor ${compact ? "row-menu-anchor" : ""}`}
      ref={anchor}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null))
          setOpen(false);
      }}
    >
      <button
        ref={trigger}
        type="button"
        className={compact ? "icon-button" : "secondary compact"}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        {children}
      </button>
      {open && (
        <div
          ref={menu}
          id={id}
          className="task-action-menu"
          role="menu"
          aria-label={label}
          onKeyDown={onKeyDown}
        >
          {actions.map(({ icon: Icon, ...action }) => (
            <button
              key={action.label}
              type="button"
              role="menuitem"
              tabIndex={-1}
              className={action.danger ? "danger" : undefined}
              disabled={action.disabled}
              onClick={() => {
                setOpen(false);
                trigger.current?.focus();
                action.onSelect();
              }}
            >
              <Icon size={16} />
              <span>
                <strong>{action.label}</strong>
                {action.description && <small>{action.description}</small>}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
