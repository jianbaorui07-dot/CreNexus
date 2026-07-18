import type { LicenseEdition } from "../../types/api";

const EDITIONS: Record<LicenseEdition, string> = {
  community: "Community",
  pro: "Pro",
  enterprise: "Enterprise",
};

export function EditionBadge({ edition }: { edition: LicenseEdition }) {
  return <span className={`edition-badge edition-${edition}`}>{EDITIONS[edition]}</span>;
}
