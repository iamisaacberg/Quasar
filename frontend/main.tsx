import { createRoot } from "react-dom/client";
import { ApplicationShell2 } from "@/components/application-shell2";
import { QuasarDashboard } from "@/dashboard";
import "./styles.css";
import polygonClipping from "polygon-clipping";

(window as unknown as { QuasarSpatial: { configureGeometry: (value: typeof polygonClipping) => void } }).QuasarSpatial.configureGeometry(polygonClipping);

createRoot(document.getElementById("root")!).render(
  <ApplicationShell2 className="quasar-shell"><QuasarDashboard /></ApplicationShell2>,
);
