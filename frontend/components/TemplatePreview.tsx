import type { TemplateComponent } from "@/lib/types";

const VAR_RE = /\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g;

/** values: {"body:1": "Ravi", "header:1": "..."}. Missing values show as {{n}}. */
export function TemplatePreview({
  components,
  values = {},
}: {
  components: TemplateComponent[];
  values?: Record<string, string>;
}) {
  const fill = (text: string, part: string) =>
    text.replace(VAR_RE, (match, name) => values[`${part}:${name}`] || match);

  const header = components.find((c) => c.type === "HEADER");
  const body = components.find((c) => c.type === "BODY");
  const footer = components.find((c) => c.type === "FOOTER");
  const buttons = components.find((c) => c.type === "BUTTONS")?.buttons ?? [];

  return (
    <div className="rounded-xl bg-[#e5ddd5] p-4">
      <div className="max-w-sm rounded-lg rounded-tl-none bg-white p-3 text-sm shadow">
        {header?.format === "TEXT" && header.text && (
          <p className="mb-1 font-semibold">{fill(header.text, "header")}</p>
        )}
        {header && header.format && header.format !== "TEXT" && (
          <div className="mb-2 flex h-28 items-center justify-center rounded bg-slate-200 text-xs text-slate-500">
            {header.format.toLowerCase()} header
          </div>
        )}
        {body?.text && <p className="whitespace-pre-wrap text-slate-800">{fill(body.text, "body")}</p>}
        {footer?.text && <p className="mt-2 text-xs text-slate-500">{footer.text}</p>}
      </div>
      {buttons.length > 0 && (
        <div className="mt-1 max-w-sm space-y-1">
          {buttons.map((b, i) => (
            <div key={i} className="rounded-lg bg-white py-2 text-center text-sm font-medium text-sky-600 shadow">
              {b.text}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
