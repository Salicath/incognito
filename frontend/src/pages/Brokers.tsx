import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Search, Loader2 } from "lucide-react";

interface BrokerItem { id: string; name: string; domain: string; category: string; dpo_email: string; removal_method: string; country: string; gdpr_applies: boolean; language: string; }

export default function Brokers() {
  const [brokers, setBrokers] = useState<BrokerItem[]>([]);
  const [search, setSearch] = useState("");
  const [countryFilter, setCountryFilter] = useState("");
  const [methodFilter, setMethodFilter] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [creatingRequest, setCreatingRequest] = useState("");

  useEffect(() => { api.getBrokers().then((data) => setBrokers(data as unknown as BrokerItem[])); }, []);

  const filtered = brokers.filter((b) => {
    const matchesSearch = b.name.toLowerCase().includes(search.toLowerCase()) || b.domain.toLowerCase().includes(search.toLowerCase());
    const matchesCountry = !countryFilter || b.country === countryFilter;
    const matchesMethod = !methodFilter || b.removal_method === methodFilter;
    return matchesSearch && matchesCountry && matchesMethod;
  });

  // Compute unique countries sorted by frequency
  const countryCounts: Record<string, number> = {};
  for (const b of brokers) {
    countryCounts[b.country] = (countryCounts[b.country] || 0) + 1;
  }
  const countries = Object.entries(countryCounts).sort((a, b) => b[1] - a[1]);

  const emailCount = brokers.filter((b) => b.removal_method === "email").length;
  const webFormCount = brokers.filter((b) => b.removal_method === "web_form").length;

  async function handleCreateRequest(brokerId: string, requestType: string) {
    const key = `${brokerId}:${requestType}`;
    setCreatingRequest(key);
    try {
      await api.createRequest(brokerId, requestType);
      setSuccessMessage(`${requestType === "access" ? "Art. 15" : "Art. 17"} request created for ${brokerId}`);
      setTimeout(() => setSuccessMessage(""), 3000);
    } finally {
      setCreatingRequest("");
    }
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Brokers</h1>
        <div className="flex items-center gap-3 text-sm text-gray-500 dark:text-gray-400">
          <span>{brokers.length} total</span>
          <span className="text-gray-300 dark:text-gray-600">|</span>
          <span>{emailCount} email</span>
          <span className="text-gray-300 dark:text-gray-600">|</span>
          <span>{webFormCount} web form</span>
          <span className="text-gray-300 dark:text-gray-600">|</span>
          <span>{countries.length} countries</span>
        </div>
      </div>

      {/* Search and filters */}
      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500" />
          <input
            type="text"
            placeholder="Search brokers..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search brokers"
            className="w-full pl-10 pr-4 py-2.5 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 dark:text-gray-100 focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none text-sm"
          />
        </div>
        <div className="flex gap-2">
          <select
            value={countryFilter}
            onChange={(e) => setCountryFilter(e.target.value)}
            aria-label="Filter by country"
            className="px-3 py-2.5 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 dark:text-gray-100 text-sm outline-none"
          >
            <option value="">All countries</option>
            {countries.map(([code, count]) => (
              <option key={code} value={code}>{code} ({count})</option>
            ))}
          </select>
          <select
            value={methodFilter}
            onChange={(e) => setMethodFilter(e.target.value)}
            aria-label="Filter by removal method"
            className="px-3 py-2.5 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 dark:text-gray-100 text-sm outline-none"
          >
            <option value="">All methods</option>
            <option value="email">Email ({emailCount})</option>
            <option value="web_form">Web form ({webFormCount})</option>
          </select>
          {(countryFilter || methodFilter) && (
            <button
              onClick={() => { setCountryFilter(""); setMethodFilter(""); }}
              className="px-3 py-2.5 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {successMessage && (
        <div className="bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 px-4 py-2 rounded-lg text-sm mb-4" role="alert">
          {successMessage}
        </div>
      )}

      <p className="text-xs text-gray-400 dark:text-gray-500 mb-2">
        Showing {filtered.length} of {brokers.length} brokers
      </p>

      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
        {filtered.length === 0 ? (
          <p className="px-5 py-8 text-gray-500 dark:text-gray-400 text-center text-sm">No brokers found.</p>
        ) : (
          <div className="divide-y divide-gray-100 dark:divide-gray-800">
            {filtered.map((broker) => (
              <div key={broker.id} className="px-5 py-3 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div>
                    <p className="text-sm font-medium">{broker.name}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">{broker.domain} · {broker.country}</p>
                  </div>
                  <span className="px-2 py-0.5 rounded text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hidden sm:inline">
                    {broker.removal_method.replace("_", " ")}
                  </span>
                  {broker.gdpr_applies && (
                    <span className="px-2 py-0.5 rounded text-xs bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 hidden sm:inline">
                      GDPR
                    </span>
                  )}
                </div>
                <div className="flex gap-2">
                  <button onClick={() => handleCreateRequest(broker.id, "access")} disabled={!!creatingRequest}
                    className="flex items-center gap-1 px-3 py-1 text-xs bg-gray-50 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition disabled:opacity-50">
                    {creatingRequest === `${broker.id}:access` ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                    Art. 15
                  </button>
                  <button onClick={() => handleCreateRequest(broker.id, "erasure")} disabled={!!creatingRequest}
                    className="flex items-center gap-1 px-3 py-1 text-xs bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400 rounded-lg hover:bg-indigo-100 dark:hover:bg-indigo-900/50 transition disabled:opacity-50">
                    {creatingRequest === `${broker.id}:erasure` ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                    Art. 17
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
