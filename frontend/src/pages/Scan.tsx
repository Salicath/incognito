import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAsyncTask } from "../hooks/useAsyncTask";
import { Search, ExternalLink, AlertTriangle, CheckCircle, Loader2, Mail, ShieldAlert, RefreshCw } from "lucide-react";

interface ScanHit {
  broker_domain: string;
  broker_name: string;
  snippet: string;
  url: string;
}

interface AccountHit {
  service: string;
  url: string;
}

interface BreachHit {
  name: string;
  title: string;
  domain: string;
  breach_date: string;
  pwn_count: number;
  data_classes: string[];
}

interface ScanResults {
  has_results: boolean;
  checked: number;
  hits: ScanHit[];
}

interface AccountResults {
  has_results: boolean;
  email: string;
  checked: number;
  hits: AccountHit[];
  errors: string[];
}

interface BreachResults {
  has_results: boolean;
  email: string;
  total_breaches: number;
  breaches: BreachHit[];
  error: string | null;
}

export default function Scan() {
  const [profileEmails, setProfileEmails] = useState<string[]>([]);

  const scan = useAsyncTask<ScanResults>({
    startFn: () => api.startScan(),
    statusFn: api.getScanStatus,
    resultsFn: api.getScanResults,
  });

  const [accountEmailInput, setAccountEmailInput] = useState("");
  const account = useAsyncTask<AccountResults>({
    startFn: (email?: unknown) => api.startAccountScan(email as string | undefined),
    statusFn: api.getAccountStatus,
    resultsFn: api.getAccountResults,
  });

  const [breachEmailInput, setBreachEmailInput] = useState("");
  const [hibpConfigured, setHibpConfigured] = useState<boolean | null>(null);
  const breach = useAsyncTask<BreachResults>({
    startFn: (email?: unknown) => api.startBreachCheck(email as string | undefined),
    statusFn: api.getBreachStatus,
    resultsFn: api.getBreachResults,
  });

  // Re-scan monitoring
  interface RescanAlert {
    broker_domain: string;
    broker_name: string;
    snippet: string;
    url: string;
    previous_removal_date?: string | null;
  }
  const [rescanReappeared, setRescanReappeared] = useState<RescanAlert[]>([]);
  const [rescanNewExposures, setRescanNew] = useState<RescanAlert[]>([]);
  const [rescanLoaded, setRescanLoaded] = useState(false);

  useEffect(() => {
    api.getHibpStatus().then((s) => setHibpConfigured(s.configured)).catch(() => setHibpConfigured(false));
    api.getProfile().then((p) => {
      const emails = (p as Record<string, unknown>).emails as string[] | undefined;
      if (emails && emails.length > 0) setProfileEmails(emails);
    }).catch(() => {});
    api.getRescanReport().then((r) => {
      if (r.has_results) {
        setRescanReappeared(r.reappeared);
        setRescanNew(r.new_exposures);
      }
      setRescanLoaded(true);
    }).catch(() => setRescanLoaded(true));
  }, [scan.hasResults]);

  async function handleCreateRequest(brokerDomain: string, type: string) {
    try {
      const brokers = await api.getBrokers();
      const broker = brokers.find(
        (b) => (b as Record<string, unknown>).domain === brokerDomain
      ) as Record<string, unknown> | undefined;

      if (broker) {
        await api.createRequest(broker.id as string, type);
        alert(`${type} request created for ${broker.name}`);
      } else {
        alert(`Broker for ${brokerDomain} not in registry.`);
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to create request");
    }
  }

  const scanHits = (scan.results as ScanResults | null)?.hits ?? [];
  const scanChecked = (scan.results as ScanResults | null)?.checked ?? 0;
  const scanPct = scan.total > 0 ? Math.round((scan.progress / scan.total) * 100) : 0;

  const accountHits = (account.results as AccountResults | null)?.hits ?? [];
  const accountChecked = (account.results as AccountResults | null)?.checked ?? 0;
  const accountEmail = (account.results as AccountResults | null)?.email ?? "";
  const accountPct = account.total > 0 ? Math.round((account.progress / account.total) * 100) : 0;

  const breachHits = (breach.results as BreachResults | null)?.breaches ?? [];
  const breachEmail = (breach.results as BreachResults | null)?.email ?? "";

  return (
    <div className="p-8">
      {/* DuckDuckGo Scanner */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Scan</h1>
          <p className="text-sm text-gray-500 mt-1">
            Search for your personal data across data broker sites
          </p>
        </div>
        <button
          onClick={() => scan.start()}
          disabled={scan.running}
          className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 transition disabled:opacity-50"
        >
          {scan.running ? (
            <><Loader2 className="w-4 h-4 animate-spin" /> Scanning...</>
          ) : (
            <><Search className="w-4 h-4" /> {scan.hasResults ? "Scan Again" : "Start Scan"}</>
          )}
        </button>
      </div>

      {scan.error && (
        <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">{scan.error}</div>
      )}

      {scan.running && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-6 mb-6">
          <div className="flex items-center gap-3 mb-3">
            <Loader2 className="w-5 h-5 text-indigo-600 animate-spin" />
            <p className="text-indigo-900 font-medium">
              Scanning... {scan.progress}/{scan.total} searches completed
            </p>
          </div>
          <div className="w-full bg-indigo-200 rounded-full h-2">
            <div
              className="bg-indigo-600 h-2 rounded-full transition-all duration-500"
              style={{ width: `${scanPct}%` }}
            />
          </div>
          <p className="text-indigo-600 text-xs mt-2">
            Searching DuckDuckGo for your data across all registered brokers.
            This takes a few minutes due to rate limiting.
          </p>
        </div>
      )}

      {!scan.running && !scan.hasResults && !scan.error && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
          <Search className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-gray-700 mb-2">No scan results yet</h2>
          <p className="text-gray-500 text-sm max-w-md mx-auto">
            Click "Start Scan" to search for your personal data across data
            broker and people-search sites via DuckDuckGo. Note: most data
            brokers keep data behind login walls, so this mainly finds
            people-search sites. For full coverage, use the Art. 15 blast from
            the Dashboard.
          </p>
        </div>
      )}

      {!scan.running && scan.hasResults && (
        <>
          <div className="flex gap-4 mb-6">
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex-1">
              <div className="flex items-center gap-3">
                {scanHits.length > 0 ? (
                  <AlertTriangle className="w-8 h-8 text-orange-500" />
                ) : (
                  <CheckCircle className="w-8 h-8 text-green-500" />
                )}
                <div>
                  <p className="text-2xl font-bold">{scanHits.length}</p>
                  <p className="text-sm text-gray-500">
                    {scanHits.length === 1 ? "site likely has your data" : "sites likely have your data"}
                  </p>
                </div>
              </div>
            </div>
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex-1">
              <p className="text-2xl font-bold">{scanChecked}</p>
              <p className="text-sm text-gray-500">searches performed</p>
            </div>
          </div>

          {scanHits.length > 0 ? (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200">
              <div className="px-5 py-4 border-b border-gray-200">
                <h2 className="font-semibold">Found Results</h2>
                <p className="text-xs text-gray-500 mt-1">
                  These sites likely contain your personal data. Click to verify, then create a removal request.
                </p>
              </div>
              <div className="divide-y divide-gray-100">
                {scanHits.map((hit) => (
                  <div key={hit.broker_domain} className="px-5 py-4">
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-medium text-sm">{hit.broker_name}</span>
                          <span className="text-xs text-gray-400">{hit.broker_domain}</span>
                        </div>
                        {hit.snippet && <p className="text-xs text-gray-500 truncate">{hit.snippet}</p>}
                      </div>
                      <div className="flex items-center gap-2 ml-4 shrink-0">
                        {hit.url && (
                          <a href={hit.url} target="_blank" rel="noopener noreferrer"
                            className="flex items-center gap-1 px-3 py-1 text-xs bg-gray-50 text-gray-600 rounded-lg hover:bg-gray-100 transition">
                            <ExternalLink className="w-3 h-3" /> Verify
                          </a>
                        )}
                        <button onClick={() => handleCreateRequest(hit.broker_domain, "erasure")}
                          className="px-3 py-1 text-xs bg-indigo-50 text-indigo-700 rounded-lg hover:bg-indigo-100 transition">
                          Art. 17
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center">
              <CheckCircle className="w-8 h-8 text-green-600 mx-auto mb-3" />
              <p className="text-green-900 font-medium">No data found in search results</p>
              <p className="text-green-700 text-sm mt-1">
                Most data brokers don't expose data to search engines. Use the
                Art. 15 blast from the Dashboard to ask them directly — they're
                legally required to respond within 30 days.
              </p>
            </div>
          )}
        </>
      )}

      {/* Re-scan Monitoring Alerts */}
      {rescanLoaded && rescanReappeared.length > 0 && (
        <div className="mt-10">
          <div className="bg-red-50 border-2 border-red-300 rounded-xl p-6">
            <div className="flex items-center gap-3 mb-4">
              <RefreshCw className="w-6 h-6 text-red-600" />
              <div>
                <h2 className="text-lg font-bold text-red-900">Data Reappeared</h2>
                <p className="text-sm text-red-700">
                  {rescanReappeared.length} {rescanReappeared.length === 1 ? "broker has" : "brokers have"} re-listed
                  your data after confirmed deletion. Consider sending a new removal request.
                </p>
              </div>
            </div>
            <div className="space-y-2">
              {rescanReappeared.map((alert) => (
                <div key={alert.broker_domain} className="bg-white rounded-lg px-4 py-3 flex items-center justify-between">
                  <div>
                    <span className="font-medium text-sm text-red-900">{alert.broker_name}</span>
                    <span className="text-xs text-red-500 ml-2">{alert.broker_domain}</span>
                    {alert.previous_removal_date && (
                      <span className="text-xs text-red-400 ml-2">removed {alert.previous_removal_date}</span>
                    )}
                  </div>
                  <button
                    onClick={() => handleCreateRequest(alert.broker_domain, "erasure")}
                    className="px-3 py-1 text-xs bg-red-100 text-red-700 rounded-lg hover:bg-red-200 transition"
                  >
                    Re-send Art. 17
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {rescanLoaded && rescanNewExposures.length > 0 && rescanReappeared.length === 0 && (
        <div className="mt-10">
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-6">
            <div className="flex items-center gap-3 mb-4">
              <AlertTriangle className="w-6 h-6 text-amber-600" />
              <div>
                <h2 className="text-lg font-bold text-amber-900">New Exposures Detected</h2>
                <p className="text-sm text-amber-700">
                  {rescanNewExposures.length} new {rescanNewExposures.length === 1 ? "site" : "sites"} found
                  since your last scan.
                </p>
              </div>
            </div>
            <div className="space-y-2">
              {rescanNewExposures.map((alert) => (
                <div key={alert.broker_domain} className="bg-white rounded-lg px-4 py-3 flex items-center justify-between">
                  <span className="font-medium text-sm">{alert.broker_name} <span className="text-xs text-gray-400">{alert.broker_domain}</span></span>
                  <button
                    onClick={() => handleCreateRequest(alert.broker_domain, "erasure")}
                    className="px-3 py-1 text-xs bg-amber-100 text-amber-700 rounded-lg hover:bg-amber-200 transition"
                  >
                    Art. 17
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Breach Scanner (HIBP) */}
      <div className="mt-10">
        <div className="mb-6">
          <h2 className="text-xl font-bold">Breach Scanner</h2>
          <p className="text-sm text-gray-500 mt-1 mb-4">
            Check if your email has appeared in known data breaches via Have I Been Pwned
          </p>

          {hibpConfigured === false && (
            <div className="bg-orange-50 border border-orange-200 rounded-xl p-4 mb-4 text-sm text-orange-800">
              <span className="font-medium">HIBP API key not configured.</span>{" "}
              <a href="/settings" className="underline hover:text-orange-900">
                Add your key in Settings
              </a>{" "}
              to use this feature. Keys are available at{" "}
              <a href="https://haveibeenpwned.com/API/Key" target="_blank" rel="noopener noreferrer"
                className="underline hover:text-orange-900">
                haveibeenpwned.com/API/Key
              </a>.
            </div>
          )}

          <div className="flex gap-3">
            <div className="flex-1">
              <input
                type="email"
                placeholder="Enter email to check (leave empty for profile email)"
                value={breachEmailInput}
                onChange={(e) => setBreachEmailInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !breach.running && hibpConfigured && breach.start(breachEmailInput.trim() || undefined)}
                disabled={!hibpConfigured}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-lg bg-white focus:ring-2 focus:ring-red-500 focus:border-transparent outline-none text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              />
              {profileEmails.length > 1 && (
                <div className="flex gap-1.5 mt-1.5">
                  {profileEmails.map((em) => (
                    <button key={em} onClick={() => setBreachEmailInput(em)}
                      className="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded hover:bg-gray-200 transition truncate max-w-[200px]">{em}</button>
                  ))}
                </div>
              )}
            </div>
            <button
              onClick={() => breach.start(breachEmailInput.trim() || undefined)}
              disabled={breach.running || !hibpConfigured}
              className="flex items-center gap-2 px-5 py-2.5 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 transition disabled:opacity-50 shrink-0"
            >
              {breach.running ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Checking...</>
              ) : (
                <><ShieldAlert className="w-4 h-4" /> {breach.hasResults ? "Check Again" : "Check Breaches"}</>
              )}
            </button>
          </div>
        </div>

        {breach.error && (
          <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">{breach.error}</div>
        )}

        {breach.running && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-6 mb-6">
            <div className="flex items-center gap-3">
              <Loader2 className="w-5 h-5 text-red-600 animate-spin" />
              <p className="text-red-900 font-medium">
                Checking {breachEmail} against known breaches...
              </p>
            </div>
          </div>
        )}

        {!breach.running && !breach.hasResults && !breach.error && hibpConfigured && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
            <ShieldAlert className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-gray-700 mb-2">No breach results yet</h3>
            <p className="text-gray-500 text-sm max-w-md mx-auto">
              Click "Check Breaches" to query Have I Been Pwned and find out if your
              email has appeared in any known data breaches.
            </p>
          </div>
        )}

        {!breach.running && breach.hasResults && (
          <>
            <div className="flex gap-4 mb-6">
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex-1">
                <div className="flex items-center gap-3">
                  {breachHits.length > 0 ? (
                    <AlertTriangle className="w-8 h-8 text-red-500" />
                  ) : (
                    <CheckCircle className="w-8 h-8 text-green-500" />
                  )}
                  <div>
                    <p className="text-2xl font-bold">{breachHits.length}</p>
                    <p className="text-sm text-gray-500">
                      {breachHits.length === 1 ? "breach found" : "breaches found"}
                    </p>
                  </div>
                </div>
              </div>
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex-1">
                <p className="text-sm text-gray-500">Checked email</p>
                <p className="font-medium text-sm mt-1">{breachEmail}</p>
              </div>
            </div>

            {breachHits.length > 0 ? (
              <div className="bg-white rounded-xl shadow-sm border border-gray-200">
                <div className="px-5 py-4 border-b border-gray-200">
                  <h3 className="font-semibold">Breaches Found</h3>
                  <p className="text-xs text-gray-500 mt-1">
                    Your email was found in these data breaches. Consider changing passwords for affected services.
                  </p>
                </div>
                <div className="divide-y divide-gray-100">
                  {breachHits.map((breach_item) => (
                    <div key={breach_item.name} className="px-5 py-4">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <ShieldAlert className="w-4 h-4 text-red-500 shrink-0" />
                            <span className="font-medium text-sm">{breach_item.title}</span>
                            {breach_item.domain && (
                              <span className="text-xs text-gray-400">{breach_item.domain}</span>
                            )}
                          </div>
                          <div className="flex flex-wrap gap-1 mt-2">
                            {breach_item.data_classes.map((dc) => (
                              <span key={dc} className="px-2 py-0.5 bg-red-50 text-red-700 rounded text-xs">
                                {dc}
                              </span>
                            ))}
                          </div>
                        </div>
                        <div className="text-right shrink-0">
                          <p className="text-xs text-gray-500">{breach_item.breach_date}</p>
                          <p className="text-xs text-gray-400 mt-0.5">
                            {breach_item.pwn_count.toLocaleString()} records
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center">
                <CheckCircle className="w-8 h-8 text-green-600 mx-auto mb-3" />
                <p className="text-green-900 font-medium">No breaches found</p>
                <p className="text-green-700 text-sm mt-1">
                  Your email was not found in any known data breaches. Stay vigilant!
                </p>
              </div>
            )}
          </>
        )}
      </div>

      {/* Account Scanner (Holehe) */}
      <div className="mt-10">
        <div className="mb-6">
          <h2 className="text-xl font-bold">Account Scanner</h2>
          <p className="text-sm text-gray-500 mt-1 mb-4">
            Check which online services have an account registered with an email address
          </p>
          <div className="flex gap-3">
            <div className="flex-1">
              <input
                type="email"
                placeholder="Enter email to check (leave empty for profile email)"
                value={accountEmailInput}
                onChange={(e) => setAccountEmailInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !account.running && account.start(accountEmailInput.trim() || undefined)}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-lg bg-white focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none text-sm"
              />
              {profileEmails.length > 1 && (
                <div className="flex gap-1.5 mt-1.5">
                  {profileEmails.map((em) => (
                    <button key={em} onClick={() => setAccountEmailInput(em)}
                      className="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded hover:bg-gray-200 transition truncate max-w-[200px]">{em}</button>
                  ))}
                </div>
              )}
            </div>
            <button
              onClick={() => account.start(accountEmailInput.trim() || undefined)}
              disabled={account.running}
              className="flex items-center gap-2 px-5 py-2.5 bg-violet-600 text-white rounded-lg font-medium hover:bg-violet-700 transition disabled:opacity-50 shrink-0"
            >
              {account.running ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Checking...</>
              ) : (
                <><Mail className="w-4 h-4" /> {account.hasResults ? "Check Again" : "Check Accounts"}</>
              )}
            </button>
          </div>
        </div>

        {account.error && (
          <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">{account.error}</div>
        )}

        {account.running && (
          <div className="bg-violet-50 border border-violet-200 rounded-xl p-6 mb-6">
            <div className="flex items-center gap-3 mb-3">
              <Loader2 className="w-5 h-5 text-violet-600 animate-spin" />
              <p className="text-violet-900 font-medium">
                Checking {accountEmail}... {account.progress}/{account.total} services checked
              </p>
            </div>
            <div className="w-full bg-violet-200 rounded-full h-2">
              <div
                className="bg-violet-600 h-2 rounded-full transition-all duration-500"
                style={{ width: `${accountPct}%` }}
              />
            </div>
            <p className="text-violet-600 text-xs mt-2">
              Probing 120+ service login endpoints to detect registered accounts.
            </p>
          </div>
        )}

        {!account.running && !account.hasResults && !account.error && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
            <Mail className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-gray-700 mb-2">No account scan results yet</h3>
            <p className="text-gray-500 text-sm max-w-md mx-auto">
              Click "Check Accounts" to probe 120+ online services and find out
              which ones have an account registered with your email address.
              No password required.
            </p>
          </div>
        )}

        {!account.running && account.hasResults && (
          <>
            <div className="flex gap-4 mb-6">
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex-1">
                <div className="flex items-center gap-3">
                  {accountHits.length > 0 ? (
                    <AlertTriangle className="w-8 h-8 text-orange-500" />
                  ) : (
                    <CheckCircle className="w-8 h-8 text-green-500" />
                  )}
                  <div>
                    <p className="text-2xl font-bold">{accountHits.length}</p>
                    <p className="text-sm text-gray-500">
                      {accountHits.length === 1 ? "service has your email registered" : "services have your email registered"}
                    </p>
                  </div>
                </div>
              </div>
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex-1">
                <p className="text-2xl font-bold">{accountChecked}</p>
                <p className="text-sm text-gray-500">services checked for <span className="font-medium">{accountEmail}</span></p>
              </div>
            </div>

            {accountHits.length > 0 ? (
              <div className="bg-white rounded-xl shadow-sm border border-gray-200">
                <div className="px-5 py-4 border-b border-gray-200">
                  <h3 className="font-semibold">Registered Accounts Found</h3>
                  <p className="text-xs text-gray-500 mt-1">
                    Your email address is registered with these services.
                  </p>
                </div>
                <div className="divide-y divide-gray-100">
                  {accountHits.map((hit) => (
                    <div key={hit.service} className="px-5 py-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <Mail className="w-4 h-4 text-violet-500 shrink-0" />
                          <span className="font-medium text-sm">{hit.service}</span>
                        </div>
                        {hit.url && (
                          <a
                            href={hit.url.startsWith("http") ? hit.url : `https://${hit.url}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1 px-3 py-1 text-xs bg-gray-50 text-gray-600 rounded-lg hover:bg-gray-100 transition"
                          >
                            <ExternalLink className="w-3 h-3" /> Visit
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center">
                <CheckCircle className="w-8 h-8 text-green-600 mx-auto mb-3" />
                <p className="text-green-900 font-medium">No registered accounts found</p>
                <p className="text-green-700 text-sm mt-1">
                  Your email was not detected as registered on any of the checked services.
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
