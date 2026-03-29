import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Search } from "lucide-react";

interface BrokerItem { id: string; name: string; domain: string; category: string; dpo_email: string; removal_method: string; country: string; gdpr_applies: boolean; language: string; }

export default function Brokers() {
  const [brokers, setBrokers] = useState<BrokerItem[]>([]);
  const [search, setSearch] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  useEffect(() => { api.getBrokers().then((data) => setBrokers(data as unknown as BrokerItem[])); }, []);

  const filtered = brokers.filter((b) => b.name.toLowerCase().includes(search.toLowerCase()) || b.domain.toLowerCase().includes(search.toLowerCase()));

  async function handleCreateRequest(brokerId: string, requestType: string) {
    await api.createRequest(brokerId, requestType);
    setSuccessMessage(`${requestType === "access" ? "Art. 15" : "Art. 17"} request created for ${brokerId}`);
    setTimeout(() => setSuccessMessage(""), 3000);
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Brokers</h1>
        <span className="text-sm text-gray-500">{brokers.length} brokers in registry</span>
      </div>
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input type="text" placeholder="Search brokers..." value={search} onChange={(e) => setSearch(e.target.value)} className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-lg bg-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none text-sm" />
      </div>
      {successMessage && (
        <div className="bg-green-50 text-green-700 px-4 py-2 rounded-lg text-sm mb-4">
          {successMessage}
        </div>
      )}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        {filtered.length === 0 ? (
          <p className="px-5 py-8 text-gray-500 text-center text-sm">No brokers found.</p>
        ) : (
          <div className="divide-y divide-gray-100">
            {filtered.map((broker) => (
              <div key={broker.id} className="px-5 py-3 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div><p className="text-sm font-medium">{broker.name}</p><p className="text-xs text-gray-500">{broker.domain} · {broker.country}</p></div>
                  <span className="px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-600">{broker.removal_method.replace("_", " ")}</span>
                  {broker.gdpr_applies && <span className="px-2 py-0.5 rounded text-xs bg-green-50 text-green-700">GDPR</span>}
                </div>
                <div className="flex gap-2">
                  <button onClick={() => handleCreateRequest(broker.id, "access")} className="px-3 py-1 text-xs bg-gray-50 text-gray-700 rounded-lg hover:bg-gray-100 transition">Art. 15</button>
                  <button onClick={() => handleCreateRequest(broker.id, "erasure")} className="px-3 py-1 text-xs bg-indigo-50 text-indigo-700 rounded-lg hover:bg-indigo-100 transition">Art. 17</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
