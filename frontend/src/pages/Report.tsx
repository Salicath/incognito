import { useEffect, useState } from "react";
import { api } from "../api/client";
import ProgressRing from "../components/ProgressRing";
import StatusBadge from "../components/StatusBadge";
import { Shield, CheckCircle, Clock, AlertTriangle, Download } from "lucide-react";

interface ExposureReport {
  generated_at: string;
  score: number;
  grade: string;
  summary: {
    total_brokers_contacted: number;
    completed: number;
    in_progress: number;
    exposures_found: number;
  };
  brokers: Array<{
    broker_id: string;
    broker_name: string;
    status: string;
    sent_at: string | null;
    response_at: string | null;
  }>;
  exposures: Array<{
    source: string;
    broker_id: string;
    scanned_at: string | null;
    actioned: boolean;
  }>;
}

const gradeColors: Record<string, string> = {
  A: "#22c55e",
  B: "#3b82f6",
  C: "#f59e0b",
  D: "#f97316",
  F: "#ef4444",
};

const gradeLabels: Record<string, string> = {
  A: "Excellent",
  B: "Good",
  C: "Fair",
  D: "Poor",
  F: "At Risk",
};

export default function Report() {
  const [report, setReport] = useState<ExposureReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getExposureReport()
      .then(setReport)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-gray-500 dark:text-gray-400">Generating report...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <p className="text-red-600">{error}</p>
      </div>
    );
  }

  if (!report) return null;

  const color = gradeColors[report.grade] || "#6b7280";
  const { summary } = report;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Shield className="w-6 h-6 text-indigo-500" />
            Privacy Report
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Generated {new Date(report.generated_at).toLocaleDateString()}
          </p>
        </div>
        <a
          href="/api/requests/export/audit-trail?output_format=csv"
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition"
        >
          <Download className="w-4 h-4" />
          Export CSV
        </a>
      </div>

      {/* Score Card */}
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-8">
        <div className="flex flex-col sm:flex-row items-center gap-8">
          <div className="relative">
            <ProgressRing
              percentage={report.score}
              size={160}
              strokeWidth={12}
              color={color}
              trackColor="#e5e7eb"
            />
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-4xl font-bold" style={{ color }}>
                {report.grade}
              </span>
              <span className="text-sm text-gray-500 dark:text-gray-400">
                {report.score}/100
              </span>
            </div>
          </div>
          <div className="flex-1 text-center sm:text-left">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              Privacy Score: <span style={{ color }}>{gradeLabels[report.grade]}</span>
            </h2>
            <p className="text-gray-500 dark:text-gray-400 mt-2 max-w-md">
              {report.score >= 80
                ? "Great progress! Most of your data removal requests have been resolved."
                : report.score >= 50
                ? "Good start. Keep monitoring your requests as brokers respond."
                : report.score >= 20
                ? "Requests are in progress. Follow up on overdue brokers to improve your score."
                : summary.total_brokers_contacted > 0
                ? "Most requests are still pending. Check for overdue deadlines."
                : "Start by scanning for your data and sending removal requests."}
            </p>
          </div>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-4">
          <div className="flex items-center gap-2 text-green-600 dark:text-green-400 mb-1">
            <CheckCircle className="w-4 h-4" />
            <span className="text-sm font-medium">Completed</span>
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{summary.completed}</p>
        </div>
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-4">
          <div className="flex items-center gap-2 text-blue-600 dark:text-blue-400 mb-1">
            <Clock className="w-4 h-4" />
            <span className="text-sm font-medium">In Progress</span>
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{summary.in_progress}</p>
        </div>
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-4">
          <div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-400 mb-1">
            <Shield className="w-4 h-4" />
            <span className="text-sm font-medium">Brokers Contacted</span>
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{summary.total_brokers_contacted}</p>
        </div>
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-4">
          <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400 mb-1">
            <AlertTriangle className="w-4 h-4" />
            <span className="text-sm font-medium">Exposures Found</span>
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{summary.exposures_found}</p>
        </div>
      </div>

      {/* Broker Status Table */}
      {report.brokers.length > 0 && (
        <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800">
          <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800">
            <h3 className="font-semibold text-gray-900 dark:text-white">
              Broker Status ({report.brokers.length})
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-800">
                  <th className="px-6 py-3 font-medium">Broker</th>
                  <th className="px-6 py-3 font-medium">Status</th>
                  <th className="px-6 py-3 font-medium hidden sm:table-cell">Sent</th>
                  <th className="px-6 py-3 font-medium hidden sm:table-cell">Response</th>
                </tr>
              </thead>
              <tbody>
                {report.brokers.map((b) => (
                  <tr
                    key={b.broker_id}
                    className="border-b border-gray-50 dark:border-gray-800/50 hover:bg-gray-50 dark:hover:bg-gray-800/30"
                  >
                    <td className="px-6 py-2.5 font-medium text-gray-900 dark:text-white">
                      {b.broker_name}
                    </td>
                    <td className="px-6 py-2.5">
                      <StatusBadge status={b.status} />
                    </td>
                    <td className="px-6 py-2.5 text-gray-500 dark:text-gray-400 hidden sm:table-cell">
                      {b.sent_at ? new Date(b.sent_at).toLocaleDateString() : "-"}
                    </td>
                    <td className="px-6 py-2.5 text-gray-500 dark:text-gray-400 hidden sm:table-cell">
                      {b.response_at ? new Date(b.response_at).toLocaleDateString() : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Empty State */}
      {report.brokers.length === 0 && (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-12 text-center">
          <Shield className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            No requests yet
          </h3>
          <p className="text-gray-500 dark:text-gray-400 max-w-sm mx-auto">
            Start by scanning for your data on the Scan page, then send removal requests to data brokers.
          </p>
        </div>
      )}
    </div>
  );
}
