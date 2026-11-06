"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Alert, Badge, Card, PageHeader, formatDate } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { Campaign } from "@/lib/types";

export default function DashboardPage() {
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const data = await api<Campaign[]>("/campaigns");
        setCampaigns(data);
        if (data.some((c) => c.status === "queued" || c.status === "sending")) timer = setTimeout(load, 4000);
      } catch (err) {
        setError(errorMessage(err));
      }
    };
    load();
    return () => clearTimeout(timer);
  }, []);

  return (
    <>
      <PageHeader
        title="Campaigns"
        subtitle="Every bulk send, with live delivery numbers"
        actions={
          <Link href="/campaigns/new" className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700">
            New campaign
          </Link>
        }
      />
      {error && <Alert>{error}</Alert>}
      {campaigns && campaigns.length === 0 && (
        <Card className="py-12 text-center">
          <p className="font-medium">No campaigns yet</p>
          <p className="mt-1 text-sm text-slate-500">
            Connect your number in <Link className="text-emerald-700 underline" href="/settings">Settings</Link>, then create
            your first campaign.
          </p>
        </Card>
      )}
      {campaigns && campaigns.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Campaign</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Recipients</th>
                <th className="px-4 py-3 text-right">Delivered</th>
                <th className="px-4 py-3 text-right">Read</th>
                <th className="px-4 py-3 text-right">Failed</th>
                <th className="px-4 py-3 text-right">Invalid</th>
                <th className="px-4 py-3">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {campaigns.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link href={`/campaigns/${c.id}`} className="font-medium text-slate-900 hover:text-emerald-700">
                      {c.name}
                    </Link>
                    <p className="text-xs text-slate-500">{c.template?.name}</p>
                  </td>
                  <td className="px-4 py-3"><Badge value={c.status} /></td>
                  <td className="px-4 py-3 text-right tabular-nums">{c.sendable.toLocaleString()}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{(c.counts.delivered + c.counts.read).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{c.counts.read.toLocaleString()}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-red-600">{c.counts.failed.toLocaleString()}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-orange-600">{c.counts.invalid.toLocaleString()}</td>
                  <td className="px-4 py-3 text-slate-500">{formatDate(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
