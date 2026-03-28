import { useState, useEffect } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Shield, LayoutDashboard, Send, Database, Search, Settings, LogOut, Menu, X, Moon, Sun } from "lucide-react";
import { api } from "../api/client";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/requests", icon: Send, label: "Requests" },
  { to: "/brokers", icon: Database, label: "Brokers" },
  { to: "/scan", icon: Search, label: "Scan" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

export default function Layout({ onLock }: { onLock: () => void }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dark, setDark] = useState(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("theme") === "dark" ||
        (!localStorage.getItem("theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
    }
    return false;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  async function handleLock() {
    await api.lock();
    onLock();
  }

  return (
    <div className="min-h-screen flex">
      {/* Mobile top bar */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-50 bg-slate-900 text-white flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2">
          <Shield className="w-5 h-5 text-indigo-400" />
          <span className="font-bold">Incognito</span>
        </div>
        <button onClick={() => setSidebarOpen(!sidebarOpen)}>
          {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Sidebar overlay on mobile */}
      {sidebarOpen && (
        <div className="lg:hidden fixed inset-0 z-40 bg-black/50" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed lg:static inset-y-0 left-0 z-40 w-56 bg-slate-900 text-white flex flex-col
        transform transition-transform lg:transform-none
        ${sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
      `}>
        <div className="flex items-center gap-2.5 px-5 py-5 border-b border-slate-700">
          <Shield className="w-6 h-6 text-indigo-400" />
          <span className="font-bold text-lg">Incognito</span>
        </div>
        <nav className="flex-1 py-4">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-5 py-2.5 text-sm transition ${
                  isActive
                    ? "bg-slate-800 text-white font-medium"
                    : "text-slate-400 hover:text-white hover:bg-slate-800/50"
                }`
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-700">
          <button
            onClick={() => setDark(!dark)}
            className="flex items-center gap-3 px-5 py-3 text-sm text-slate-400 hover:text-white w-full transition"
          >
            {dark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            {dark ? "Light Mode" : "Dark Mode"}
          </button>
          <button
            onClick={handleLock}
            className="flex items-center gap-3 px-5 py-3 text-sm text-slate-400 hover:text-white w-full transition"
          >
            <LogOut className="w-4 h-4" />
            Lock
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 bg-gray-50 dark:bg-gray-950 overflow-auto pt-14 lg:pt-0">
        <Outlet />
      </main>
    </div>
  );
}
