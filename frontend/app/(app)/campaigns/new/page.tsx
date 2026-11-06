"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { TemplatePreview } from "@/components/TemplatePreview";
import { Alert, Button, Card, Field, PageHeader, inputClass } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { Campaign, Mapping, MessagePage, Template, UploadResult } from "@/lib/types";

const COUNTRIES: [string, string][] = [
  ["IN", "India (+91)"], ["AE", "UAE (+971)"], ["SA", "Saudi Arabia (+966)"], ["US", "USA (+1)"],
  ["GB", "UK (+44)"], ["SG", "Singapore (+65)"], ["MY", "Malaysia (+60)"], ["ID", "Indonesia (+62)"],
  ["BR", "Brazil (+55)"], ["MX", "Mexico (+52)"], ["NG", "Nigeria (+234)"], ["KE", "Kenya (+254)"],
  ["ZA", "South Africa (+27)"], ["AU", "Australia (+61)"], ["CA", "Canada (+1)"], ["PK", "Pakistan (+92)"],
  ["BD", "Bangladesh (+880)"], ["NP", "Nepal (+977)"], ["LK", "Sri Lanka (+94)"],
];

type Step = "upload" | "setup" | "review";

export default function NewCampaignPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("upload");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const [upload, setUpload] = useState<UploadResult | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [name, setName] = useState("");
  const [templateId, setTemplateId] = useState<number | "">("");
  const [phoneColumn, setPhoneColumn] = useState("");
  const [nameColumn, setNameColumn] = useState("");
  const [country, setCountry] = useState("IN");
  const [mapping, setMapping] = useState<Record<string, Mapping>>({});
  const [mediaUrl, setMediaUrl] = useState("");

  const [draft, setDraft] = useState<Campaign | null>(null);
  const [invalidRows, setInvalidRows] = useState<MessagePage | null>(null);

  useEffect(() => {
    api<Template[]>("/templates").then(setTemplates).catch(() => setTemplates([]));
  }, []);

  const approved = templates.filter((t) => t.status === "APPROVED");
  const template = approved.find((t) => t.id === templateId);

  // Pre-fill variable mapping when a template is chosen.
  useEffect(() => {
    if (!template) return;
    setMapping((prev) => {
      const next: Record<string, Mapping> = {};
      template.variables.forEach((v, i) => {
        next[v.key] = prev[v.key] ?? {
          type: "column",
          value: i === 0 && upload?.suggested.name ? upload.suggested.name : "",
        };
      });
      return next;
    });
  }, [template, upload]);

  const previewValues = useMemo(() => {
    const row = upload?.sample_rows[0] ?? {};
    const out: Record<string, string> = {};
    for (const [key, m] of Object.entries(mapping)) out[key] = m.type === "static" ? m.value : row[m.value] ?? "";
    return out;
  }, [mapping, upload]);

  async function handleFile(file: File) {
    setError("");
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await api<UploadResult>("/uploads", { method: "POST", body: form });
      setUpload(result);
      setPhoneColumn(result.suggested.phone ?? result.columns[0]);
      setNameColumn(result.suggested.name ?? "");
      if (!name) setName(file.name.replace(/\.[^.]+$/, ""));
      setStep("setup");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function createDraft() {
    if (!upload || !template) return;
    setError("");
    setBusy(true);
    try {
      const campaign = await api<Campaign>("/campaigns", {
        method: "POST",
        json: {
          name,
          upload_id: upload.id,
          template_id: template.id,
          phone_column: phoneColumn,
          name_column: nameColumn || null,
          default_country: country,
          variable_mapping: mapping,
          header_media_url: mediaUrl || null,
        },
      });
      setDraft(campaign);
      setInvalidRows(
        campaign.counts.invalid > 0
          ? await api<MessagePage>(`/campaigns/${campaign.id}/messages?status=invalid&page_size=20`)
          : null,
      );
      setStep("review");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    if (!draft) return;
    setBusy(true);
    setError("");
    try {
      await api(`/campaigns/${draft.id}/start`, { method: "POST" });
      router.push(`/campaigns/${draft.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  async function discardDraft() {
    if (draft) await api(`/campaigns/${draft.id}`, { method: "DELETE" }).catch(() => undefined);
    setDraft(null);
    setStep("setup");
  }

  return (
    <>
      <PageHeader title="New campaign" subtitle="Upload contacts, pick a template, and send" />
      <ol className="mb-6 flex flex-wrap gap-2 text-sm">
        {(["upload", "setup", "review"] as Step[]).map((s, i) => (
          <li
            key={s}
            className={`rounded-full px-3 py-1 ${step === s ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-600"}`}
          >
            {i + 1}. {s === "upload" ? "Upload contacts" : s === "setup" ? "Choose template" : "Review & send"}
          </li>
        ))}
      </ol>
      {error && <div className="mb-4"><Alert>{error}</Alert></div>}

      {step === "upload" && (
        <Card>
          <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 px-6 py-14 text-center hover:border-emerald-400 hover:bg-emerald-50/40">
            <span className="text-3xl">📄</span>
            <span className="mt-2 font-medium">{busy ? "Reading file…" : "Choose a CSV or Excel (.xlsx) file"}</span>
            <span className="mt-1 text-sm text-slate-500">
              First row must be column names, e.g. <code>name, phone, order_id</code>
            </span>
            <input
              type="file"
              accept=".csv,.xlsx,.xlsm,.txt"
              className="hidden"
              disabled={busy}
              onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
            />
          </label>
        </Card>
      )}

      {step === "setup" && upload && (
        <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
          <div className="space-y-6">
            <Card>
              <div className="mb-4 flex items-center justify-between">
                <p className="text-sm">
                  <b>{upload.filename}</b> · {upload.row_count.toLocaleString()} rows
                </p>
                <Button variant="ghost" onClick={() => setStep("upload")}>Change file</Button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr>{upload.columns.map((c) => <th key={c} className="border-b px-2 py-1 text-left font-medium text-slate-600">{c}</th>)}</tr>
                  </thead>
                  <tbody>
                    {upload.sample_rows.map((r, i) => (
                      <tr key={i}>{upload.columns.map((c) => <td key={c} className="border-b border-slate-100 px-2 py-1">{r[c]}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card className="space-y-4">
              <Field label="Campaign name">
                <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
              <div className="grid gap-4 sm:grid-cols-3">
                <Field label="Phone number column">
                  <select className={inputClass} value={phoneColumn} onChange={(e) => setPhoneColumn(e.target.value)}>
                    {upload.columns.map((c) => <option key={c}>{c}</option>)}
                  </select>
                </Field>
                <Field label="Name column (optional)">
                  <select className={inputClass} value={nameColumn} onChange={(e) => setNameColumn(e.target.value)}>
                    <option value="">—</option>
                    {upload.columns.map((c) => <option key={c}>{c}</option>)}
                  </select>
                </Field>
                <Field label="Default country" hint="Used when a number has no country code">
                  <select className={inputClass} value={country} onChange={(e) => setCountry(e.target.value)}>
                    {COUNTRIES.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
                  </select>
                </Field>
              </div>
              <Field
                label="Template"
                hint={
                  approved.length === 0 ? (
                    <>No approved templates. Create or sync one on the <Link className="underline" href="/templates">Templates</Link> page.</>
                  ) : "Only templates approved by Meta can be sent"
                }
              >
                <select
                  className={inputClass}
                  value={templateId}
                  onChange={(e) => setTemplateId(e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">Select a template…</option>
                  {approved.map((t) => (
                    <option key={t.id} value={t.id}>{t.name} ({t.language}, {t.category?.toLowerCase()})</option>
                  ))}
                </select>
              </Field>

              {template && template.header_media && (
                <Field label={`Header ${template.header_media.toLowerCase()} link`} hint="A public https:// link Meta can download">
                  <input className={inputClass} value={mediaUrl} onChange={(e) => setMediaUrl(e.target.value)} placeholder="https://…" />
                </Field>
              )}

              {template && template.variables.length > 0 && (
                <div className="space-y-3">
                  <p className="text-sm font-medium text-slate-700">Fill in the template variables</p>
                  {template.variables.map((v) => {
                    const m = mapping[v.key] ?? { type: "column", value: "" };
                    const set = (next: Mapping) => setMapping((prev) => ({ ...prev, [v.key]: next }));
                    return (
                      <div key={v.key} className="grid items-center gap-2 sm:grid-cols-[160px_130px_1fr]">
                        <span className="text-sm text-slate-600">{v.label}</span>
                        <select className={inputClass} value={m.type} onChange={(e) => set({ type: e.target.value as Mapping["type"], value: "" })}>
                          <option value="column">From column</option>
                          <option value="static">Same text for all</option>
                        </select>
                        {m.type === "column" ? (
                          <select className={inputClass} value={m.value} onChange={(e) => set({ ...m, value: e.target.value })}>
                            <option value="">Choose column…</option>
                            {upload.columns.map((c) => <option key={c}>{c}</option>)}
                          </select>
                        ) : (
                          <input className={inputClass} value={m.value} onChange={(e) => set({ ...m, value: e.target.value })} />
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="flex justify-end">
                <Button onClick={createDraft} disabled={busy || !template || !name.trim()}>
                  {busy ? "Checking numbers…" : "Check numbers & continue"}
                </Button>
              </div>
            </Card>
          </div>

          <div className="lg:sticky lg:top-6 lg:self-start">
            <p className="mb-2 text-sm font-medium text-slate-700">Preview (first row)</p>
            {template ? (
              <TemplatePreview components={template.components} values={previewValues} />
            ) : (
              <Card className="text-sm text-slate-500">Choose a template to see a preview.</Card>
            )}
          </div>
        </div>
      )}

      {step === "review" && draft && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <Card>
              <p className="text-sm text-slate-500">Ready to send</p>
              <p className="mt-1 text-3xl font-semibold text-emerald-700">{draft.counts.queued.toLocaleString()}</p>
            </Card>
            <Card>
              <p className="text-sm text-slate-500">Invalid (won&apos;t be sent)</p>
              <p className="mt-1 text-3xl font-semibold text-orange-600">{draft.counts.invalid.toLocaleString()}</p>
            </Card>
            <Card>
              <p className="text-sm text-slate-500">Duplicates removed</p>
              <p className="mt-1 text-3xl font-semibold text-slate-600">{draft.duplicate_count.toLocaleString()}</p>
            </Card>
          </div>

          {invalidRows && invalidRows.items.length > 0 && (
            <Card>
              <p className="mb-3 text-sm font-medium">Invalid rows {invalidRows.total > 20 && `(first 20 of ${invalidRows.total})`}</p>
              <table className="w-full text-sm">
                <tbody className="divide-y divide-slate-100">
                  {invalidRows.items.map((m) => (
                    <tr key={m.id}>
                      <td className="py-1.5 pr-3 text-slate-400">Row {m.row_index}</td>
                      <td className="py-1.5 pr-3">{m.contact_name}</td>
                      <td className="py-1.5 pr-3 font-mono">{m.raw_phone || "(empty)"}</td>
                      <td className="py-1.5 text-orange-700">{m.error_title}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}

          <Alert kind="info">
            Meta charges the business for each delivered template message ({draft.template?.category?.toLowerCase()} rate).
            Make sure everyone on this list has agreed to receive WhatsApp messages from you.
          </Alert>

          <div className="flex flex-wrap justify-between gap-2">
            <Button variant="secondary" onClick={discardDraft} disabled={busy}>Back</Button>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => router.push(`/campaigns/${draft.id}`)} disabled={busy}>
                Save as draft
              </Button>
              <Button onClick={send} disabled={busy || draft.counts.queued === 0}>
                Send to {draft.counts.queued.toLocaleString()} contacts
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
