export default function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    created: "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300",
    sent: "bg-blue-100 text-blue-700",
    acknowledged: "bg-indigo-100 text-indigo-700",
    completed: "bg-green-100 text-green-700",
    refused: "bg-red-100 text-red-700",
    overdue: "bg-orange-100 text-orange-700",
    escalated: "bg-red-100 text-red-700",
    manual_action_needed: "bg-yellow-100 text-yellow-700",
  };

  return (
    <span role="status" className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${styles[status] || "bg-gray-100 dark:bg-gray-700"}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}
