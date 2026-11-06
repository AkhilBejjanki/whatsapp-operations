"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, getToken, setToken } from "@/lib/api";
import type { Me } from "@/lib/types";

const NAV = [
  { href: "/dashboard", label: "Campaigns" },
  { href: "/campaigns/new", label: "New campaign" },
  { href: "/templates", label: "Templates" },
  { href: "/settings", label: "Settings" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api<Me>("/auth/me").then(setMe).catch(() => router.replace("/login"));
  }, [router]);

  if (!me) return <div className="p-10 text-sm text-slate-500">Loading…</div>;

  const isActive = (href: string) =>
    href === "/dashboard"
      ? pathname === "/dashboard" || (pathname.startsWith("/campaigns/") && pathname !== "/campaigns/new")
      : pathname.startsWith(href);

  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-slate-200 bg-white md:min-h-screen md:w-60 md:border-r md:border-b-0">
        <div className="flex items-center gap-2 px-5 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-600 text-white">✉</div>
          <div className="min-w-0">
            <p className="text-sm font-semibold">Bulk Sender</p>
            <p className="truncate text-xs text-slate-500">{me.organization.name}</p>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm ${
                isActive(item.href) ? "bg-emerald-50 font-medium text-emerald-700" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {item.label}
            </Link>
          ))}
          <button
            onClick={() => {
              setToken(null);
              router.replace("/login");
            }}
            className="whitespace-nowrap rounded-lg px-3 py-2 text-left text-sm text-slate-500 hover:bg-slate-100 md:mt-4"
          >
            Log out
          </button>
        </nav>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-6 md:px-10 md:py-8">
        {me.mock_mode && (
          <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
            <b>Mock mode:</b> no real WhatsApp messages are sent. Numbers ending in 00 fail as &quot;not on
            WhatsApp&quot;; numbers ending in 1 are delivered but not read.
          </div>
        )}
        {children}
      </main>
    </div>
  );
}
