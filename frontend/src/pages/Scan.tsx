import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Search, ExternalLink, AlertTriangle, CheckCircle, Loader2 } from "lucide-react";

interface ScanHit {
  broker_domain: string;
  broker_name: string;
  snippet: string;
  url: string;
}

export default function Scan() {
  const [scanning, setScanning] = useState(false);
  const [results, setResults] = useState<ScanHit[]>([]);
  const [hasResults, setHasResults] = useState(false);
  const [checked, setChecked] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    loadResults();
  }, []);

  async function loadResults() {
    try {
      const data = await api.getScanResults();
      setResults(data.hits);
      setHasResults(data.has_results);
      setChecked(data.checked);
    } catch {
      // No results yet, that's fine
    }
  }

  async function startScan() {
    setScanning(true);
    setError("");
    try {
      const data = await api.startScan();
      setChecked(data.checked);
      await loadResults();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }

  async function handleCreateRequest(brokerDomain: string, type: string) {
    try {
      // Find the broker ID from domain
      const brokers = await api.getBrokers();
      const broker = brokers.find(
        (b) => (b as Record<string, unknown>).domain === brokerDomain
      ) as Record<string, unknown> | undefined;

      if (broker) {
        await api.createRequest(broker.id as string, type);
        alert(`${type} request created for ${broker.name}`);
      } else {
        alert(`Broker for ${brokerDomain} not in registry. You may need to add it manually.`);
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to create request");
    }
  }

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
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Scanning...
            </>
          ) : (
            <>
              <Search className="w-4 h-4" />
              {hasResults ? "Scan Again" : "Start Scan"}
            </>
          )}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">
          {error}
        </div>
      )}

      {scanning && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-6 mb-6 text-center">
          <Loader2 className="w-8 h-8 text-indigo-600 animate-spin mx-auto mb-3" />
          <p className="text-indigo-900 font-medium">
            Scanning data broker sites...
          </p>
          <p className="text-indigo-600 text-sm mt-1">
            This may take a minute. Searching DuckDuckGo for your data across
            all registered brokers.
          </p>
        </div>
      )}

      {!scanning && !hasResults && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
          <Search className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-gray-700 mb-2">
            No scan results yet
          </h2>
          <p className="text-gray-500 text-sm max-w-md mx-auto">
            Click "Start Scan" to search for your personal data across data
            broker and people-search sites. We'll use DuckDuckGo to find where
            your information appears.
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
                  <p className="text-2xl font-bold">
                    {results.length}
                  </p>
                  <p className="text-sm text-gray-500">
                    {results.length === 1
                      ? "site likely has your data"
                      : "sites likely have your data"}
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
                  These sites likely contain your personal data. Click to verify,
                  then create a removal request.
                </p>
              </div>
              <div className="divide-y divide-gray-100">
                {results.map((hit) => (
                  <div
                    key={hit.broker_domain}
                    className="px-5 py-4"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-medium text-sm">
                            {hit.broker_name}
                          </span>
                          <span className="text-xs text-gray-400">
                            {hit.broker_domain}
                          </span>
                        </div>
                        {hit.snippet && (
                          <p className="text-xs text-gray-500 truncate">
                            {hit.snippet}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2 ml-4 shrink-0">
                        {hit.url && (
                          <a
                            href={hit.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1 px-3 py-1 text-xs bg-gray-50 text-gray-600 rounded-lg hover:bg-gray-100 transition"
                          >
                            <ExternalLink className="w-3 h-3" /> Verify
                          </a>
                        )}
                        <button
                          onClick={() =>
                            handleCreateRequest(hit.broker_domain, "erasure")
                          }
                          className="px-3 py-1 text-xs bg-indigo-50 text-indigo-700 rounded-lg hover:bg-indigo-100 transition"
                        >
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
              <p className="text-green-900 font-medium">
                No data found on searched broker sites
              </p>
              <p className="text-green-700 text-sm mt-1">
                Your data wasn't found in our search. This doesn't guarantee
                you're not listed — brokers may block search engine indexing.
                Consider sending Art. 15 access requests to verify directly.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
