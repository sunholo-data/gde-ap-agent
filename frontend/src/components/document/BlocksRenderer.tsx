import type { ReactNode } from "react";

export interface BlockCell {
  text?: string;
}

export interface BlockRow {
  cells?: BlockCell[];
}

export interface Block {
  type: string;
  text?: string;
  level?: number;
  style?: string;
  change_type?: string;
  author?: string;
  date?: string;
  headers?: BlockCell[];
  rows?: BlockRow[];
  items?: string[];
  ordered?: boolean;
  description?: string;
  transcription?: string;
  mime?: string;
  kind?: string;
  children?: Block[];
}

const HEADING_STYLE_LEVEL: Record<string, number> = {
  Title: 1,
  "Heading 1": 1,
  Subtitle: 2,
  "Heading 2": 2,
  "Heading 3": 3,
  "Heading 4": 4,
  "Heading 5": 5,
  "Heading 6": 6,
};

function headingClass(level: number): string {
  // scroll-margin gives anchor-jump some breathing room beneath the doc toolbar.
  const base = "scroll-mt-12";
  switch (level) {
    case 1:
      return `${base} mt-6 mb-3 border-b border-border/60 pb-1.5 text-2xl font-bold tracking-tight text-foreground`;
    case 2:
      return `${base} mt-5 mb-2 text-xl font-semibold tracking-tight text-foreground`;
    case 3:
      return `${base} mt-4 mb-1.5 text-lg font-semibold text-foreground/90`;
    case 4:
      return `${base} mt-3 mb-1 text-base font-semibold text-foreground/85`;
    case 5:
      return `${base} mt-2 mb-0.5 text-sm font-semibold uppercase tracking-wide text-muted-foreground`;
    default:
      return `${base} mt-2 mb-0.5 text-xs font-medium uppercase tracking-wider text-muted-foreground`;
  }
}

function renderHeading(level: number, text: string): ReactNode {
  const cls = headingClass(level);
  switch (Math.min(Math.max(level, 1), 6)) {
    case 1: return <h1 className={cls}>{text}</h1>;
    case 2: return <h2 className={cls}>{text}</h2>;
    case 3: return <h3 className={cls}>{text}</h3>;
    case 4: return <h4 className={cls}>{text}</h4>;
    case 5: return <h5 className={cls}>{text}</h5>;
    default: return <h6 className={cls}>{text}</h6>;
  }
}

function renderText(b: Block): ReactNode {
  const text = b.text ?? "";
  const headingLevel = b.style ? HEADING_STYLE_LEVEL[b.style] : undefined;
  if (headingLevel) return renderHeading(headingLevel, text);

  if (b.style === "abstract") {
    return (
      <blockquote className="my-3 rounded-r border-l-4 border-primary/40 bg-primary/5 py-2 pl-4 pr-3 italic text-sm leading-relaxed text-muted-foreground">
        {text}
      </blockquote>
    );
  }
  if (b.style === "bibitem") {
    return <p className="my-1 pl-6 -indent-6 text-xs leading-snug text-muted-foreground">{text}</p>;
  }
  if (b.style === "equation" || b.style === "equation-display") {
    return (
      <pre className="my-3 overflow-x-auto rounded-md border border-border/60 bg-muted/40 px-3 py-2 font-mono text-xs leading-relaxed">
        {text}
      </pre>
    );
  }
  if (b.style === "code" || b.style === "code-block") {
    return (
      <pre className="my-3 overflow-x-auto rounded-md bg-zinc-900 px-3 py-2 font-mono text-xs leading-relaxed text-zinc-100">
        {text}
      </pre>
    );
  }
  if (b.style === "caption") {
    return <p className="my-1 text-center text-xs italic text-muted-foreground">{text}</p>;
  }
  if (!text.trim()) return null;
  return <p className="my-2 text-sm leading-relaxed text-foreground/90">{text}</p>;
}

function renderTable(b: Block): ReactNode {
  const headers = b.headers ?? [];
  const rows = b.rows ?? [];
  return (
    <div className="my-3 overflow-x-auto rounded-md border border-border/60 shadow-sm">
      <table className="w-full border-collapse text-xs">
        {headers.length > 0 && (
          <thead className="sticky top-0 z-10 bg-muted/80 backdrop-blur">
            <tr>
              {headers.map((h, i) => (
                <th
                  key={i}
                  className="border-b border-border/70 px-2.5 py-1.5 text-left text-[11px] font-semibold uppercase tracking-wide text-foreground/80"
                >
                  {h.text ?? ""}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {rows.map((row, ri) => (
            <tr
              key={ri}
              className={[
                "border-b border-border/30 last:border-b-0 transition-colors hover:bg-accent/40",
                ri % 2 === 1 ? "bg-muted/20" : "",
              ].join(" ")}
            >
              {(row.cells ?? []).map((c, ci) => (
                <td key={ci} className="px-2.5 py-1.5 align-top text-foreground/90">
                  {c.text ?? ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderList(b: Block): ReactNode {
  const items = b.items ?? [];
  const cls = "my-2 pl-6 text-sm space-y-1 text-foreground/90 leading-relaxed";
  if (b.ordered) {
    return (
      <ol className={`${cls} list-decimal marker:text-muted-foreground`}>
        {items.map((it, i) => <li key={i}>{it}</li>)}
      </ol>
    );
  }
  return (
    <ul className={`${cls} list-disc marker:text-primary/60`}>
      {items.map((it, i) => <li key={i}>{it}</li>)}
    </ul>
  );
}

function renderChange(b: Block): ReactNode {
  const isDelete = b.change_type === "deletion" || b.change_type === "delete";
  const wrapperCls = isDelete
    ? "bg-rose-50 text-rose-700 line-through"
    : "bg-emerald-50 text-emerald-700";
  const label = isDelete ? "deleted" : "inserted";
  return (
    <span className={`inline-flex items-baseline gap-1.5 rounded px-1.5 py-0.5 text-sm ${wrapperCls}`}>
      <span>{b.text}</span>
      <span className="rounded bg-white/70 px-1 py-px text-[9px] font-medium uppercase tracking-wide opacity-80">
        {label}
        {b.author && ` · ${b.author}`}
      </span>
    </span>
  );
}

function renderImage(b: Block): ReactNode {
  const label = b.description || b.transcription || "embedded image";
  return (
    <figure className="my-3 rounded-md border border-dashed border-border/60 bg-muted/30 px-3 py-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <svg className="h-4 w-4 shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
          <rect x="2" y="3" width="12" height="10" rx="1" />
          <circle cx="6" cy="7" r="1.2" />
          <path d="M2.5 12l3.5-3 3 2.5 2-1.5 2.5 2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="italic">{label}</span>
        {b.mime && <span className="rounded bg-background px-1 py-px text-[10px] font-mono">{b.mime}</span>}
      </div>
    </figure>
  );
}

function renderBlock(b: Block, key: number): ReactNode {
  switch (b.type) {
    case "heading":
      return <div key={key}>{renderHeading(b.level ?? 1, b.text ?? "")}</div>;
    case "text":
      return <div key={key}>{renderText(b)}</div>;
    case "table":
      return <div key={key}>{renderTable(b)}</div>;
    case "list":
      return <div key={key}>{renderList(b)}</div>;
    case "change":
      return <div key={key} className="my-1">{renderChange(b)}</div>;
    case "image":
      return <div key={key}>{renderImage(b)}</div>;
    case "section":
      return (
        <section key={key} className="my-3 first:mt-0">
          {b.kind && (
            <div className="mb-1 inline-block rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              {b.kind}
            </div>
          )}
          {(b.children ?? []).map((c, i) => renderBlock(c, i))}
        </section>
      );
    default:
      if (b.children?.length) {
        return <div key={key}>{b.children.map((c, i) => renderBlock(c, i))}</div>;
      }
      if (b.text) return <p key={key} className="my-2 text-sm leading-relaxed text-foreground/90">{b.text}</p>;
      return null;
  }
}

interface BlocksRendererProps {
  blocks: Block[];
}

export function BlocksRenderer({ blocks }: BlocksRendererProps) {
  return (
    <div className="mx-auto max-w-3xl space-y-1 px-1 py-2 text-foreground">
      {blocks.map((b, i) => renderBlock(b, i))}
    </div>
  );
}
