"use client";

import { useEffect, useMemo, useState } from "react";
import { TemplatePreview } from "@/components/TemplatePreview";
import { Alert, Badge, Button, Card, Field, PageHeader, inputClass } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { Template, TemplateComponent } from "@/lib/types";

type ButtonDraft = { type: "QUICK_REPLY" | "URL" | "PHONE_NUMBER"; text: string; url: string; phone_number: string };

const EMPTY_FORM = {
  name: "",
  language: "en",
  category: "UTILITY" as "UTILITY" | "MARKETING",
  header_text: "",
  header_example: "",
  body: "",
  body_examples: [] as string[],
  footer: "",
  buttons: [] as ButtonDraft[],
};

const LANGUAGES = [
  ["en", "English"], ["en_US", "English (US)"], ["en_GB", "English (UK)"], ["hi", "Hindi"], ["te", "Telugu"],
  ["ta", "Tamil"], ["kn", "Kannada"], ["ml", "Malayalam"], ["mr", "Marathi"], ["bn", "Bengali"], ["gu", "Gujarati"],
  ["pa", "Punjabi"], ["ur", "Urdu"], ["ar", "Arabic"], ["es", "Spanish"], ["pt_BR", "Portuguese (BR)"], ["id", "Indonesian"],
];

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<Template[] | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);

  useEffect(() => {
    api<Template[]>("/templates").then(setTemplates).catch((err) => setError(errorMessage(err)));
  }, []);

  async function sync() {
    setBusy(true);
    setError("");
    try {
      setTemplates(await api<Template[]>("/templates/sync", { method: "POST" }));
      setNotice("Templates updated from Meta.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(t: Template) {
    if (!window.confirm(`Delete template "${t.name}" from Meta? This removes all its languages.`)) return;
    setBusy(true);
    try {
      await api(`/templates/${t.id}`, { method: "DELETE" });
      setTemplates((prev) => prev?.filter((x) => x.name !== t.name) ?? null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const bodyVarCount = useMemo(() => new Set(form.body.match(/\{\{\s*\d+\s*\}\}/g) ?? []).size, [form.body]);
  const headerHasVar = /\{\{\s*1\s*\}\}/.test(form.header_text);

  const previewComponents: TemplateComponent[] = useMemo(() => {
    const comps: TemplateComponent[] = [];
    if (form.header_text) comps.push({ type: "HEADER", format: "TEXT", text: form.header_text });
    comps.push({ type: "BODY", text: form.body || "Your message…" });
    if (form.footer) comps.push({ type: "FOOTER", text: form.footer });
    if (form.buttons.length) comps.push({ type: "BUTTONS", buttons: form.buttons });
    return comps;
  }, [form]);

  const previewValues = useMemo(() => {
    const v: Record<string, string> = {};
    form.body_examples.forEach((ex, i) => ex && (v[`body:${i + 1}`] = ex));
    if (form.header_example) v["header:1"] = form.header_example;
    return v;
  }, [form]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const created = await api<Template>("/templates", {
        method: "POST",
        json: {
          ...form,
          header_text: form.header_text || null,
          header_example: form.header_example || null,
          footer: form.footer || null,
          body_examples: form.body_examples.slice(0, bodyVarCount),
          buttons: form.buttons.map((b) => ({
            type: b.type,
            text: b.text,
            url: b.type === "URL" ? b.url : null,
            phone_number: b.type === "PHONE_NUMBER" ? b.phone_number : null,
          })),
        },
      });
      setTemplates((prev) => [...(prev ?? []).filter((t) => t.id !== created.id), created].sort((a, b) => a.name.localeCompare(b.name)));
      setNotice(`Template "${created.name}" submitted. Status: ${created.status}. Meta usually reviews within minutes to a few hours.`);
      setForm(EMPTY_FORM);
      setShowForm(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const setButton = (i: number, patch: Partial<ButtonDraft>) =>
    setForm((f) => ({ ...f, buttons: f.buttons.map((b, j) => (j === i ? { ...b, ...patch } : b)) }));

  return (
    <>
      <PageHeader
        title="Templates"
        subtitle="Messages must use a template approved by Meta"
        actions={
          <>
            <Button variant="secondary" onClick={sync} disabled={busy}>Sync from Meta</Button>
            <Button onClick={() => setShowForm((s) => !s)}>{showForm ? "Close" : "New template"}</Button>
          </>
        }
      />
      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      {notice && <div className="mb-4"><Alert kind="success">{notice}</Alert></div>}

      {showForm && (
        <Card className="mb-6">
          <form onSubmit={create} className="grid gap-6 lg:grid-cols-[1fr_340px]">
            <div className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-3">
                <Field label="Name" hint="lowercase letters, numbers and _">
                  <input
                    className={inputClass}
                    required
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })}
                  />
                </Field>
                <Field label="Category" hint="Marketing costs more than utility">
                  <select className={inputClass} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value as "UTILITY" | "MARKETING" })}>
                    <option value="UTILITY">Utility (orders, reminders, updates)</option>
                    <option value="MARKETING">Marketing (offers, promotions)</option>
                  </select>
                </Field>
                <Field label="Language">
                  <select className={inputClass} value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })}>
                    {LANGUAGES.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
                  </select>
                </Field>
              </div>
              <Field label="Header (optional)" hint="Up to 60 characters. May contain one variable {{1}}.">
                <input className={inputClass} maxLength={60} value={form.header_text} onChange={(e) => setForm({ ...form, header_text: e.target.value })} />
              </Field>
              {headerHasVar && (
                <Field label="Example for header {{1}}">
                  <input className={inputClass} value={form.header_example} onChange={(e) => setForm({ ...form, header_example: e.target.value })} />
                </Field>
              )}
              <Field label="Body" hint="Use {{1}}, {{2}}… for values that change per contact, e.g. Hi {{1}}, your order {{2}} is ready.">
                <textarea className={`${inputClass} min-h-28`} required maxLength={1024} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />
              </Field>
              {bodyVarCount > 0 && (
                <div className="grid gap-3 sm:grid-cols-2">
                  {Array.from({ length: bodyVarCount }, (_, i) => (
                    <Field key={i} label={`Example for {{${i + 1}}}`} hint={i === 0 ? "Meta needs a sample value to review the template" : undefined}>
                      <input
                        className={inputClass}
                        required
                        value={form.body_examples[i] ?? ""}
                        onChange={(e) => {
                          const examples = [...form.body_examples];
                          examples[i] = e.target.value;
                          setForm({ ...form, body_examples: examples });
                        }}
                      />
                    </Field>
                  ))}
                </div>
              )}
              <Field label="Footer (optional)">
                <input className={inputClass} maxLength={60} value={form.footer} onChange={(e) => setForm({ ...form, footer: e.target.value })} />
              </Field>

              <div className="space-y-2">
                <p className="text-sm font-medium text-slate-700">Buttons (optional)</p>
                {form.buttons.map((b, i) => (
                  <div key={i} className="grid gap-2 sm:grid-cols-[150px_1fr_1fr_auto]">
                    <select className={inputClass} value={b.type} onChange={(e) => setButton(i, { type: e.target.value as ButtonDraft["type"] })}>
                      <option value="QUICK_REPLY">Quick reply</option>
                      <option value="URL">Website link</option>
                      <option value="PHONE_NUMBER">Call number</option>
                    </select>
                    <input className={inputClass} placeholder="Button text" maxLength={25} required value={b.text} onChange={(e) => setButton(i, { text: e.target.value })} />
                    {b.type === "URL" && (
                      <input className={inputClass} placeholder="https://… (may end with {{1}})" required value={b.url} onChange={(e) => setButton(i, { url: e.target.value })} />
                    )}
                    {b.type === "PHONE_NUMBER" && (
                      <input className={inputClass} placeholder="+919876543210" required value={b.phone_number} onChange={(e) => setButton(i, { phone_number: e.target.value })} />
                    )}
                    {b.type === "QUICK_REPLY" && <span />}
                    <Button type="button" variant="ghost" onClick={() => setForm({ ...form, buttons: form.buttons.filter((_, j) => j !== i) })}>✕</Button>
                  </div>
                ))}
                {form.buttons.length < 3 && (
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setForm({ ...form, buttons: [...form.buttons, { type: "QUICK_REPLY", text: "", url: "", phone_number: "" }] })}
                  >
                    + Add button
                  </Button>
                )}
              </div>
              <Button type="submit" disabled={busy}>{busy ? "Submitting…" : "Submit to Meta for approval"}</Button>
            </div>
            <div>
              <p className="mb-2 text-sm font-medium text-slate-700">Preview</p>
              <TemplatePreview components={previewComponents} values={previewValues} />
            </div>
          </form>
        </Card>
      )}

      {templates && templates.length === 0 && !showForm && (
        <Card className="py-10 text-center text-sm text-slate-500">
          No templates yet. Click <b>Sync from Meta</b> to load existing ones, or create a new one.
        </Card>
      )}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {templates?.map((t) => (
          <Card key={t.id} className="flex flex-col">
            <div className="mb-3 flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate font-medium">{t.name}</p>
                <p className="text-xs text-slate-500">{t.language} · {t.category?.toLowerCase()}</p>
              </div>
              <Badge value={t.status} />
            </div>
            <div className="flex-1">
              <TemplatePreview components={t.components} />
            </div>
            {t.rejected_reason && t.rejected_reason !== "NONE" && (
              <p className="mt-2 text-xs text-red-600">Rejected: {t.rejected_reason}</p>
            )}
            <div className="mt-3 flex justify-end">
              <Button variant="ghost" className="!px-2 !py-1 text-xs text-red-600" onClick={() => remove(t)} disabled={busy}>
                Delete
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
