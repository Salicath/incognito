import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Shield } from "lucide-react";

type Step = "password" | "profile" | "confirm";

export default function SetupWizard() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("password");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [profile, setProfile] = useState({
    full_name: "",
    previous_names: [] as string[],
    date_of_birth: "",
    emails: [""],
    phones: [""],
    addresses: [] as Array<{ street: string; city: string; postal_code: string; country: string }>,
  });
  const steps: Step[] = ["password", "profile", "confirm"];
  const currentIndex = steps.indexOf(step);

  async function handleSubmit() {
    setLoading(true);
    setError("");
    try {
      await api.setup({
        password,
        profile: {
          ...profile,
          emails: profile.emails.filter((e) => e.trim()),
          phones: profile.phones.filter((p) => p.trim()),
          date_of_birth: profile.date_of_birth || undefined,
        },
      });
      navigate("/");
      window.location.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Setup failed");
    } finally {
      setLoading(false);
    }
  }

  const inputClass = "w-full px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 dark:text-gray-100 focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none";

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl max-w-xl w-full p-8">
        <div className="flex items-center gap-3 mb-6">
          <Shield className="w-8 h-8 text-indigo-600" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Incognito Setup</h1>
        </div>
        <div className="flex gap-2 mb-8">
          {steps.map((_, i) => (
            <div key={i} className={`h-1.5 flex-1 rounded-full ${i <= currentIndex ? "bg-indigo-600" : "bg-gray-200 dark:bg-gray-700"}`} />
          ))}
        </div>
        {error && <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">{error}</div>}

        {step === "password" && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Master Password</h2>
            <p className="text-sm text-gray-600 dark:text-gray-300">This encrypts your profile data. Choose something strong.</p>
            <input type="password" placeholder="Master password" value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} />
            <input type="password" placeholder="Confirm password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className={inputClass} />
            <button onClick={() => { if (password.length < 8) { setError("Password must be at least 8 characters"); return; } if (password !== confirmPassword) { setError("Passwords don't match"); return; } setError(""); setStep("profile"); }} className="w-full bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition">Continue</button>
          </div>
        )}

        {step === "profile" && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Your Identity</h2>
            <p className="text-sm text-gray-600 dark:text-gray-300">This is what we search for and include in removal requests.</p>
            <input type="text" placeholder="Full name" value={profile.full_name} onChange={(e) => setProfile({ ...profile, full_name: e.target.value })} className={inputClass} />
            <input type="date" value={profile.date_of_birth} onChange={(e) => setProfile({ ...profile, date_of_birth: e.target.value })} className={inputClass} />
            <input type="email" placeholder="Primary email" value={profile.emails[0]} onChange={(e) => setProfile({ ...profile, emails: [e.target.value, ...profile.emails.slice(1)] })} className={inputClass} />
            <input type="tel" placeholder="Phone (optional)" value={profile.phones[0]} onChange={(e) => setProfile({ ...profile, phones: [e.target.value] })} className={inputClass} />
            <div className="flex gap-3">
              <button onClick={() => setStep("password")} className="flex-1 border border-gray-300 dark:border-gray-600 py-2.5 rounded-lg font-medium hover:bg-gray-50 dark:hover:bg-gray-800 transition">Back</button>
              <button onClick={() => { if (!profile.full_name.trim()) { setError("Name is required"); return; } if (!profile.emails[0]?.trim()) { setError("At least one email is required"); return; } setError(""); setStep("confirm"); }} className="flex-1 bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition">Continue</button>
            </div>
          </div>
        )}

        {step === "confirm" && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Confirm Setup</h2>
            <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 text-sm space-y-2">
              <p><span className="font-medium">Name:</span> {profile.full_name}</p>
              <p><span className="font-medium">Email:</span> {profile.emails.filter((e) => e.trim()).join(", ")}</p>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-300">Your profile will be encrypted with your master password and stored locally.</p>
            <div className="flex gap-3">
              <button onClick={() => setStep("profile")} className="flex-1 border border-gray-300 dark:border-gray-600 py-2.5 rounded-lg font-medium hover:bg-gray-50 dark:hover:bg-gray-800 transition">Back</button>
              <button onClick={handleSubmit} disabled={loading} className="flex-1 bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition disabled:opacity-50">{loading ? "Setting up..." : "Complete Setup"}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
