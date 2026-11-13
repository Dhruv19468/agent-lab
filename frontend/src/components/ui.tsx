import { LoaderCircle, TriangleAlert, X } from "lucide-react";
import { useEffect } from "react";
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

import { errorMessage } from "../lib/api";
import type { AgentStatus } from "../lib/types";

export function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

/* ---------------------------------------------------------------------------- buttons */

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const buttonStyles: Record<ButtonVariant, string> = {
  primary: "bg-signal-500 text-ink-950 hover:bg-signal-400 border border-signal-600/40 font-semibold",
  secondary: "bg-surface text-ink-900 border border-line-strong hover:border-ink-400 hover:bg-paper",
  ghost: "bg-transparent text-ink-700 border border-transparent hover:bg-ink-900/5",
  danger: "bg-surface text-bad-600 border border-bad-600/30 hover:bg-bad-50",
};

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: "sm" | "md";
  loading?: boolean;
  icon?: ReactNode;
};

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon,
  className,
  children,
  disabled,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-md whitespace-nowrap transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "h-8 px-3 text-sm" : "h-10 px-4 text-[14px]",
        buttonStyles[variant],
        className,
      )}
      {...props}
    >
      {loading ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

/* ---------------------------------------------------------------------------- badges */

type Tone = "neutral" | "signal" | "ok" | "bad" | "ink";

const toneStyles: Record<Tone, string> = {
  neutral: "bg-paper text-ink-700 border-line",
  signal: "bg-signal-50 text-signal-800 border-signal-100",
  ok: "bg-ok-50 text-ok-800 border-ok-600/20",
  bad: "bg-bad-50 text-bad-800 border-bad-600/20",
  ink: "bg-ink-900 text-white border-ink-900",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium", toneStyles[tone])}>
      {children}
    </span>
  );
}

const statusTone: Record<AgentStatus, Tone> = {
  DRAFT: "neutral",
  ACTIVE: "ok",
  INACTIVE: "signal",
  ARCHIVED: "neutral",
};

const statusLabel: Record<AgentStatus, string> = {
  DRAFT: "Draft",
  ACTIVE: "Active",
  INACTIVE: "Paused",
  ARCHIVED: "Archived",
};

export function StatusBadge({ status }: { status: AgentStatus }) {
  return (
    <Badge tone={statusTone[status]}>
      <span
        aria-hidden
        className={cx(
          "size-1.5 rounded-full",
          status === "ACTIVE" ? "bg-ok-600" : status === "INACTIVE" ? "bg-signal-500" : "bg-ink-400",
        )}
      />
      {statusLabel[status]}
    </Badge>
  );
}

/** Small mono chip for code-like values: tool names, trigger phrases. */
export function Chip({ children, onRemove }: { children: ReactNode; onRemove?: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-line bg-paper px-2 py-0.5 font-mono text-[12.5px] text-ink-800">
      {children}
      {onRemove && (
        <button type="button" onClick={onRemove} className="text-ink-400 hover:text-bad-600" aria-label="Remove">
          <X className="size-3.5" />
        </button>
      )}
    </span>
  );
}

/* ---------------------------------------------------------------------------- form controls */

const controlBase =
  "w-full rounded-md border border-line-strong bg-surface px-3 text-[14px] text-ink-900 placeholder:text-ink-400 " +
  "focus:border-ink-700 focus:outline-none focus:ring-2 focus:ring-signal-400/40 disabled:bg-paper";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx(controlBase, "h-10", className)} {...props} />;
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cx(controlBase, "py-2 leading-relaxed", className)} {...props} />;
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cx(controlBase, "h-10 pr-8", className)} {...props}>
      {children}
    </select>
  );
}

export function Field({
  label,
  hint,
  error,
  htmlFor,
  children,
}: {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  htmlFor?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-sm font-medium text-ink-800">
        {label}
      </label>
      {children}
      {error ? (
        <p className="text-sm text-bad-600">{error}</p>
      ) : hint ? (
        <p className="text-sm text-ink-500">{hint}</p>
      ) : null}
    </div>
  );
}

/* ---------------------------------------------------------------------------- layout pieces */

export function PageHeader({
  title,
  description,
  actions,
  back,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  back?: ReactNode;
}) {
  return (
    <header className="mb-8 border-b border-line pb-6">
      {back && <div className="mb-3">{back}</div>}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-[24px] leading-tight font-semibold tracking-[-0.015em] text-ink-950">{title}</h1>
          {description && <div className="mt-2 max-w-[68ch] text-ink-500">{description}</div>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </div>
    </header>
  );
}

/** A titled region of a page. Bordered, flat: hierarchy comes from the heading, not a shadow. */
export function Section({
  title,
  description,
  actions,
  children,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cx("rounded-lg border border-line bg-surface", className)}>
      <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
        <div>
          <h2 className="font-semibold text-ink-950">{title}</h2>
          {description && <p className="mt-0.5 text-sm text-ink-500">{description}</p>}
        </div>
        {actions}
      </div>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line-strong bg-surface px-6 py-12 text-center">
      <p className="font-semibold text-ink-900">{title}</p>
      {body && <p className="mx-auto mt-1.5 max-w-[52ch] text-ink-500">{body}</p>}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-10 text-ink-500" role="status">
      <LoaderCircle className="size-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorNotice({ error, title = "This didn't load" }: { error: unknown; title?: string }) {
  return (
    <div className="flex gap-3 rounded-lg border border-bad-600/25 bg-bad-50 px-4 py-3 text-bad-800" role="alert">
      <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>
        <p className="font-medium">{title}</p>
        <p className="text-sm">{errorMessage(error)}</p>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------------- tables */

export function Table({ head, children }: { head: ReactNode; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full text-left text-[14px]">
        <thead className="border-b border-line bg-paper/60 text-sm text-ink-500">
          <tr>{head}</tr>
        </thead>
        <tbody className="divide-y divide-line">{children}</tbody>
      </table>
    </div>
  );
}

export function Th({ children, className }: { children?: ReactNode; className?: string }) {
  return <th className={cx("px-4 py-2.5 font-medium", className)}>{children}</th>;
}

export function Td({ children, className }: { children?: ReactNode; className?: string }) {
  return <td className={cx("px-4 py-3 align-top", className)}>{children}</td>;
}

/* ---------------------------------------------------------------------------- dialogs */

export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
  wide = false,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-ink-950/45 p-4 pt-[10vh]">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cx("stack-in w-full rounded-lg border border-line bg-surface shadow-xl shadow-ink-950/15", wide ? "max-w-2xl" : "max-w-lg")}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="font-semibold text-ink-950">{title}</h2>
          <button type="button" onClick={onClose} className="rounded p-1 text-ink-400 hover:bg-paper hover:text-ink-900" aria-label="Close">
            <X className="size-4" />
          </button>
        </div>
        <div className="space-y-4 px-5 py-5">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  onConfirm,
  onClose,
  loading,
}: {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onClose: () => void;
  loading?: boolean;
}) {
  return (
    <Modal
      open={open}
      title={title}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="text-ink-700">{body}</div>
    </Modal>
  );
}

/* ---------------------------------------------------------------------------- tabs */

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: Array<{ id: T; label: string }>;
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <div role="tablist" className="mb-6 flex gap-6 overflow-x-auto border-b border-line">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={value === tab.id}
          onClick={() => onChange(tab.id)}
          className={cx(
            "-mb-px border-b-2 pb-3 text-[14px] whitespace-nowrap transition-colors",
            value === tab.id ? "border-signal-500 font-semibold text-ink-950" : "border-transparent text-ink-500 hover:text-ink-900",
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
