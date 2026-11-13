import { useState } from "react";

import { Chip, cx } from "./ui";

/** Type a phrase and press Enter (or comma) to add it. Backspace on an empty box removes the last one. */
export function TagInput({
  id,
  value,
  onChange,
  placeholder,
}: {
  id?: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");

  function add(raw: string) {
    const text = raw.trim();
    if (!text) return;
    if (value.some((existing) => existing.toLowerCase() === text.toLowerCase())) {
      setDraft("");
      return;
    }
    onChange([...value, text]);
    setDraft("");
  }

  return (
    <div
      className={cx(
        "flex min-h-10 flex-wrap items-center gap-1.5 rounded-md border border-line-strong bg-surface px-2 py-1.5",
        "focus-within:border-ink-700 focus-within:ring-2 focus-within:ring-signal-400/40",
      )}
    >
      {value.map((phrase) => (
        <Chip key={phrase} onRemove={() => onChange(value.filter((item) => item !== phrase))}>
          {phrase}
        </Chip>
      ))}
      <input
        id={id}
        value={draft}
        placeholder={value.length === 0 ? placeholder : undefined}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => add(draft)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === ",") {
            event.preventDefault();
            add(draft);
          } else if (event.key === "Backspace" && draft === "" && value.length > 0) {
            onChange(value.slice(0, -1));
          }
        }}
        className="min-w-[10ch] flex-1 bg-transparent px-1 py-1 text-[14px] outline-none placeholder:text-ink-400"
      />
    </div>
  );
}
