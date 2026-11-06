"use client";

import { useEffect, useState } from "react";
import { Alert, Badge, Button, Card, Field, PageHeader, inputClass } from "@/components/ui";
import { API_URL, api, errorMessage } from "@/lib/api";
import type { AccountResponse } from "@/lib/types";

export default function SettingsPage() {
  const [data, setData] = useState<AccountResponse | null>(null);
  const [wabaId, setWabaId] = useState("");
  const [phoneNumberId, setPhoneNumberId] = useState("");
  const [token, setToken] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<AccountResponse>("/whatsapp-account")
      .then((d) => {
        setData(d);
        setWabaId(d.account?.waba_id ?? "");
        setPhoneNumberId(d.account?.phone_number_id ?? "");
      })
      .catch((err) => setError(errorMessage(err)));
  }, []);

  async function run(fn: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
      setNotice(success);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const updateAccount = (res: Pick<AccountResponse, "account">) => setData((d) => (d ? { ...d, account: res.account } : d));

  const save = (e: React.FormEvent) => {
    e.preventDefault();
    run(async () => {
      updateAccount(
        await api<AccountResponse>("/whatsapp-account", {
          method: "PUT",
          json: { waba_id: wabaId, phone_number_id: phoneNumberId, access_token: token || null },
        }),
      );
      setToken("");
    }, "Connected. Meta confirmed the number and token.");
  };

  const account = data?.account;
  const webhookUrl = `${API_URL}${data?.webhook_path ?? "/api/webhook"}`;

  return (
    <>
      <PageHeader title="Settings" subtitle="Connect the WhatsApp Business number that sends your messages" />
      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      {notice && <div className="mb-4"><Alert kind="success">{notice}</Alert></div>}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-4 font-semibold">WhatsApp number</h2>
          {account ? (
            <dl className="mb-6 grid grid-cols-2 gap-3 text-sm">
              <dt className="text-slate-500">Number</dt>
              <dd className="font-medium">{account.display_phone_number ?? "—"}</dd>
              <dt className="text-slate-500">Business name</dt>
              <dd>{account.verified_name ?? "—"}</dd>
              <dt className="text-slate-500">Quality rating</dt>
              <dd>{account.quality_rating ? <Badge value={account.quality_rating} /> : "—"}</dd>
              <dt className="text-slate-500">Messaging limit</dt>
              <dd>{account.messaging_limit?.replace("TIER_", "") ?? "—"} {account.messaging_limit && "contacts / 24h"}</dd>
              <dt className="text-slate-500">Webhooks</dt>
              <dd>{account.webhook_subscribed ? "Subscribed ✓" : "Not subscribed"}</dd>
            </dl>
          ) : (
            <p className="mb-6 text-sm text-slate-500">Not connected yet.</p>
          )}

          <form onSubmit={save} className="space-y-4">
            <Field label="WhatsApp Business Account ID" hint="Meta App Dashboard → WhatsApp → API Setup">
              <input className={inputClass} required value={wabaId} onChange={(e) => setWabaId(e.target.value)} />
            </Field>
            <Field label="Phone number ID" hint="Same page, under the 'From' phone number (not the phone number itself)">
              <input className={inputClass} required value={phoneNumberId} onChange={(e) => setPhoneNumberId(e.target.value)} />
            </Field>
            <Field
              label="Permanent access token"
              hint={account ? "Leave blank to keep the saved token" : "System User token from Meta Business Settings. Stored encrypted."}
            >
              <input className={inputClass} type="password" autoComplete="off" required={!account} value={token} onChange={(e) => setToken(e.target.value)} />
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={busy}>{account ? "Save changes" : "Connect"}</Button>
              {account && (
                <>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={busy}
                    onClick={() => run(async () => updateAccount(await api("/whatsapp-account/refresh", { method: "POST" })), "Refreshed from Meta.")}
                  >
                    Refresh
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={busy}
                    onClick={() =>
                      run(async () => updateAccount(await api("/whatsapp-account/subscribe-webhooks", { method: "POST" })), "Webhooks subscribed. Delivery updates will now arrive.")
                    }
                  >
                    Subscribe webhooks
                  </Button>
                </>
              )}
            </div>
          </form>
        </Card>

        <div className="space-y-6">
          <Card>
            <h2 className="mb-3 font-semibold">Webhook (delivery updates)</h2>
            <p className="mb-3 text-sm text-slate-600">
              In the Meta App Dashboard → WhatsApp → Configuration, set the callback URL and verify token, then subscribe to the{" "}
              <code>messages</code> and <code>message_template_status_update</code> fields.
            </p>
            <Field label="Callback URL" hint="Must be public HTTPS. For local testing, use an ngrok URL instead of localhost.">
              <input className={`${inputClass} font-mono`} readOnly value={webhookUrl} onFocus={(e) => e.target.select()} />
            </Field>
            <ul className="mt-3 space-y-1 text-sm">
              <li>{data?.verify_token_configured ? "✓" : "✗"} WEBHOOK_VERIFY_TOKEN is set in .env</li>
              <li>{data?.app_secret_configured ? "✓" : "✗"} META_APP_SECRET is set in .env (checks webhooks really come from Meta)</li>
            </ul>
          </Card>

          {account && (
            <Card>
              <h2 className="mb-2 font-semibold">Register number</h2>
              <p className="mb-3 text-sm text-slate-600">
                Only needed if sending fails with &quot;Phone number not registered&quot; (error 133010). Enter the 6-digit two-step
                verification PIN you want for this number.
              </p>
              <div className="flex gap-2">
                <input className={`${inputClass} max-w-40`} inputMode="numeric" maxLength={6} placeholder="123456" value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))} />
                <Button
                  variant="secondary"
                  disabled={busy || pin.length !== 6}
                  onClick={() => run(() => api("/whatsapp-account/register", { method: "POST", json: { pin } }), "Number registered with the Cloud API.")}
                >
                  Register
                </Button>
              </div>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
