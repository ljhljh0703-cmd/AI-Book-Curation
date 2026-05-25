import type { ReactNode } from "react";

type PersonalizationHintProps = {
  title: string;
  description: ReactNode;
  items?: readonly string[];
  note?: string;
  className?: string;
};

export default function PersonalizationHint({
  title,
  description,
  items = [],
  note,
  className = "",
}: PersonalizationHintProps) {
  return (
    <aside
      className={[
        "rounded-2xl border border-primary/20 bg-primary/5 p-4 text-left shadow-sm",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <p className="text-sm font-semibold text-primary">{title}</p>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>

      {items.length > 0 && (
        <ul className="mt-3 space-y-2 text-sm leading-6 text-muted-foreground">
          {items.map((item) => (
            <li key={item} className="flex gap-2">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary/70" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}

      {note && (
        <p className="mt-3 rounded-xl bg-background/80 px-3 py-2 text-xs leading-5 text-muted-foreground">
          {note}
        </p>
      )}
    </aside>
  );
}
