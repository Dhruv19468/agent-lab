import { CircleCheck, TriangleAlert } from "lucide-react";
import { createContext, useCallback, useContext, useState } from "react";
import type { ReactNode } from "react";

type ToastTone = "success" | "error";
type Notify = (tone: ToastTone, text: string) => void;

interface ToastItem {
  id: number;
  tone: ToastTone;
  text: string;
}

const ToastContext = createContext<Notify>(() => undefined);

let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const notify = useCallback<Notify>((tone, text) => {
    const id = nextId++;
    setItems((current) => [...current, { id, tone, text }]);
    window.setTimeout(() => setItems((current) => current.filter((item) => item.id !== id)), tone === "error" ? 7000 : 4000);
  }, []);

  return (
    <ToastContext.Provider value={notify}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-[min(92vw,380px)] flex-col gap-2">
        {items.map((item) => (
          <div
            key={item.id}
            className={
              "stack-in pointer-events-auto flex gap-3 rounded-lg border px-4 py-3 text-sm shadow-lg shadow-ink-950/10 " +
              (item.tone === "success" ? "border-ink-800 bg-ink-900 text-white" : "border-bad-600/30 bg-bad-50 text-bad-800")
            }
          >
            {item.tone === "success" ? (
              <CircleCheck className="mt-0.5 size-4 shrink-0 text-signal-400" aria-hidden />
            ) : (
              <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
            )}
            <span>{item.text}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): Notify {
  return useContext(ToastContext);
}
