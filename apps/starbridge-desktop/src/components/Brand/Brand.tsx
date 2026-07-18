import symbolUrl from "../../assets/crenexus-software-icon.png";

interface BrandProps {
  compact?: boolean;
}

export function Brand({ compact = false }: BrandProps) {
  return (
    <div className={`brand-lockup${compact ? " brand-lockup-compact" : ""}`}>
      <img src={symbolUrl} alt="" aria-hidden="true" />
      <span>
        <strong>CreNexus</strong>
        {!compact ? <><small>STARBRIDGE</small><em>LOCAL CREATIVE OS</em></> : null}
      </span>
    </div>
  );
}
