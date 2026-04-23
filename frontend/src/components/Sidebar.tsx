import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import styles from "./Sidebar.module.css";

// ── Inline SVG icons (20×20, consistent 1.5px stroke) ─────────────────────────

function IconOverview() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="18" height="18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="2" width="7" height="7" rx="1.5"/>
      <rect x="11" y="2" width="7" height="7" rx="1.5"/>
      <rect x="2" y="11" width="7" height="7" rx="1.5"/>
      <rect x="11" y="11" width="7" height="7" rx="1.5"/>
    </svg>
  );
}

function IconPortfolio() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="18" height="18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 14h3v4H3zM8.5 9h3v9h-3zM14 4h3v14h-3z"/>
    </svg>
  );
}

function IconTrade() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="18" height="18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 6h13M12 3l3 3-3 3"/>
      <path d="M18 14H5m8 3l-3-3 3-3"/>
    </svg>
  );
}

function IconMarket() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="18" height="18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="10" cy="10" r="8"/>
      <path d="M2 10h16M10 2a12 12 0 0 1 3 8 12 12 0 0 1-3 8M10 2a12 12 0 0 0-3 8 12 12 0 0 0 3 8"/>
    </svg>
  );
}

function IconImport() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="18" height="18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 2v11M7 10l3 3 3-3"/>
      <path d="M3 15h14"/>
    </svg>
  );
}

function IconAssistant() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="18" height="18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 10a8 8 0 0 1-8 8H4l-2 2V10a8 8 0 1 1 16 0z"/>
      <path d="M6.5 10h.01M10 10h.01M13.5 10h.01" strokeWidth="2.2" strokeLinecap="round"/>
    </svg>
  );
}

function IconActivity() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="18" height="18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="1,11 5,11 7,5 10,16 13,8.5 15,11 19,11"/>
    </svg>
  );
}

function IconIntelligence() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="18" height="18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="10" cy="10" r="8"/>
      <path d="M10 6v4l3 2"/>
      <path d="M6 3.5L4 2M14 3.5L16 2"/>
    </svg>
  );
}


function IconLogout() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="18" height="18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 17H3a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h4M13 14l4-4-4-4M17 10H7"/>
    </svg>
  );
}

function IconChevron() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="14" height="14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M13 5l-5 5 5 5"/>
    </svg>
  );
}

// ── Brand logo icon ────────────────────────────────────────────────────────────

function BrandIcon() {
  return (
    <svg viewBox="0 0 28 28" fill="none" width="26" height="26">
      <rect x="1" y="1" width="26" height="26" rx="7" fill="var(--accent)" opacity="0.15"/>
      <rect x="1" y="1" width="26" height="26" rx="7" stroke="var(--accent)" strokeWidth="1.2" opacity="0.4"/>
      <path d="M7 20L11 11L14 16L17 9L21 20" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
      <circle cx="21" cy="9" r="2" fill="var(--positive)" opacity="0.9"/>
    </svg>
  );
}

// ── Nav config ─────────────────────────────────────────────────────────────────

const NAV_PRIMARY = [
  { path: "/overview",      label: "Overview",      Icon: IconOverview },
  { path: "/portfolio",     label: "Portfolio",     Icon: IconPortfolio },
  { path: "/trade",         label: "Trade",         Icon: IconTrade },
  { path: "/market",        label: "Market",        Icon: IconMarket },
  { path: "/import",        label: "Import",        Icon: IconImport },
  { path: "/assistant",     label: "AI Assistant",  Icon: IconAssistant },
  { path: "/intelligence",  label: "Intelligence",  Icon: IconIntelligence },
  { path: "/activity",      label: "Activity",      Icon: IconActivity },
];

// ── Component ──────────────────────────────────────────────────────────────────

interface Props {
  collapsed: boolean;
  onToggle: () => void;
}

export default function Sidebar({ collapsed, onToggle }: Props) {
  const { logout } = useAuth();

  return (
    <nav
      className={`${styles.sidebar} ${collapsed ? styles.collapsed : ""}`}
      aria-label="Main navigation"
    >
      {/* Brand */}
      <div className={styles.brand}>
        <div className={styles.brandIcon}>
          <BrandIcon />
        </div>
        <span className={styles.brandLabel}>PortfolioAI</span>
      </div>

      {/* Primary nav */}
      <div className={styles.nav}>
        <span className={styles.navGroup}>Navigation</span>
        {NAV_PRIMARY.map(({ path, label, Icon }) => (
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
            {path === "/assistant" && (
              <span className={styles.badge}>AI</span>
            )}
            {path === "/intelligence" && (
              <span className={styles.badge}>Live</span>
            )}
          </NavLink>
        ))}
      </div>

      {/* Footer */}
      <div className={styles.footer}>
        <button
          className={`${styles.item} ${styles.logoutItem}`}
          onClick={logout}
          title={collapsed ? "Sign out" : undefined}
        >
          <span className={styles.itemIcon}><IconLogout /></span>
          <span className={styles.itemLabel}>Sign out</span>
        </button>

        <button
          className={styles.collapseBtn}
          onClick={onToggle}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <span className={`${styles.chevron} ${collapsed ? styles.chevronFlipped : ""}`}>
            <IconChevron />
          </span>
        </button>
      </div>
    </nav>
  );
}
