import { ArrowUpRight, ArrowDownLeft } from "lucide-react";

interface EmailItem {
  id: number;
  direction: "inbound" | "outbound";
  from_address: string;
  to_address: string;
  subject: string;
  body_text: string;
  received_at: string | null;
}

export default function EmailThread({ emails }: { emails: EmailItem[] }) {
  if (emails.length === 0) return null;

  return (
    <div className="space-y-3">
      {emails.map((email) => (
        <div
          key={email.id}
          className={`rounded-lg border p-4 ${
            email.direction === "outbound"
              ? "border-blue-200 bg-blue-50"
              : "border-green-200 bg-green-50"
          }`}
        >
          <div className="flex items-center gap-2 mb-2">
            {email.direction === "outbound" ? (
              <ArrowUpRight className="w-3.5 h-3.5 text-blue-500" />
            ) : (
              <ArrowDownLeft className="w-3.5 h-3.5 text-green-500" />
            )}
            <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
              {email.direction === "outbound" ? "Sent" : "Received"}
            </span>
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {email.received_at ? new Date(email.received_at).toLocaleString() : ""}
            </span>
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400 space-y-0.5 mb-2">
            <p>From: {email.from_address}</p>
            <p>To: {email.to_address}</p>
            <p>Subject: {email.subject}</p>
          </div>
          <pre className="text-sm whitespace-pre-wrap text-gray-800 dark:text-gray-200 max-h-40 overflow-y-auto">
            {email.body_text}
          </pre>
        </div>
      ))}
    </div>
  );
}
