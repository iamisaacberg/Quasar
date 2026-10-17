import { createRoot } from "react-dom/client";
import { ApplicationShell2 } from "@/components/application-shell2";
import { QuasarDashboard } from "@/dashboard";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <ApplicationShell2 className="quasar-shell"><QuasarDashboard /></ApplicationShell2>,
);
