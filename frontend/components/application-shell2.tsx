"use client";

// Adapted from @shadcnblocks/application-shell2 for the Quasar exercise workspace.
import * as React from "react";
import {
  ChevronRight, ChevronsUpDown, CircleHelp, CloudRain, ExternalLink,
  FileChartColumn, Layers3, Map, MapPin, Radar, ShieldCheck, Waves,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent,
  SidebarGroupLabel, SidebarHeader, SidebarInset, SidebarMenu, SidebarMenuButton,
  SidebarMenuItem, SidebarMenuSub, SidebarMenuSubButton, SidebarMenuSubItem,
  SidebarProvider, SidebarRail, SidebarTrigger, useSidebar,
} from "@/components/ui/sidebar";

type NavItem = {
  label: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  href: string;
  children?: { label: string; href: string }[];
};
const navGroups = [
  { title: "Workspace", items: [
    { label: "Map overview", icon: Map, href: "#map-overview" },
    { label: "Exercise sites", icon: MapPin, href: "#exercise-sites" },
    { label: "Forecast & sources", icon: CloudRain, href: "#data-sources" },
    { label: "Reports & exports", icon: FileChartColumn, href: "#reports" },
  ] },
  { title: "Resources", items: [
    { label: "Exercise guide", icon: CircleHelp, href: "#exercise-guide", children: [
      { label: "Reading the map", href: "#exercise-guide" },
      { label: "Understanding a score", href: "#site-details" },
    ] },
    { label: "Official NWS guidance", icon: ShieldCheck, href: "https://www.weather.gov/mfl/" },
  ] },
];

function NavMenuItem({ item, active, onNavigate }: {
  item: NavItem; active: string; onNavigate: (href: string) => void;
}) {
  const { setOpenMobile } = useSidebar();
  const Icon = item.icon;
  const navigate = (href: string) => { onNavigate(href); setOpenMobile(false); };
  const isActive = active === item.href;
  if (!item.children) return (
    <SidebarMenuItem>
      <SidebarMenuButton asChild isActive={isActive} tooltip={item.label}>
        <a href={item.href} onClick={() => navigate(item.href)}
          aria-current={isActive ? "location" : undefined}
          {...(item.href.startsWith("https:") ? { target: "_blank", rel: "noopener noreferrer" } : {})}>
          <Icon className="size-4" /><span>{item.label}</span>
          {item.href.startsWith("https:") && <ExternalLink className="ml-auto size-3 opacity-50" />}
        </a>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );
  return (
    <Collapsible asChild defaultOpen className="group/collapsible">
      <SidebarMenuItem>
        <CollapsibleTrigger asChild>
          <SidebarMenuButton isActive={isActive} tooltip={item.label}>
            <Icon className="size-4" /><span>{item.label}</span>
            <ChevronRight className="ml-auto size-4 transition-transform group-data-[state=open]/collapsible:rotate-90" />
          </SidebarMenuButton>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <SidebarMenuSub>
            {item.children.map(child => (
              <SidebarMenuSubItem key={child.href}>
                <SidebarMenuSubButton asChild isActive={active === child.href}>
                  <a href={child.href} onClick={() => navigate(child.href)}>{child.label}</a>
                </SidebarMenuSubButton>
              </SidebarMenuSubItem>
            ))}
          </SidebarMenuSub>
        </CollapsibleContent>
      </SidebarMenuItem>
    </Collapsible>
  );
}

function AppSidebar() {
  const [active, setActive] = React.useState(window.location.hash || "#map-overview");
  React.useEffect(() => {
    const update = () => setActive(window.location.hash || "#map-overview");
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return (
    <Sidebar variant="inset" collapsible="icon" aria-label="Quasar navigation">
      <SidebarHeader>
        <div className="flex items-center gap-2 group-data-[collapsible=icon]:flex-col">
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton asChild size="lg" tooltip="Quasar · Miami-Dade">
                <a href="#map-overview">
                  <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground"><Waves className="size-5" /></div>
                  <div className="flex flex-col gap-0.5 leading-none"><span className="font-semibold tracking-tight">Quasar</span><span className="text-xs text-muted-foreground">Flood intelligence</span></div>
                </a>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
          <SidebarTrigger className="ml-auto group-data-[collapsible=icon]:ml-0" />
        </div>
      </SidebarHeader>
      <SidebarContent className="overflow-hidden">
        <ScrollArea className="min-h-0 flex-1">
          {navGroups.map(group => (
            <SidebarGroup key={group.title}>
              <SidebarGroupLabel>{group.title}</SidebarGroupLabel>
              <SidebarGroupContent><SidebarMenu>
                {group.items.map(item => <NavMenuItem key={item.label} item={item} active={active} onNavigate={href => { if (href.startsWith("#")) setActive(href); }} />)}
              </SidebarMenu></SidebarGroupContent>
            </SidebarGroup>
          ))}
          <div className="mx-3 mt-8 rounded-xl border border-sidebar-border p-3 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
            <Radar className="mb-2 size-4 text-primary" /><p className="font-medium text-sidebar-foreground">One county. A clearer picture.</p>
            <p className="mt-2 leading-relaxed">Explore how fictional sites respond to changing rainfall.</p>
          </div>
        </ScrollArea>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu><SidebarMenuItem>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <SidebarMenuButton size="lg" tooltip="Exercise workspace" className="data-[state=open]:bg-sidebar-accent">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-sidebar-border bg-background"><Layers3 className="size-4" /></div>
                <div className="grid flex-1 text-left text-sm leading-tight"><span className="font-medium">Miami-Dade County</span><span className="text-xs text-muted-foreground">Datathon exercise</span></div>
                <ChevronsUpDown className="ml-auto size-4" />
              </SidebarMenuButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" side="top" className="w-64">
              <DropdownMenuLabel>Exercise workspace · FIPS 12086</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild><a href="#data-sources"><CloudRain />Forecast & source status</a></DropdownMenuItem>
              <DropdownMenuItem asChild><a href="https://www.weather.gov/mfl/" target="_blank" rel="noopener noreferrer"><ShieldCheck />Official NWS guidance<ExternalLink /></a></DropdownMenuItem>
              <DropdownMenuSeparator /><p className="px-2 py-1.5 text-xs text-muted-foreground">Fictional sites. No notifications are sent.</p>
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarMenuItem></SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}

export function ApplicationShell2({ className, children }: React.PropsWithChildren<{ className?: string }>) {
  return (
    <SidebarProvider className={cn(className)}>
      <a href="#map-overview" className="skip-link">Skip to map workspace</a>
      <AppSidebar />
      <SidebarInset className="min-w-0 overflow-clip border border-border shadow-sm">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4 md:hidden">
          <SidebarTrigger /><Separator orientation="vertical" className="mx-2 data-[orientation=vertical]:h-4" />
          <Waves className="size-4 text-primary" /><span className="text-sm font-semibold">Quasar</span><span className="ml-auto text-xs text-muted-foreground">Miami-Dade</span>
        </header>
        {children}
      </SidebarInset>
    </SidebarProvider>
  );
}
