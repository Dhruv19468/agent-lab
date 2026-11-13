import { Textarea, cx } from "./ui";

/** Returns the parsed object, or an error message when the text isn't a JSON object. */
export function parseJsonObject(text: string): { value: Record<string, unknown> | null; error: string | null } {
  if (!text.trim()) return { value: {}, error: null };
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { value: null, error: "Must be a JSON object, like { ... }." };
    }
    return { value: parsed as Record<string, unknown>, error: null };
  } catch (error) {
    return { value: null, error: error instanceof Error ? error.message : "Not valid JSON." };
  }
}

export function JsonField({
  id,
  value,
  onChange,
  rows = 10,
}: {
  id?: string;
  value: string;
  onChange: (next: string) => void;
  rows?: number;
}) {
  const { error } = parseJsonObject(value);
  return (
    <div className="space-y-1.5">
      <Textarea
        id={id}
        rows={rows}
        spellCheck={false}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={cx("font-mono text-[13px]", error && "border-bad-600 focus:border-bad-600")}
      />
      <div className="flex items-center justify-between text-sm">
        <span className={error ? "text-bad-600" : "text-ok-600"}>{error ?? "Valid JSON"}</span>
        {!error && value.trim() && (
          <button
            type="button"
            className="text-ink-500 underline-offset-2 hover:text-ink-900 hover:underline"
            onClick={() => onChange(JSON.stringify(JSON.parse(value), null, 2))}
          >
            Format
          </button>
        )}
      </div>
    </div>
  );
}
