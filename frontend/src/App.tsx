import { Routes, Route, Navigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "./api/client";
import SetupWizard from "./pages/SetupWizard";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Requests from "./pages/Requests";
import Brokers from "./pages/Brokers";

function LockScreen({ onUnlock }: { onUnlock: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function handleUnlock() {
    try { await api.unlock(password); onUnlock(); } catch { setError("Wrong password"); }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-sm w-full p-8 text-center">
        <h1 className="text-2xl font-bold mb-2">Incognito</h1>
        <p className="text-gray-500 text-sm mb-6">Enter your master password to unlock</p>
        {error && <p className="text-red-600 text-sm mb-3">{error}</p>}
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleUnlock()} placeholder="Master password" className="w-full px-4 py-2.5 border border-gray-300 rounded-lg mb-3 focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none" />
        <button onClick={handleUnlock} className="w-full bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition">Unlock</button>
      </div>
    </div>
  );
}

function App() {
  const [status, setStatus] = useState<{ initialized: boolean; authenticated: boolean; loading: boolean }>({ initialized: false, authenticated: false, loading: true });

  useEffect(() => { checkStatus(); }, []);

  async function checkStatus() {
    const [s, profile] = await Promise.all([api.getStatus(), api.getProfile().catch(() => null)]);
    setStatus({ initialized: s.initialized, authenticated: profile !== null, loading: false });
  }

  if (status.loading) return <div className="min-h-screen flex items-center justify-center"><p className="text-gray-500">Loading...</p></div>;
  if (!status.initialized) return <SetupWizard />;
  if (!status.authenticated) return <LockScreen onUnlock={() => setStatus({ ...status, authenticated: true })} />;

  return (
    <div className="min-h-screen">
      <Routes>
        <Route element={<Layout onLock={() => setStatus({ ...status, authenticated: false })} />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/requests" element={<Requests />} />
          <Route path="/brokers" element={<Brokers />} />
          <Route path="/settings" element={<p className="p-8">Settings page coming soon.</p>} />
        </Route>
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </div>
  );
}

export default App;
