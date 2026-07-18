import symbolUrl from "../../assets/starbridge-symbol.svg";

interface BrandProps {
  compact?: boolean;
}

export function Brand({ compact = false }: BrandProps) {
  return (
    <div className={`brand-lockup${compact ? " brand-lockup-compact" : ""}`}>
      <img src={symbolUrl} alt="" aria-hidden="true" />
      <span>
        <strong>StarBridge</strong>
        {!compact ? <small>本地创意工作台</small> : null}
      </span>
    </div>
  );
}
