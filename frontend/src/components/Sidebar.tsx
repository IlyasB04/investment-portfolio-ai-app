import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import styles from "./Sidebar.module.css";

// ── Inline SVG icons ─────────────────────────────────────────────────────────

function IconOverview() {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" width="16" height="16">
      <rect x="1" y="1" width="6" height="6" rx="1.5"/>
      <rect x="9" y="1" width="6" height="6" rx="1.5"/>
      <rect x="1" y="9" width="6" height="6" rx="1.5"/>
      <rect x="9" y="9" width="6" height="6" rx="1.5"/>
    </svg>
  );
}

function IconPortfolio() {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" width="16" height="16">
      <path d="M2 11h2.5v3H2zM6.75 7h2.5v7h-2.5zM11.5 3H14v11h-2.5z"/>
    </svg>
  );
}

function IconTrade() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 5h11M9 2l3 3-3 3M15 11H4m8 3l-3-3 3-3"/>
    </svg>
  );
}

function IconImport() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 1v9M5 7l3 3 3-3"/>
      <path d="M2 12h12"/>
    </svg>
  );
}

function IconAssistant() {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" width="16" height="16">
      <path d="M8 1L9.8 5.4 14.5 5.9 11.1 9 12.1 13.5 8 11.1 3.9 13.5 4.9 9 1.5 5.9 6.2 5.4z"/>
    </svg>
  );
}

function IconActivity() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="1,9 4,9 5.5,5 7.5,12 9.5,7.5 11,9 15,9"/>
    </svg>
  );
}

function IconLogout() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 14H2V2h4M11 11l3-3-3-3M14 8H6"/>
    </svg>
  );
}

// ── Nav items config ──────────────────────────────────────────────────────────

const NAV = [
  { path: "/overview",   label: "Overview",     Icon: IconOverview },
  { path: "/portfolio",  label: "Portfolio",    Icon: IconPortfolio },
  { path: "/trade",      label: "Trade",        Icon: IconTrade },
  { path: "/import",     label: "Import",       Icon: IconImport },
  { path: "/assistant",  label: "AI Assistant", Icon: IconAssistant },
  { path: "/activity",   label: "Activity",     Icon: IconActivity },
];

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  collapsed: boolean;
  onToggle: () => void;
}

export default function Sidebar({ collapsed, onToggle }: Props) {
  const { logout } = useAuth();

  return (
    <nav className={`${styles.sidebar} ${collapsed ? styles.collapsed : ""}`} aria-label="Main navigation">
      {/* Brand */}
      <div className={styles.brand}>
        <span className={styles.brandIcon}>◈</span>
        <span className={styles.brandLabel}>Portfolio</span>
      </div>

      {/* Nav items */}
      <div className={styles.nav}>
        {NAV.map(({ path, label, Icon }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              `${styles.item} ${isActive ? styles.active : ""}`
            }
            title={collapsed ? label : undefined}
          >
            <span className={styles.itemIcon}><Icon /></span>
            <span className={styles.itemLabel}>{label}</span>
          </NavLink>
        ))}
      </div>

      {/* Footer */}
      <div className={styles.footer}>
        <button
          className={styles.item}
          onClick={logout}
          title={collapsed ? "Sign out" : undefined}
        >
          <span className={styles.itemIcon}><IconLogout /></span>
          <span className={styles.itemLabel}>Sign out</span>
        </button>

        <button className={styles.collapseBtn} onClick={onToggle} title={collapsed ? "Expand" : "Collapse"}>
          <svg
            viewBox="0 0 16 16"
            width="14"
            height="14"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            style={{ transform: collapsed ? "rotate(180deg)" : "none", transition: "transform 0.22s" }}
          >
            <path d="M10 3L5 8l5 5"/>
          </svg>
        </button>
      </div>
    </nav>
  );
}
