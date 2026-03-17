import { useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import styles from "./AppShell.module.css";

export default function AppShell() {
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem("sidebar-collapsed") === "1"; }
    catch { return false; }
  });

  function toggle() {
    setCollapsed((c) => {
      const next = !c;
      try { localStorage.setItem("sidebar-collapsed", next ? "1" : "0"); }
      catch { /* ignore */ }
      return next;
    });
  }

  return (
    <div className={`${styles.shell} ${collapsed ? styles.collapsed : ""}`}>
      <Sidebar collapsed={collapsed} onToggle={toggle} />

      <div className={styles.body}>
        <TopBar />
        <main className={styles.main}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
