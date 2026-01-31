import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Check, X, Edit } from "lucide-react";
import { cn } from "@/lib/utils";

interface InlineApprovalActionsProps {
  approvalId: string;
  expanded?: boolean;
  className?: string;
}

export function InlineApprovalActions({
  approvalId,
  expanded,
  className,
}: InlineApprovalActionsProps) {
  const [status, setStatus] = useState<
    "pending" | "approved" | "rejected" | "loading"
  >("pending");

  const handleApprove = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setStatus("loading");
    try {
      await fetch(`/api/approvals/${approvalId}/approve`, { method: "POST" });
      setStatus("approved");
    } catch {
      setStatus("pending");
    }
  };

  const handleReject = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setStatus("loading");
    try {
      await fetch(`/api/approvals/${approvalId}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: null }),
      });
      setStatus("rejected");
    } catch {
      setStatus("pending");
    }
  };

  if (status === "approved") {
    return (
      <span className="text-success text-sm font-medium flex items-center gap-1">
        <Check className="w-4 h-4" />
        Approved
      </span>
    );
  }
  if (status === "rejected") {
    return (
      <span className="text-error text-sm font-medium flex items-center gap-1">
        <X className="w-4 h-4" />
        Rejected
      </span>
    );
  }

  return (
    <div
      className={cn("flex gap-2", className)}
      onClick={(e) => e.stopPropagation()}
    >
      <Button
        variant="outline"
        size="sm"
        onClick={handleApprove}
        disabled={status === "loading"}
        className="gap-1 text-success border-success/30 hover:bg-success/10 hover:border-success/50"
      >
        <Check className="w-3.5 h-3.5" />
        {expanded && "Approve"}
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={handleReject}
        disabled={status === "loading"}
        className="gap-1 text-error border-error/30 hover:bg-error/10 hover:border-error/50"
      >
        <X className="w-3.5 h-3.5" />
        {expanded && "Reject"}
      </Button>
      {expanded && (
        <Button variant="outline" size="sm" className="gap-1">
          <Edit className="w-3.5 h-3.5" />
          Modify
        </Button>
      )}
    </div>
  );
}
