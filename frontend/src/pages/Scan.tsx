import { useEffect, useState, useRef } from "react";
import { api } from "../api/client";
import { Search, ExternalLink, AlertTriangle, CheckCircle, Loader2, Mail } from "lucide-react";

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

export default function Scan() {
  const [scanning, setScanning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [total, setTotal] = useState(0);
  const [results, setResults] = useState<ScanHit[]>([]);
  const [hasResults, setHasResults] = useState(false);
  const [checked, setChecked] = useState(0);
  const [error, setError] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Account scan state
  const [accountScanning, setAccountScanning] = useState(false);
  const [accountProgress, setAccountProgress] = useState(0);
  const [accountTotal, setAccountTotal] = useState(0);
  const [accountResults, setAccountResults] = useState<AccountHit[]>([]);
  const [accountHasResults, setAccountHasResults] = useState(false);
  const [accountChecked, setAccountChecked] = useState(0);
  const [accountEmail, setAccountEmail] = useState("");
  const [accountError, setAccountError] = useState("");
  const accountPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    loadResults();
    checkIfRunning();
    loadAccountResults();
    checkIfAccountRunning();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (accountPollRef.current) clearInterval(accountPollRef.current);
    };
  }, []);

  async function checkIfRunning() {
    try {
      const status = await api.getScanStatus();
      if (status.running) {
        setScanning(true);
        setProgress(status.progress);
        setTotal(status.total);
        startPolling();
      }
    } catch {
      // ignore
    }
  }

  async function loadResults() {
    try {
      const data = await api.getScanResults();
      setResults(data.hits);
      setHasResults(data.has_results);
      setChecked(data.checked);
    } catch {
      // No results yet
    }
  }

  function startPolling() {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const status = await api.getScanStatus();
        setProgress(status.progress);
        setTotal(status.total);
        if (status.error) {
          setError(status.error);
          setScanning(false);
          if (pollRef.current) clearInterval(pollRef.current);
          return;
        }
        if (!status.running) {
          setScanning(false);
          if (pollRef.current) clearInterval(pollRef.current);
          await loadResults();
        }
      } catch {
        // ignore poll errors
      }
    }, 2000);
  }

  async function startScan() {
    setScanning(true);
    setError("");
    setProgress(0);
    try {
      const data = await api.startScan();
      setTotal(data.total);
      startPolling();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
      setScanning(false);
    }
  }

  async function checkIfAccountRunning() {
    try {
      const status = await api.getAccountStatus();
      if (status.running) {
        setAccountScanning(true);
        setAccountProgress(status.progress);
        setAccountTotal(status.total);
        startAccountPolling();
      }
    } catch {
      // ignore
    }
  }

  async function loadAccountResults() {
    try {
      const data = await api.getAccountResults();
      setAccountResults(data.hits);
      setAccountHasResults(data.has_results);
      setAccountChecked(data.checked);
      setAccountEmail(data.email);
    } catch {
      // No results yet
    }
  }

  function startAccountPolling() {
    if (accountPollRef.current) clearInterval(accountPollRef.current);
    accountPollRef.current = setInterval(async () => {
      try {
        const status = await api.getAccountStatus();
        setAccountProgress(status.progress);
        setAccountTotal(status.total);
        if (status.error) {
          setAccountError(status.error);
          setAccountScanning(false);
          if (accountPollRef.current) clearInterval(accountPollRef.current);
          return;
        }
        if (!status.running) {
          setAccountScanning(false);
          if (accountPollRef.current) clearInterval(accountPollRef.current);
          await loadAccountResults();
        }
      } catch {
        // ignore poll errors
      }
    }, 2000);
  }

  async function startAccountScan() {
    setAccountScanning(true);
    setAccountError("");
    setAccountProgress(0);
    try {
      const data = await api.startAccountScan();
      setAccountEmail(data.email);
      startAccountPolling();
    } catch (e) {
      setAccountError(e instanceof Error ? e.message : "Account scan failed");
      setAccountScanning(false);
    }
  }

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

  const pct = total > 0 ? Math.round((progress / total) * 100) : 0;
  const accountPct = accountTotal > 0 ? Math.round((accountProgress / accountTotal) * 100) : 0;

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Scan</h1>
          <p className="text-sm text-gray-500 mt-1">
            Search for your personal data across data broker sites
          </p>
        </div>
        <button
          onClick={startScan}
          disabled={scanning}
          className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 transition disabled:opacity-50"
        >
          {scanning ? (
            <><Loader2 className="w-4 h-4 animate-spin" /> Scanning...</>
          ) : (
            <><Search className="w-4 h-4" /> {hasResults ? "Scan Again" : "Start Scan"}</>
          )}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">{error}</div>
      )}

      {scanning && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-6 mb-6">
          <div className="flex items-center gap-3 mb-3">
            <Loader2 className="w-5 h-5 text-indigo-600 animate-spin" />
            <p className="text-indigo-900 font-medium">
              Scanning... {progress}/{total} searches completed
            </p>
          </div>
          <div className="w-full bg-indigo-200 rounded-full h-2">
            <div
              className="bg-indigo-600 h-2 rounded-full transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="text-indigo-600 text-xs mt-2">
            Searching DuckDuckGo for your data across all registered brokers.
            This takes a few minutes due to rate limiting.
          </p>
        </div>
      )}

      {!scanning && !hasResults && !error && (
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

      {!scanning && hasResults && (
        <>
          <div className="flex gap-4 mb-6">
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex-1">
              <div className="flex items-center gap-3">
                {results.length > 0 ? (
                  <AlertTriangle className="w-8 h-8 text-orange-500" />
                ) : (
                  <CheckCircle className="w-8 h-8 text-green-500" />
                )}
                <div>
                  <p className="text-2xl font-bold">{results.length}</p>
                  <p className="text-sm text-gray-500">
                    {results.length === 1 ? "site likely has your data" : "sites likely have your data"}
                  </p>
                </div>
              </div>
            </div>
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex-1">
              <p className="text-2xl font-bold">{checked}</p>
              <p className="text-sm text-gray-500">searches performed</p>
            </div>
          </div>

          {results.length > 0 ? (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200">
              <div className="px-5 py-4 border-b border-gray-200">
                <h2 className="font-semibold">Found Results</h2>
                <p className="text-xs text-gray-500 mt-1">
                  These sites likely contain your personal data. Click to verify, then create a removal request.
                </p>
              </div>
              <div className="divide-y divide-gray-100">
                {results.map((hit) => (
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

      {/* Account Scanner (Holehe) */}
      <div className="mt-10">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-bold">Account Scanner</h2>
            <p className="text-sm text-gray-500 mt-1">
              Check which online services have an account registered with your email
            </p>
          </div>
          <button
            onClick={startAccountScan}
            disabled={accountScanning}
            className="flex items-center gap-2 px-5 py-2.5 bg-violet-600 text-white rounded-lg font-medium hover:bg-violet-700 transition disabled:opacity-50"
          >
            {accountScanning ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Checking...</>
            ) : (
              <><Mail className="w-4 h-4" /> {accountHasResults ? "Check Again" : "Check Accounts"}</>
            )}
          </button>
        </div>

        {accountError && (
          <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">{accountError}</div>
        )}

        {accountScanning && (
          <div className="bg-violet-50 border border-violet-200 rounded-xl p-6 mb-6">
            <div className="flex items-center gap-3 mb-3">
              <Loader2 className="w-5 h-5 text-violet-600 animate-spin" />
              <p className="text-violet-900 font-medium">
                Checking {accountEmail}... {accountProgress}/{accountTotal} services checked
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

        {!accountScanning && !accountHasResults && !accountError && (
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

        {!accountScanning && accountHasResults && (
          <>
            <div className="flex gap-4 mb-6">
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex-1">
                <div className="flex items-center gap-3">
                  {accountResults.length > 0 ? (
                    <AlertTriangle className="w-8 h-8 text-orange-500" />
                  ) : (
                    <CheckCircle className="w-8 h-8 text-green-500" />
                  )}
                  <div>
                    <p className="text-2xl font-bold">{accountResults.length}</p>
                    <p className="text-sm text-gray-500">
                      {accountResults.length === 1 ? "service has your email registered" : "services have your email registered"}
                    </p>
                  </div>
                </div>
              </div>
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex-1">
                <p className="text-2xl font-bold">{accountChecked}</p>
                <p className="text-sm text-gray-500">services checked for <span className="font-medium">{accountEmail}</span></p>
              </div>
            </div>

            {accountResults.length > 0 ? (
              <div className="bg-white rounded-xl shadow-sm border border-gray-200">
                <div className="px-5 py-4 border-b border-gray-200">
                  <h3 className="font-semibold">Registered Accounts Found</h3>
                  <p className="text-xs text-gray-500 mt-1">
                    Your email address is registered with these services.
                  </p>
                </div>
                <div className="divide-y divide-gray-100">
                  {accountResults.map((hit) => (
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
