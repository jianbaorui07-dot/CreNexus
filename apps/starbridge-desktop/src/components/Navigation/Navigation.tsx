import { NAVIGATION_ITEMS, type PageId } from "../../app/routes";

function NavigationIcon({ page }: { page: PageId }) {
  const paths: Record<PageId, React.ReactNode> = {
    home: <><path d="M3 10.5 12 3l9 7.5" /><path d="M5.5 9.5V21h13V9.5" /></>,
    projects: <><path d="M3 7h7l2 2h9v11H3z" /><path d="M3 7V4h7l2 3" /></>,
    workflows: <><circle cx="6" cy="6" r="2" /><circle cx="18" cy="18" r="2" /><path d="M8 6h5a3 3 0 0 1 3 3v7M6 8v10h10" /></>,
    vectorization: <><path d="m4 18 5-5 4 4 3-3 4 4" /><rect x="3" y="4" width="18" height="16" rx="2" /></>,
    "ai-generation": <><path d="m12 3 1.4 4.1L17.5 8.5l-4.1 1.4L12 14l-1.4-4.1-4.1-1.4 4.1-1.4z" /><path d="m18 14 .8 2.2L21 17l-2.2.8L18 20l-.8-2.2L15 17l2.2-.8z" /></>,
    "photoshop-production": <><rect x="4" y="4" width="16" height="16" rx="3" /><path d="M8 16V8h3.2a2.7 2.7 0 0 1 0 5.4H8M15 11.5c.7-.6 2.3-.6 2.8.2.6 1-2.8.6-2.8 2.5 0 1.3 2 1.4 3 .6" /></>,
    batch: <><rect x="4" y="4" width="12" height="12" rx="2" /><path d="M8 20h10a2 2 0 0 0 2-2V8" /></>,
    integrations: <><path d="M8 8h8v8H8z" /><path d="M3 12h5m8 0h5M12 3v5m0 8v5" /></>,
    tasks: <><path d="M7 4h10M7 9h10M7 14h7M7 19h5" /><path d="M3 4h.01M3 9h.01M3 14h.01M3 19h.01" /></>,
    delivery: <><path d="M4 5h16v14H4z" /><path d="m8 12 3 3 5-6" /></>,
    license: <><path d="M12 3 5 6v5c0 4.6 2.8 8 7 10 4.2-2 7-5.4 7-10V6z" /><path d="m9 12 2 2 4-5" /></>,
    diagnostics: <><circle cx="12" cy="12" r="3" /><path d="M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M19 5l-2 2M7 17l-2 2" /></>,
    "job-detail": <><path d="M6 3h9l3 3v15H6z" /><path d="M9 11h6M9 15h6" /></>,
    "legacy-vectorization": <><path d="M4 4h16v16H4z" /><path d="m7 16 3-4 3 3 4-5" /></>,
  };
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      {paths[page]}
    </svg>
  );
}

interface NavigationProps {
  currentPage: PageId;
  onNavigate: (page: PageId) => void;
}

export function Navigation({ currentPage, onNavigate }: NavigationProps) {
  return (
    <nav className="side-navigation" aria-label="主要导航">
      {NAVIGATION_ITEMS.map((item) => (
        <button
          type="button"
          key={item.id}
          className={currentPage === item.id ? "is-active" : undefined}
          aria-current={currentPage === item.id ? "page" : undefined}
          onClick={() => onNavigate(item.id)}
        >
          <NavigationIcon page={item.id} />
          <span>{item.label}</span>
          {item.id === "batch" ? <span className="nav-lock">规划中</span> : null}
        </button>
      ))}
    </nav>
  );
}
