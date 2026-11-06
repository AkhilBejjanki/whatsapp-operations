"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Alert, Badge, Button, Card, PageHeader, formatDate, inputClass } from "@/components/ui";
import { api, downloadFile, errorMessage } from "@/lib/api";
import type { Campaign, MessagePage } from "@/lib/types";

const FILTERS: { label: string; value: string }[] = [
  { label: "All", value: "" },
  { label: "Waiting", value: "queued" },
  { label: "Sent", value: "accepted,sent" },
  { label: "Delivered", value: "delivered" },
  { label: "Read", value: "read" },
  { label: "Failed", value: "failed" },
  { label: "Invalid", value: "invalid" },
];

export default function CampaignPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [messages, setMessages] = useState<MessagePage | null>(null);
  const [filter, setFilter] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadCampaign = useCallback(async () => {
    try {
      setCampaign(await api<Campaign>(`/campaigns/${id}`));
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [id]);

  const loadMessages = useCallback(async () => {
    const params = new URLSearchParams({ page: String(page), page_size: "50" });
    if (filter) params.set("status", filter);
    if (search.trim()) params.set("q", search.trim());
    try {
      setMessages(await api<MessagePage>(`/campaigns/${id}/messages?${params}`));
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [id, page, filter, search]);

  useEffect(() => {
    loadCampaign();
  }, [loadCampaign]);

  useEffect(() => {
    const t = setTimeout(loadMessages, 250);
    return () => clearTimeout(t);
  }, [loadMessages]);

  // Live updates while sending, and for a minute after (delivered/read webhooks keep arriving).
  const live =
    campaign &&
    (campaign.status === "queued" ||
      campaign.status === "sending" ||
      (campaign.completed_at && Date.now() - new Date(campaign.completed_at).getTime() < 120_000));
  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => {
      loadCampaign();
      loadMessages();
    }, 3000);
    return () => clearInterval(timer);
  }, [live, loadCampaign, loadMessages]);

  async function action(path: string, confirmText?: string) {
    if (confirmText && !window.confirm(confirmText)) return;
    setBusy(true);
    setError("");
    try {
      if (path === "delete") {
        await api(`/campaigns/${id}`, { method: "DELETE" });
        router.push("/dashboard");
        return;
      }
      setCampaign(await api<Campaign>(`/campaigns/${id}/${path}`, { method: "POST" }));
      loadMessages();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (!campaign) return error ? <Alert>{error}</Alert> : <p className="text-sm text-slate-500">Loading…</p>;

  const c = campaign.counts;
  const delivered = c.delivered + c.read;
  const sentTotal = c.accepted + c.sent + delivered;
  const pct = (n: number) => (campaign.sendable ? Math.round((n / campaign.sendable) * 100) : 0);
  const progress = pct(campaign.processed);

  const stats = [
    { label: "Recipients", value: campaign.sendable, color: "text-slate-900" },
    { label: "Waiting", value: c.queued, color: "text-slate-600" },
    { label: "Sent", value: sentTotal, color: "text-blue-700", sub: `${pct(sentTotal)}%` },
    { label: "Delivered", value: delivered, color: "text-emerald-700", sub: `${pct(delivered)}%` },
    { label: "Read", value: c.read, color: "text-teal-700", sub: `${pct(c.read)}%` },
    { label: "Failed", value: c.failed, color: "text-red-600", sub: `${pct(c.failed)}%` },
    { label: "Invalid numbers", value: c.invalid, color: "text-orange-600" },
  ];

  return (
    <>
      <PageHeader
        title={campaign.name}
        subtitle={
          <>
            <Badge value={campaign.status} /> <span className="ml-2">Template: {campaign.template?.name}</span>
            <span className="ml-2">· Created {formatDate(campaign.created_at)}</span>
          </>
        }
        actions={
          <>
            {(campaign.status === "draft" || campaign.status === "paused") && c.queued > 0 && (
              <Button disabled={busy} onClick={() => action("start")}>
                {campaign.status === "draft" ? "Start sending" : "Resume"}
              </Button>
            )}
            {(campaign.status === "queued" || campaign.status === "sending") && (
              <Button variant="secondary" disabled={busy} onClick={() => action("pause")}>Pause</Button>
            )}
            {["completed", "paused", "cancelled"].includes(campaign.status) && c.failed > 0 && (
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => action("retry-failed", "Retry failed messages? (Numbers not on WhatsApp and opted-out users are skipped.)")}
              >
                Retry failed
              </Button>
            )}
            <Button variant="secondary" onClick={() => downloadFile(`/campaigns/${id}/export`, "report.csv")}>
              Export CSV
            </Button>
            {!["completed", "cancelled", "draft"].includes(campaign.status) && (
              <Button variant="danger" disabled={busy} onClick={() => action("cancel", "Cancel this campaign? Messages not yet sent will not be sent.")}>
                Cancel
              </Button>
            )}
            {["draft", "completed", "cancelled"].includes(campaign.status) && (
              <Button variant="danger" disabled={busy} onClick={() => action("delete", "Delete this campaign and its report?")}>
                Delete
              </Button>
            )}
          </>
        }
      />

      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      {campaign.last_error && (
        <div className="mb-4">
          <Alert kind="warning"><b>Sending paused:</b> {campaign.last_error}</Alert>
        </div>
      )}

      <Card className="mb-6">
        <div className="mb-2 flex justify-between text-sm">
          <span className="text-slate-600">
            {campaign.processed.toLocaleString()} of {campaign.sendable.toLocaleString()} processed
          </span>
          <span className="font-medium">{progress}%</span>
        </div>
        <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
          <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${progress}%` }} />
        </div>
        {campaign.duplicate_count > 0 && (
          <p className="mt-2 text-xs text-slate-500">{campaign.duplicate_count} duplicate numbers were removed from the file.</p>
        )}
      </Card>

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
        {stats.map((s) => (
          <Card key={s.label} className="!p-4">
            <p className="text-xs text-slate-500">{s.label}</p>
            <p className={`mt-1 text-2xl font-semibold tabular-nums ${s.color}`}>{s.value.toLocaleString()}</p>
            {s.sub && <p className="text-xs text-slate-400">{s.sub}</p>}
          </Card>
        ))}
      </div>

      {campaign.errors && campaign.errors.length > 0 && (
        <Card className="mb-6">
          <p className="mb-3 text-sm font-medium">Why messages didn&apos;t go through</p>
          <table className="w-full text-sm">
            <tbody className="divide-y divide-slate-100">
              {campaign.errors.map((e, i) => (
                <tr key={i}>
                  <td className="py-2 pr-4">{e.title ?? "Unknown"}</td>
                  <td className="py-2 pr-4 text-xs text-slate-400">{e.code ? `Meta code ${e.code}` : ""}</td>
                  <td className="py-2 text-right font-medium tabular-nums">{e.count.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <Card className="!p-0">
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 p-4">
          {FILTERS.map((f) => (
            <button
              key={f.label}
              onClick={() => {
                setFilter(f.value);
                setPage(1);
              }}
              className={`rounded-full px-3 py-1 text-sm ${filter === f.value ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
            >
              {f.label}
            </button>
          ))}
          <input
            className={`${inputClass} ml-auto max-w-xs`}
            placeholder="Search name or number"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2">Row</th>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2">Number</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Details</th>
                <th className="px-4 py-2">Last update</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {messages?.items.map((m) => (
                <tr key={m.id}>
                  <td className="px-4 py-2 text-slate-400">{m.row_index}</td>
                  <td className="px-4 py-2">{m.contact_name ?? "—"}</td>
                  <td className="px-4 py-2 font-mono text-xs">{m.phone ?? m.raw_phone}</td>
                  <td className="px-4 py-2"><Badge value={m.status} /></td>
                  <td className="max-w-sm px-4 py-2 text-xs text-slate-600" title={m.error_detail ?? ""}>
                    {m.error_title ?? ""}
                  </td>
                  <td className="px-4 py-2 text-xs text-slate-500">
                    {formatDate(m.read_at ?? m.delivered_at ?? m.sent_at ?? m.failed_at)}
                  </td>
                </tr>
              ))}
              {messages && messages.items.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">No messages match.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        {messages && messages.total > messages.page_size && (
          <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 text-sm">
            <span className="text-slate-500">
              {(messages.page - 1) * messages.page_size + 1}–{Math.min(messages.page * messages.page_size, messages.total)} of{" "}
              {messages.total.toLocaleString()}
            </span>
            <div className="flex gap-2">
              <Button variant="secondary" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <Button variant="secondary" disabled={page * messages.page_size >= messages.total} onClick={() => setPage(page + 1)}>
                Next
              </Button>
            </div>
          </div>
        )}
      </Card>
    </>
  );
}
