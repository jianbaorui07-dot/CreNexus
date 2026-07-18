import { NAVIGATION_ITEMS, type PageId } from "../../app/routes";

interface NavigationProps {
  currentPage: PageId;
  onNavigate: (page: PageId) => void;
}

export function Navigation({ currentPage, onNavigate }: NavigationProps) {
  return (
    <nav className="side-navigation" aria-label="主要导航">
      {NAVIGATION_ITEMS.map((item, index) => (
        <button
          type="button"
          key={item.id}
          className={currentPage === item.id ? "is-active" : undefined}
          aria-label={item.label}
          aria-current={currentPage === item.id ? "page" : undefined}
          onClick={() => onNavigate(item.id)}
        >
          <span className="nav-index">{String(index + 1).padStart(2, "0")}</span>
          <span className="nav-copy"><span>{item.label}</span><small>{item.caption}</small></span>
          {item.id === "batch" ? <span className="nav-lock">规划中</span> : null}
        </button>
      ))}
    </nav>
  );
}
