import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAsyncTask } from "../hooks/useAsyncTask";
import { Search, ExternalLink, AlertTriangle, CheckCircle, Loader2, Mail, ShieldAlert, RefreshCw, Github } from "lucide-react";

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

interface WaybackHit {
  platform: string;
  username: string;
  url: string;
  snapshots: number;
  first_snapshot: string;
  last_snapshot: string;
  archive_url: string;
}

interface WaybackResults {
  has_results: boolean;
  usernames: string[];
  checked: number;
  hits: WaybackHit[];
  errors: string[];
}

interface DeepHit {
  service: string;
  url: string;
  username: string;
  tags: string[];
}

interface DeepResults {
  has_results: boolean;
  usernames: string[];
  checked: number;
  hits: DeepHit[];
  errors: string[];
}

interface GithubHit {
  identifier: string;
  repository: string;
  path: string;
  url: string;
}

interface GithubResults {
  has_results: boolean;
  identifiers: string[];
  checked: number;
  hits: GithubHit[];
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

  const [waybackInput, setWaybackInput] = useState("");
  const wayback = useAsyncTask<WaybackResults>({
    startFn: (usernames?: unknown) => api.startWaybackScan(usernames as string | undefined),
    statusFn: api.getWaybackStatus,
    resultsFn: api.getWaybackResults,
  });

  const [deepInput, setDeepInput] = useState("");
  const deep = useAsyncTask<DeepResults>({
    startFn: (usernames?: unknown) => api.startDeepScan(usernames as string | undefined),
    statusFn: api.getDeepScanStatus,
    resultsFn: api.getDeepScanResults,
  });

  const [githubConfigured, setGithubConfigured] = useState<boolean | null>(null);
  const github = useAsyncTask<GithubResults>({
    startFn: () => api.startGithubScan(),
    statusFn: api.getGithubStatus,
    resultsFn: api.getGithubResults,
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
    api.getGithubTokenStatus().then((s) => setGithubConfigured(s.configured)).catch(() => setGithubConfigured(false));
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
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
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
        <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-12 text-center">
          <Search className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">No scan results yet</h2>
          <p className="text-gray-500 dark:text-gray-400 text-sm max-w-md mx-auto">
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
            <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5 flex-1">
              <div className="flex items-center gap-3">
                {scanHits.length > 0 ? (
                  <AlertTriangle className="w-8 h-8 text-orange-500" />
                ) : (
                  <CheckCircle className="w-8 h-8 text-green-500" />
                )}
                <div>
                  <p className="text-2xl font-bold">{scanHits.length}</p>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {scanHits.length === 1 ? "site likely has your data" : "sites likely have your data"}
                  </p>
                </div>
              </div>
            </div>
            <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5 flex-1">
              <p className="text-2xl font-bold">{scanChecked}</p>
              <p className="text-sm text-gray-500 dark:text-gray-400">searches performed</p>
            </div>
          </div>

          {scanHits.length > 0 ? (
            <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
              <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700">
                <h2 className="font-semibold">Found Results</h2>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  These sites likely contain your personal data. Click to verify, then create a removal request.
                </p>
              </div>
              <div className="divide-y divide-gray-100 dark:divide-gray-800">
                {scanHits.map((hit) => (
                  <div key={hit.broker_domain} className="px-5 py-4">
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-medium text-sm">{hit.broker_name}</span>
                          <span className="text-xs text-gray-400 dark:text-gray-500">{hit.broker_domain}</span>
                        </div>
                        {hit.snippet && <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{hit.snippet}</p>}
                      </div>
                      <div className="flex items-center gap-2 ml-4 shrink-0">
                        {hit.url && (
                          <a href={hit.url} target="_blank" rel="noopener noreferrer"
                            className="flex items-center gap-1 px-3 py-1 text-xs bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition">
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
                <div key={alert.broker_domain} className="bg-white dark:bg-gray-900 rounded-lg px-4 py-3 flex items-center justify-between">
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
                <div key={alert.broker_domain} className="bg-white dark:bg-gray-900 rounded-lg px-4 py-3 flex items-center justify-between">
                  <span className="font-medium text-sm">{alert.broker_name} <span className="text-xs text-gray-400 dark:text-gray-500">{alert.broker_domain}</span></span>
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
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 mb-4">
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
                className="w-full px-4 py-2.5 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 dark:text-gray-100 focus:ring-2 focus:ring-red-500 focus:border-transparent outline-none text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              />
              {profileEmails.length > 1 && (
                <div className="flex gap-1.5 mt-1.5">
                  {profileEmails.map((em) => (
                    <button key={em} onClick={() => setBreachEmailInput(em)}
                      className="px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition truncate max-w-[200px]">{em}</button>
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
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-12 text-center">
            <ShieldAlert className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">No breach results yet</h3>
            <p className="text-gray-500 dark:text-gray-400 text-sm max-w-md mx-auto">
              Click "Check Breaches" to query Have I Been Pwned and find out if your
              email has appeared in any known data breaches.
            </p>
          </div>
        )}

        {!breach.running && breach.hasResults && (
          <>
            <div className="flex gap-4 mb-6">
              <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5 flex-1">
                <div className="flex items-center gap-3">
                  {breachHits.length > 0 ? (
                    <AlertTriangle className="w-8 h-8 text-red-500" />
                  ) : (
                    <CheckCircle className="w-8 h-8 text-green-500" />
                  )}
                  <div>
                    <p className="text-2xl font-bold">{breachHits.length}</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {breachHits.length === 1 ? "breach found" : "breaches found"}
                    </p>
                  </div>
                </div>
              </div>
              <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5 flex-1">
                <p className="text-sm text-gray-500 dark:text-gray-400">Checked email</p>
                <p className="font-medium text-sm mt-1">{breachEmail}</p>
              </div>
            </div>

            {breachHits.length > 0 ? (
              <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
                <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700">
                  <h3 className="font-semibold">Breaches Found</h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Your email was found in these data breaches. Consider changing passwords for affected services.
                  </p>
                </div>
                <div className="divide-y divide-gray-100 dark:divide-gray-800">
                  {breachHits.map((breach_item) => (
                    <div key={breach_item.name} className="px-5 py-4">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <ShieldAlert className="w-4 h-4 text-red-500 shrink-0" />
                            <span className="font-medium text-sm">{breach_item.title}</span>
                            {breach_item.domain && (
                              <span className="text-xs text-gray-400 dark:text-gray-500">{breach_item.domain}</span>
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
                          <p className="text-xs text-gray-500 dark:text-gray-400">{breach_item.breach_date}</p>
                          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
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

      {/* Account Scanner (user-scanner) */}
      <div className="mt-10">
        <div className="mb-6">
          <h2 className="text-xl font-bold">Account Scanner</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 mb-4">
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
                className="w-full px-4 py-2.5 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 dark:text-gray-100 focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none text-sm"
              />
              {profileEmails.length > 1 && (
                <div className="flex gap-1.5 mt-1.5">
                  {profileEmails.map((em) => (
                    <button key={em} onClick={() => setAccountEmailInput(em)}
                      className="px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition truncate max-w-[200px]">{em}</button>
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
                Checking {account.runningLabel || accountEmail}... {account.progress}/{account.total} services checked
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
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-12 text-center">
            <Mail className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">No account scan results yet</h3>
            <p className="text-gray-500 dark:text-gray-400 text-sm max-w-md mx-auto">
              Click "Check Accounts" to probe 120+ online services and find out
              which ones have an account registered with your email address.
              No password required.
            </p>
          </div>
        )}

        {!account.running && account.hasResults && (
          <>
            <div className="flex gap-4 mb-6">
              <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5 flex-1">
                <div className="flex items-center gap-3">
                  {accountHits.length > 0 ? (
                    <AlertTriangle className="w-8 h-8 text-orange-500" />
                  ) : (
                    <CheckCircle className="w-8 h-8 text-green-500" />
                  )}
                  <div>
                    <p className="text-2xl font-bold">{accountHits.length}</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {accountHits.length === 1 ? "service has your email registered" : "services have your email registered"}
                    </p>
                  </div>
                </div>
              </div>
              <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5 flex-1">
                <p className="text-2xl font-bold">{accountChecked}</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">services checked for <span className="font-medium">{accountEmail}</span></p>
              </div>
            </div>

            {accountHits.length > 0 ? (
              <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
                <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700">
                  <h3 className="font-semibold">Registered Accounts Found</h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Your email address is registered with these services.
                  </p>
                </div>
                <div className="divide-y divide-gray-100 dark:divide-gray-800">
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
                            className="flex items-center gap-1 px-3 py-1 text-xs bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition"
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

      {/* Wayback Archive Scanner */}
      <div className="mt-10">
        <div className="mb-6">
          <h2 className="text-xl font-bold">Archive Scanner</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 mb-4">
            Find archived copies of your profile pages in the Wayback Machine — deleted accounts can live on in the archive
          </p>
          <div className="flex gap-3">
            <input
              type="text"
              placeholder="Usernames, comma-separated (leave empty to use profile usernames / email handle)"
              value={waybackInput}
              onChange={(e) => setWaybackInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !wayback.running && wayback.start(waybackInput.trim() || undefined)}
              className="flex-1 px-4 py-2.5 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 dark:text-gray-100 focus:ring-2 focus:ring-amber-500 focus:border-transparent outline-none text-sm"
            />
            <button
              onClick={() => wayback.start(waybackInput.trim() || undefined)}
              disabled={wayback.running}
              className="flex items-center gap-2 px-5 py-2.5 bg-amber-600 text-white rounded-lg font-medium hover:bg-amber-700 transition disabled:opacity-50 shrink-0"
            >
              {wayback.running ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Searching...</>
              ) : (
                <><Search className="w-4 h-4" /> {wayback.hasResults ? "Search Again" : "Search Archive"}</>
              )}
            </button>
          </div>
        </div>

        {wayback.error && (
          <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">{wayback.error}</div>
        )}

        {wayback.running && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 mb-6">
            <div className="flex items-center gap-3 mb-3">
              <Loader2 className="w-5 h-5 text-amber-600 animate-spin" />
              <p className="text-amber-900 font-medium">
                Checking {wayback.runningLabel}... {wayback.progress}/{wayback.total} profile URLs checked
              </p>
            </div>
            <div className="w-full bg-amber-200 rounded-full h-2">
              <div
                className="bg-amber-600 h-2 rounded-full transition-all duration-500"
                style={{ width: `${wayback.total > 0 ? Math.round((wayback.progress / wayback.total) * 100) : 0}%` }}
              />
            </div>
            <p className="text-amber-600 text-xs mt-2">
              Querying the Internet Archive CDX index for archived profile pages on 15 platforms.
            </p>
          </div>
        )}

        {!wayback.running && !wayback.hasResults && !wayback.error && (
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-12 text-center">
            <Search className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">No archive results yet</h3>
            <p className="text-gray-500 dark:text-gray-400 text-sm max-w-md mx-auto">
              Even after you delete an account, snapshots of your profile can
              remain in the Wayback Machine. This checks 15 platforms for
              archived copies. Removal requests go to info@archive.org.
            </p>
          </div>
        )}

        {!wayback.running && wayback.hasResults && (
          <>
            {((wayback.results as WaybackResults | null)?.errors ?? []).map((err) => (
              <div key={err} className="bg-yellow-50 text-yellow-800 px-4 py-3 rounded-lg mb-4 text-sm">{err}</div>
            ))}
            <div className="flex gap-4 mb-6">
              <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5 flex-1">
                <div className="flex items-center gap-3">
                  {((wayback.results as WaybackResults | null)?.hits.length ?? 0) > 0 ? (
                    <AlertTriangle className="w-8 h-8 text-orange-500" />
                  ) : (
                    <CheckCircle className="w-8 h-8 text-green-500" />
                  )}
                  <div>
                    <p className="text-2xl font-bold">{(wayback.results as WaybackResults | null)?.hits.length ?? 0}</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">archived profiles found</p>
                  </div>
                </div>
              </div>
              <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5 flex-1">
                <p className="text-2xl font-bold">{(wayback.results as WaybackResults | null)?.checked ?? 0}</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  profile URLs checked for <span className="font-medium">{((wayback.results as WaybackResults | null)?.usernames ?? []).join(", ")}</span>
                </p>
              </div>
            </div>

            {((wayback.results as WaybackResults | null)?.hits.length ?? 0) > 0 ? (
              <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
                <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700">
                  <h3 className="font-semibold">Archived Profiles Found</h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    These profile pages have snapshots in the Wayback Machine. If the live account is deleted,
                    email info@archive.org to request removal of the snapshots.
                  </p>
                </div>
                <div className="divide-y divide-gray-100 dark:divide-gray-800">
                  {((wayback.results as WaybackResults | null)?.hits ?? []).map((hit) => (
                    <div key={`${hit.platform}-${hit.username}`} className="px-5 py-4">
                      <div className="flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-medium text-sm">{hit.platform}</span>
                            <span className="text-xs text-gray-400 dark:text-gray-500">{hit.username}</span>
                          </div>
                          <p className="text-xs text-gray-500 dark:text-gray-400">
                            {hit.snapshots} snapshot{hit.snapshots === 1 ? "" : "s"}, {hit.first_snapshot.slice(0, 4)}–{hit.last_snapshot.slice(0, 4)}
                          </p>
                        </div>
                        <a href={hit.archive_url} target="_blank" rel="noopener noreferrer"
                          className="flex items-center gap-1 px-3 py-1 text-xs bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition shrink-0 ml-4">
                          <ExternalLink className="w-3 h-3" /> View snapshot
                        </a>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center">
                <CheckCircle className="w-8 h-8 text-green-600 mx-auto mb-3" />
                <p className="text-green-900 font-medium">No archived profiles found</p>
                <p className="text-green-700 text-sm mt-1">
                  The Wayback Machine has no snapshots of profile pages for these usernames.
                </p>
              </div>
            )}
          </>
        )}
      </div>

      {/* Deep Username Scanner (Maigret) */}
      <div className="mt-10">
        <div className="mb-6">
          <h2 className="text-xl font-bold">Deep Username Scan</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 mb-4">
            Enumerate ~3000 sites for accounts tied to a username (slower; up to 3 usernames). Requires Maigret installed.
          </p>
          <div className="flex gap-3">
            <input
              type="text"
              placeholder="Usernames, comma-separated (leave empty to use profile usernames / email handle)"
              value={deepInput}
              onChange={(e) => setDeepInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !deep.running && deep.start(deepInput.trim() || undefined)}
              className="flex-1 px-4 py-2.5 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 dark:text-gray-100 focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none text-sm"
            />
            <button
              onClick={() => deep.start(deepInput.trim() || undefined)}
              disabled={deep.running}
              className="flex items-center gap-2 px-5 py-2.5 bg-violet-600 text-white rounded-lg font-medium hover:bg-violet-700 transition disabled:opacity-50 shrink-0"
            >
              {deep.running ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Scanning...</>
              ) : (
                <><Search className="w-4 h-4" /> {deep.hasResults ? "Scan Again" : "Deep Scan"}</>
              )}
            </button>
          </div>
        </div>

        {deep.error && (
          <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">{deep.error}</div>
        )}

        {deep.running && (
          <div className="bg-violet-50 border border-violet-200 rounded-xl p-6 mb-6">
            <div className="flex items-center gap-3">
              <Loader2 className="w-5 h-5 text-violet-600 animate-spin" />
              <p className="text-violet-900 font-medium">
                Scanning {deep.runningLabel}... this can take a few minutes across ~3000 sites.
              </p>
            </div>
          </div>
        )}

        {!deep.running && !deep.hasResults && !deep.error && (
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-12 text-center">
            <Search className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">No deep-scan results yet</h3>
            <p className="text-gray-500 dark:text-gray-400 text-sm max-w-md mx-auto">
              Maigret checks a username against ~3000 sites and verifies each profile,
              extracting linked accounts and profile data. Slower than the account scan,
              but far broader. Found accounts appear in the Exposures inbox.
            </p>
          </div>
        )}

        {!deep.running && deep.hasResults && (
          <>
            {((deep.results as DeepResults | null)?.errors ?? []).map((err) => (
              <div key={err} className="bg-yellow-50 text-yellow-800 px-4 py-3 rounded-lg mb-4 text-sm">{err}</div>
            ))}
            <div className="flex gap-4 mb-6">
              <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5 flex-1">
                <div className="flex items-center gap-3">
                  {((deep.results as DeepResults | null)?.hits.length ?? 0) > 0 ? (
                    <AlertTriangle className="w-8 h-8 text-orange-500" />
                  ) : (
                    <CheckCircle className="w-8 h-8 text-green-500" />
                  )}
                  <div>
                    <p className="text-2xl font-bold">{(deep.results as DeepResults | null)?.hits.length ?? 0}</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">accounts found</p>
                  </div>
                </div>
              </div>
              <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5 flex-1">
                <p className="text-2xl font-bold">{(deep.results as DeepResults | null)?.checked ?? 0}</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  sites checked for <span className="font-medium">{((deep.results as DeepResults | null)?.usernames ?? []).join(", ")}</span>
                </p>
              </div>
            </div>

            {((deep.results as DeepResults | null)?.hits.length ?? 0) > 0 && (
              <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
                <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700">
                  <h3 className="font-semibold">Accounts Found</h3>
                </div>
                <div className="divide-y divide-gray-100 dark:divide-gray-800">
                  {((deep.results as DeepResults | null)?.hits ?? []).map((hit) => (
                    <div key={`${hit.service}-${hit.username}`} className="px-5 py-4 flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-medium text-sm">{hit.service}</span>
                          <span className="text-xs text-gray-400 dark:text-gray-500">{hit.username}</span>
                          {hit.tags.map((t) => (
                            <span key={t} className="text-[10px] uppercase tracking-wide bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300 px-1.5 py-0.5 rounded">{t}</span>
                          ))}
                        </div>
                      </div>
                      <a href={hit.url} target="_blank" rel="noopener noreferrer"
                        className="flex items-center gap-1 px-3 py-1 text-xs bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition shrink-0 ml-4">
                        <ExternalLink className="w-3 h-3" /> View profile
                      </a>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* GitHub Code Search Scanner */}
      <div className="mt-10">
        <div className="mb-6">
          <h2 className="text-xl font-bold">Code Leak Scanner</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 mb-4">
            Search public GitHub code for your email or phone — leaked in old commits, <code>.env</code> files, and gists
          </p>
          {githubConfigured === false && (
            <div className="bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 text-blue-800 dark:text-blue-200 px-4 py-3 rounded-lg mb-4 text-sm">
              A GitHub personal access token is required (code search is authenticated-only).
              Add one under Settings → GitHub token. A classic token with no scopes is enough.
            </div>
          )}
          <button
            onClick={() => github.start()}
            disabled={github.running || !githubConfigured}
            className="flex items-center gap-2 px-5 py-2.5 bg-gray-800 text-white rounded-lg font-medium hover:bg-gray-900 transition disabled:opacity-50"
          >
            {github.running ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Searching...</>
            ) : (
              <><Github className="w-4 h-4" /> {github.hasResults ? "Search Again" : "Search Code"}</>
            )}
          </button>
        </div>

        {github.error && (
          <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">{github.error}</div>
        )}

        {github.running && (
          <div className="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl p-6 mb-6">
            <div className="flex items-center gap-3 mb-3">
              <Loader2 className="w-5 h-5 text-gray-700 dark:text-gray-300 animate-spin" />
              <p className="text-gray-900 dark:text-gray-100 font-medium">
                Searching {github.runningLabel}... {github.progress}/{github.total} identifiers checked
              </p>
            </div>
            <div className="w-full bg-gray-300 dark:bg-gray-700 rounded-full h-2">
              <div
                className="bg-gray-700 dark:bg-gray-400 h-2 rounded-full transition-all duration-500"
                style={{ width: `${github.total > 0 ? Math.round((github.progress / github.total) * 100) : 0}%` }}
              />
            </div>
            <p className="text-gray-500 dark:text-gray-400 text-xs mt-2">
              GitHub code search is rate-limited to ~10 queries/min, so this paces itself (~7s per identifier).
            </p>
          </div>
        )}

        {!github.running && !github.hasResults && !github.error && githubConfigured && (
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-12 text-center">
            <Github className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">No code scan results yet</h3>
            <p className="text-gray-500 dark:text-gray-400 text-sm max-w-md mx-auto">
              Click "Search Code" to search public GitHub for your email and phone.
              Hits often point to leaked config committed by a service you signed up with.
            </p>
          </div>
        )}

        {!github.running && github.hasResults && (
          <>
            {((github.results as GithubResults | null)?.errors ?? []).map((err) => (
              <div key={err} className="bg-yellow-50 text-yellow-800 px-4 py-3 rounded-lg mb-4 text-sm">{err}</div>
            ))}
            <div className="flex gap-4 mb-6">
              <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5 flex-1">
                <div className="flex items-center gap-3">
                  {((github.results as GithubResults | null)?.hits.length ?? 0) > 0 ? (
                    <AlertTriangle className="w-8 h-8 text-orange-500" />
                  ) : (
                    <CheckCircle className="w-8 h-8 text-green-500" />
                  )}
                  <div>
                    <p className="text-2xl font-bold">{(github.results as GithubResults | null)?.hits.length ?? 0}</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">code matches found</p>
                  </div>
                </div>
              </div>
              <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5 flex-1">
                <p className="text-2xl font-bold">{(github.results as GithubResults | null)?.checked ?? 0}</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  identifiers searched: <span className="font-medium">{((github.results as GithubResults | null)?.identifiers ?? []).join(", ")}</span>
                </p>
              </div>
            </div>

            {((github.results as GithubResults | null)?.hits.length ?? 0) > 0 ? (
              <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
                <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700">
                  <h3 className="font-semibold">Code Matches Found</h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Your identifier appears in these public files. Open an issue or contact the repo owner to have it removed.
                  </p>
                </div>
                <div className="divide-y divide-gray-100 dark:divide-gray-800">
                  {((github.results as GithubResults | null)?.hits ?? []).map((hit) => (
                    <div key={hit.url} className="px-5 py-4">
                      <div className="flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <Github className="w-4 h-4 text-gray-500 shrink-0" />
                            <span className="font-medium text-sm truncate">{hit.repository}</span>
                            <span className="text-xs text-gray-400 dark:text-gray-500">{hit.identifier}</span>
                          </div>
                          <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{hit.path}</p>
                        </div>
                        <a href={hit.url} target="_blank" rel="noopener noreferrer"
                          className="flex items-center gap-1 px-3 py-1 text-xs bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition shrink-0 ml-4">
                          <ExternalLink className="w-3 h-3" /> View file
                        </a>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center">
                <CheckCircle className="w-8 h-8 text-green-600 mx-auto mb-3" />
                <p className="text-green-900 font-medium">No code leaks found</p>
                <p className="text-green-700 text-sm mt-1">
                  None of your identifiers appear in public GitHub code.
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
