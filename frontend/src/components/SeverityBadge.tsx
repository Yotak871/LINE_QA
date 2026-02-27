import clsx from "clsx";
import type { Severity } from "@/lib/types";

const MAP = {
  critical: { label: "Critical", cls: "bg-red-50 text-[#e02000] border-red-200" },
  major:    { label: "Major",    cls: "bg-orange-50 text-orange-700 border-orange-200" },
  minor:    { label: "Minor",    cls: "bg-yellow-50 text-yellow-700 border-yellow-200" },
};

export default function SeverityBadge({ severity }: { severity: Severity }) {
  const { label, cls } = MAP[severity] ?? MAP.minor;
  return (
    <span className={clsx("text-xs font-medium px-2 py-0.5 rounded-full border", cls)}>
      {label}
    </span>
  );
}
