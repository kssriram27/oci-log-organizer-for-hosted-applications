import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  Clipboard,
  Download,
  FileArchive,
  FolderOpen,
  Home,
  Layers,
  ListChecks,
  Loader2,
  Maximize2,
  Minimize2,
  Paintbrush,
  Play,
  RefreshCw,
  Save,
  Search,
  ServerCog,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Radio,
  Terminal,
  Trash2,
  X,
} from "lucide-react";
import { ChangeEvent, ReactNode, UIEvent, useEffect, useMemo, useRef, useState } from "react";

type ProviderMode = "auto" | "sdk" | "cli";
type OutputFormat = "text" | "jsonl";
type RevisionScope = "workload" | "global";
type Page = "home" | "search" | "settings";
type ThemeStyleId = "classic" | "accent-light" | "accent-dark";
type ThemeId =
  | "frosted-light"
  | "graphite-dark"
  | "oracle-redwood"
  | "emerald-console"
  | "indigo-glass"
  | "accent-light-azure"
  | "accent-light-redwood"
  | "accent-light-emerald"
  | "accent-light-amber"
  | "accent-dark-azure"
  | "accent-dark-redwood"
  | "accent-dark-emerald"
  | "accent-dark-amber";
type TimePreset = "custom" | "5" | "15" | "60" | "180" | "360" | "live";

type OciContextHistory = {
  region_options: string[];
  compartment_id_options: string[];
  selected_log_group_id: string;
  selected_log_group_name: string;
};

type AppSettings = {
  config_file: string;
  profile: string;
  region: string;
  compartment_id: string;
  region_options: string[];
  compartment_id_options: string[];
  oci_context_history: Record<string, OciContextHistory>;
  provider_mode: ProviderMode;
  output_format: OutputFormat;
  sort_by_timestamp: boolean;
  merge_partial_oci_logs: boolean;
  remove_timestamp_from_message: boolean;
  filter_latest_revision: boolean;
  latest_revision_scope: RevisionScope;
  default_time_minutes: number;
  selected_log_group_id: string;
  selected_log_group_name: string;
  include_raw_in_zip: boolean;
  theme: ThemeId;
  theme_style: ThemeStyleId;
  theme_selection_by_style: Record<ThemeStyleId, ThemeId>;
  sidebar_collapsed: boolean;
};

type LogGroup = {
  id: string;
  name: string;
  lifecycle_state?: string;
};

type LogItem = {
  id: string;
  name: string;
  log_type?: string;
  lifecycle_state?: string;
  is_enabled?: boolean;
};

type FetchResult = {
  status: "success" | "error";
  result_id?: string;
  log_id: string;
  log_name: string;
  provider?: string;
  output_format?: OutputFormat;
  provider_errors?: Array<Record<string, unknown>>;
  stats?: {
    raw_count: number;
    filtered_count: number;
    merged_count: number;
    output_count: number;
    live_added_count?: number | null;
    selections: Record<string, Record<string, unknown>>;
    deployment_candidates?: Record<string, Array<Record<string, unknown>>>;
  };
  message?: string;
};

type OciCheck = {
  sdk_ready: boolean;
  sdk_error: string;
  cli_ready: boolean;
  cli_path: string;
  provider_mode: string;
  remote_ok: boolean | null;
  remote_error: string;
  log_groups?: LogGroup[];
  provider?: string;
};

type OciConfigProfile = {
  name: string;
  region: string;
};

type TerminalPage = {
  lines: string[];
  total: number;
  offset: number;
  limit: number;
};

type RevisionChange = {
  result_id: string;
  log_name: string;
  changes: Array<{
    workload: string;
    current: Record<string, unknown>;
    candidate: Record<string, unknown>;
  }>;
};

type DeploymentCandidate = Record<string, unknown> & { workload: string };

const ENTER_NEW_VALUE = "__enter-new-value__";

const defaultSettings: AppSettings = {
  config_file: "~/.oci/config",
  profile: "DEFAULT",
  region: "",
  compartment_id: "",
  region_options: [],
  compartment_id_options: [],
  oci_context_history: {},
  provider_mode: "auto",
  output_format: "text",
  sort_by_timestamp: true,
  merge_partial_oci_logs: true,
  remove_timestamp_from_message: true,
  filter_latest_revision: true,
  latest_revision_scope: "workload",
  default_time_minutes: 5,
  selected_log_group_id: "",
  selected_log_group_name: "",
  include_raw_in_zip: false,
  theme: "frosted-light",
  theme_style: "classic",
  theme_selection_by_style: {
    classic: "frosted-light",
    "accent-light": "accent-light-azure",
    "accent-dark": "accent-dark-azure",
  },
  sidebar_collapsed: false,
};

const themeStyles: Array<{ id: ThemeStyleId; name: string; description: string }> = [
  { id: "classic", name: "Classic themes", description: "Original full palettes" },
  { id: "accent-light", name: "Accent Light", description: "Neutral light workspace" },
  { id: "accent-dark", name: "Accent Dark", description: "Neutral dark workspace" },
];

const defaultThemeSelections: Record<ThemeStyleId, ThemeId> = {
  classic: "frosted-light",
  "accent-light": "accent-light-azure",
  "accent-dark": "accent-dark-azure",
};

const themes: Array<{ id: ThemeId; style: ThemeStyleId; name: string; description: string }> = [
  { id: "frosted-light", style: "classic", name: "Frosted Light", description: "Soft glass, bright work surface" },
  { id: "graphite-dark", style: "classic", name: "Graphite Dark", description: "Deep neutral console" },
  { id: "oracle-redwood", style: "classic", name: "Oracle Redwood", description: "Warm redwood accent" },
  { id: "emerald-console", style: "classic", name: "Emerald Console", description: "Developer green signal" },
  { id: "indigo-glass", style: "classic", name: "Indigo Glass", description: "Cool blue glass system" },
  { id: "accent-light-azure", style: "accent-light", name: "Azure", description: "Neutral light with azure accents" },
  { id: "accent-light-redwood", style: "accent-light", name: "Redwood", description: "Neutral light with redwood accents" },
  { id: "accent-light-emerald", style: "accent-light", name: "Emerald", description: "Neutral light with emerald accents" },
  { id: "accent-light-amber", style: "accent-light", name: "Amber", description: "Neutral light with amber accents" },
  { id: "accent-dark-azure", style: "accent-dark", name: "Azure", description: "Neutral dark with azure accents" },
  { id: "accent-dark-redwood", style: "accent-dark", name: "Redwood", description: "Neutral dark with redwood accents" },
  { id: "accent-dark-emerald", style: "accent-dark", name: "Emerald", description: "Neutral dark with emerald accents" },
  { id: "accent-dark-amber", style: "accent-dark", name: "Amber", description: "Neutral dark with amber accents" },
];

const timePresets: Array<{ value: TimePreset; label: string; minutes?: number }> = [
  { value: "5", label: "Last 5 mins", minutes: 5 },
  { value: "15", label: "Last 15 mins", minutes: 15 },
  { value: "60", label: "Last 1 hour", minutes: 60 },
  { value: "180", label: "Last 3 hours", minutes: 180 },
  { value: "360", label: "Last 6 hours", minutes: 360 },
  { value: "live", label: "Live Logs", minutes: 5 },
  { value: "custom", label: "Custom" },
];
const TERMINAL_CHUNK_SIZE = 500;

function utcInputValue(date: Date) {
  return date.toISOString().slice(0, 16);
}

function toIsoUtc(value: string) {
  return `${value}:00Z`;
}

function defaultTimeRange(minutes: number) {
  const end = new Date();
  const start = new Date(end.getTime() - minutes * 60_000);
  return {
    start: utcInputValue(start),
    end: utcInputValue(end),
  };
}

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {}),
    },
    ...options,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      // Keep the status text.
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  return response.json();
}

function uniqueOptions(values: Array<string | undefined>): string[] {
  return Array.from(new Set(values.map((value) => value?.trim() ?? "").filter(Boolean)));
}

function ociContextKey(configFile: string, profile: string): string {
  return `${configFile.trim() || "~/.oci/config"}\n${profile.trim() || "DEFAULT"}`;
}

export function App() {
  const [settings, setSettings] = useState<AppSettings>(defaultSettings);
  const [settingsReady, setSettingsReady] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [page, setPage] = useState<Page>("home");
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    oci: true,
    formatter: true,
    appearance: true,
    diagnostics: true,
  });
  const [logGroups, setLogGroups] = useState<LogGroup[]>([]);
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [logsLoadedFor, setLogsLoadedFor] = useState("");
  const [selectedLogs, setSelectedLogs] = useState<string[]>([]);
  const initialRange = defaultTimeRange(5);
  const [startTime, setStartTime] = useState(initialRange.start);
  const [endTime, setEndTime] = useState(initialRange.end);
  const [results, setResults] = useState<FetchResult[]>([]);
  const [activeLogId, setActiveLogId] = useState("");
  const [viewerSearch, setViewerSearch] = useState("");
  const [viewerLines, setViewerLines] = useState<string[]>([]);
  const [viewerTotal, setViewerTotal] = useState(0);
  const [viewerLoading, setViewerLoading] = useState(false);
  const [logFilter, setLogFilter] = useState("");
  const [timePreset, setTimePreset] = useState<TimePreset>("5");
  const [liveState, setLiveState] = useState<"off" | "running" | "paused">("off");
  const [revisionChanges, setRevisionChanges] = useState<RevisionChange[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [check, setCheck] = useState<OciCheck | null>(null);
  const [configProfiles, setConfigProfiles] = useState<OciConfigProfile[]>([]);
  const logLoadRequestId = useRef(0);
  const logLoadController = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function initialize() {
      try {
        const staleSession = sessionStorage.getItem("oci-log-organizer-session");
        if (staleSession) {
          await fetch(`/api/sessions/${staleSession}/close`, { method: "POST", keepalive: true }).catch(() => undefined);
        }
        const [loaded, created] = await Promise.all([
          api<Partial<AppSettings>>("/api/settings"),
          api<{ session_id: string }>("/api/sessions", { method: "POST" }),
        ]);
        if (cancelled) {
          return;
        }
        const merged = { ...defaultSettings, ...loaded } as AppSettings;
        setSettings(merged);
        setSessionId(created.session_id);
        sessionStorage.setItem("oci-log-organizer-session", created.session_id);
        const range = defaultTimeRange(5);
        setStartTime(range.start);
        setEndTime(range.end);
        setTimePreset("5");
        setSettingsReady(true);
        if (merged.compartment_id) {
          await runConnectionCheck(merged, true);
        }
      } catch (err) {
        if (!cancelled) {
          setError((err as Error).message);
          setSettingsReady(true);
        }
      }
    }

    void initialize();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!status) {
      return undefined;
    }

    const timer = window.setTimeout(() => setStatus(""), 3500);
    return () => window.clearTimeout(timer);
  }, [status]);

  useEffect(() => {
    if (!settingsReady || !settings.config_file.trim()) {
      setConfigProfiles([]);
      return undefined;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      void api<{ profiles: OciConfigProfile[] }>(
        `/api/oci/config-profiles?config_file=${encodeURIComponent(settings.config_file.trim())}`,
      )
        .then((payload) => {
          if (!cancelled) {
            setConfigProfiles(payload.profiles);
          }
        })
        .catch((err) => {
          if (!cancelled) {
            setConfigProfiles([]);
          }
        });
    }, 350);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [settings.config_file, settingsReady]);

  function reloadProfileOptions() {
    const configFile = settings.config_file.trim();
    if (!configFile) {
      return;
    }

    void api<{ profiles: OciConfigProfile[] }>(`/api/oci/config-profiles?config_file=${encodeURIComponent(configFile)}`)
      .then((payload) => setConfigProfiles(payload.profiles))
      .catch(() => setConfigProfiles([]));
  }

  useEffect(() => {
    if (!sessionId) {
      return undefined;
    }
    const closeSession = () => {
      navigator.sendBeacon(`/api/sessions/${sessionId}/close`);
    };
    const heartbeat = window.setInterval(() => {
      void fetch(`/api/sessions/${sessionId}/heartbeat`, { method: "POST", keepalive: true });
    }, 60_000);
    window.addEventListener("pagehide", closeSession);
    return () => {
      window.clearInterval(heartbeat);
      window.removeEventListener("pagehide", closeSession);
    };
  }, [sessionId]);

  const setupComplete = settingsReady && Boolean(settings.config_file && settings.profile && settings.compartment_id);
  const activeResult = useMemo(() => {
    if (!results.length) {
      return null;
    }
    return results.find((result) => result.result_id === activeLogId || result.log_id === activeLogId) ?? results[0];
  }, [activeLogId, results]);

  useEffect(() => {
    let cancelled = false;
    async function loadFirstPage() {
      if (!sessionId || !activeResult?.result_id) {
        setViewerLines([]);
        setViewerTotal(0);
        return;
      }
      setViewerLoading(true);
      try {
        const payload = await api<TerminalPage>(
          `/api/sessions/${sessionId}/results/${activeResult.result_id}/lines?offset=0&limit=${TERMINAL_CHUNK_SIZE}&query=${encodeURIComponent(viewerSearch)}`,
        );
        if (!cancelled) {
          setViewerLines(payload.lines);
          setViewerTotal(payload.total);
        }
      } catch (err) {
        if (!cancelled) {
          setError((err as Error).message);
        }
      } finally {
        if (!cancelled) {
          setViewerLoading(false);
        }
      }
    }
    void loadFirstPage();
    return () => {
      cancelled = true;
    };
  }, [activeResult?.result_id, sessionId, viewerSearch]);

  const displayedContent = viewerLines.join("\n\n");
  const terminalVisibleCount = viewerLines.length;
  const terminalHasMore = terminalVisibleCount < viewerTotal;

  const filteredLogs = useMemo(() => {
    const query = logFilter.trim().toLowerCase();
    if (!query) {
      return logs;
    }

    return logs.filter((log) => `${log.name} ${log.id} ${log.log_type ?? ""}`.toLowerCase().includes(query));
  }, [logFilter, logs]);

  const profileOptions = useMemo(
    () => uniqueOptions([settings.profile, ...configProfiles.map((profile) => profile.name)]),
    [configProfiles, settings.profile],
  );
  const regionOptions = useMemo(
    () => uniqueOptions([settings.region, ...settings.region_options, configProfiles.find((profile) => profile.name === settings.profile)?.region]),
    [configProfiles, settings.profile, settings.region, settings.region_options],
  );
  const compartmentOptions = useMemo(
    () => uniqueOptions([settings.compartment_id, ...settings.compartment_id_options]),
    [settings.compartment_id, settings.compartment_id_options],
  );

  function clearLoadedOciData() {
    logLoadRequestId.current += 1;
    logLoadController.current?.abort();
    logLoadController.current = null;
    setLogGroups([]);
    setLogs([]);
    setLogsLoadedFor("");
    setSelectedLogs([]);
    setLiveState("off");
    setCheck(null);
  }

  function patchSettings<T extends keyof AppSettings>(key: T, value: AppSettings[T]) {
    const changesOciContext = key === "config_file" || key === "profile" || key === "region" || key === "compartment_id";
    if (changesOciContext) {
      clearLoadedOciData();
    }
    setSettings((current) => ({
      ...current,
      [key]: value,
      ...(changesOciContext ? { selected_log_group_id: "", selected_log_group_name: "" } : {}),
    }));
  }

  function selectProfile(profile: string) {
    clearLoadedOciData();
    setSettings((current) => {
      const profileConfig = configProfiles.find((candidate) => candidate.name === profile);
      const key = ociContextKey(current.config_file, profile);
      const history = current.oci_context_history[key];
      const region = profileConfig?.region || history?.region_options[0] || "";
      return {
        ...current,
        profile,
        region,
        compartment_id: history?.compartment_id_options[0] || "",
        region_options: history?.region_options || (region ? [region] : []),
        compartment_id_options: history?.compartment_id_options || [],
        selected_log_group_id: history?.selected_log_group_id || "",
        selected_log_group_name: history?.selected_log_group_name || "",
      };
    });
  }

  function selectThemeStyle(style: ThemeStyleId) {
    setSettings((current) => {
      const selections = { ...defaultThemeSelections, ...current.theme_selection_by_style };
      return {
        ...current,
        theme_style: style,
        theme: selections[style],
        theme_selection_by_style: selections,
      };
    });
  }

  function selectTheme(theme: ThemeId) {
    setSettings((current) => {
      const selections = { ...defaultThemeSelections, ...current.theme_selection_by_style };
      return {
        ...current,
        theme,
        theme_selection_by_style: {
          ...selections,
          [current.theme_style]: theme,
        },
      };
    });
  }

  async function saveSettingsPayload(nextSettings = settings, busyKey = "settings", keepBusy = false) {
    setBusy(busyKey);
    setError("");
    try {
      const saved = await api<AppSettings>("/api/settings", {
        method: "PUT",
        body: JSON.stringify(nextSettings),
      });
      setSettings({ ...defaultSettings, ...saved });
      if (busyKey === "settings") {
        setStatus("Settings saved.");
      }
      return saved;
    } catch (err) {
      setError((err as Error).message);
      throw err;
    } finally {
      if (!keepBusy) {
        setBusy("");
      }
    }
  }

  async function saveCurrentSettings() {
    const saved = await saveSettingsPayload(settings, "settings");
    if (saved.compartment_id) {
      await runConnectionCheck(saved, true);
    }
  }

  async function toggleSidebar() {
    const next = { ...settings, sidebar_collapsed: !settings.sidebar_collapsed };
    setSettings(next);
    try {
      await saveSettingsPayload(next, "sidebar");
    } catch {
      // Error is surfaced by saveSettingsPayload.
    }
  }

  async function runConnectionCheck(nextSettings = settings, loadGroups = false) {
    setBusy("check");
    setError("");
    try {
      const payload = await api<OciCheck>("/api/oci/check", {
        method: "POST",
        body: JSON.stringify(nextSettings),
      });
      setCheck(payload);
      if (payload.remote_ok && loadGroups) {
        await resolveLogGroups(payload.log_groups || [], nextSettings);
      }
      setStatus(payload.remote_ok === false ? "Local config checked. OCI query failed." : "Connection check complete.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function loadLogGroups(settingsSnapshot = settings) {
    setBusy("groups");
    setError("");
    try {
      const payload = await api<{ provider: string; data: LogGroup[] }>(
        "/api/oci/log-groups",
        {
          method: "POST",
          body: JSON.stringify(settingsSnapshot),
        },
      );
      await resolveLogGroups(payload.data, settingsSnapshot);
      setStatus(`Loaded ${payload.data.length} log group(s) with ${payload.provider}.`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function loadLogs(
    logGroupId = settings.selected_log_group_id,
    logGroupName = settings.selected_log_group_name,
    persistSelection = true,
    settingsSnapshot = settings,
  ) {
    if (!logGroupId) {
      return;
    }
    const requestId = logLoadRequestId.current + 1;
    logLoadRequestId.current = requestId;
    logLoadController.current?.abort();
    const controller = new AbortController();
    logLoadController.current = controller;
    setBusy("logs");
    setError("");
    try {
      const requestSettings = {
        ...settingsSnapshot,
        selected_log_group_id: logGroupId,
        selected_log_group_name: logGroupName,
      };
      if (persistSelection) {
        await saveSettingsPayload(
          requestSettings,
          "logs",
          true,
        );
      }
      const payload = await api<{ provider: string; data: LogItem[] }>(
        "/api/oci/logs",
        {
          method: "POST",
          body: JSON.stringify({ log_group_id: logGroupId, settings: requestSettings }),
          signal: controller.signal,
        },
      );
      if (requestId !== logLoadRequestId.current) {
        return;
      }
      setLogs(payload.data);
      setLogsLoadedFor(logGroupId);
      setSelectedLogs([]);
      setStatus(`Loaded ${payload.data.length} log(s) with ${payload.provider}.`);
    } catch (err) {
      if ((err as Error).name !== "AbortError" && requestId === logLoadRequestId.current) {
        setError((err as Error).message);
      }
    } finally {
      if (requestId === logLoadRequestId.current) {
        setBusy("");
      }
    }
  }

  async function activateLogGroup(group: LogGroup | undefined, settingsSnapshot: AppSettings) {
    if (!group) {
      setSettings((current) => ({
        ...current,
        selected_log_group_id: "",
        selected_log_group_name: "",
      }));
      setLogs([]);
      setLogsLoadedFor("");
      setSelectedLogs([]);
      return;
    }

    const selectedSettings = {
      ...settingsSnapshot,
      selected_log_group_id: group.id,
      selected_log_group_name: group.name,
    };
    setSettings((current) => ({
      ...current,
      selected_log_group_id: group.id,
      selected_log_group_name: group.name,
    }));
    setLiveState("off");
    setLogs([]);
    setLogsLoadedFor("");
    setSelectedLogs([]);
    await loadLogs(group.id, group.name, true, selectedSettings);
  }

  async function resolveLogGroups(groups: LogGroup[], settingsSnapshot: AppSettings) {
    setLogGroups(groups);
    const resolvedGroup = groups.find((group) => group.id === settingsSnapshot.selected_log_group_id) ?? groups[0];
    await activateLogGroup(resolvedGroup, settingsSnapshot);
  }

  async function fetchAndFormat(mode: "manual" | "live" = timePreset === "live" ? "live" : "manual", liveDecision?: "switch" | "keep") {
    const selected = logs.filter((log) => selectedLogs.includes(log.id));
    if (!selected.length) {
      setError("Select at least one log.");
      return;
    }
    if (!sessionId || busy === "fetch") {
      return;
    }

    const preset = timePresets.find((item) => item.value === timePreset);
    const shouldRefreshRange = mode === "live" || (mode === "manual" && timePreset !== "custom");
    const range = shouldRefreshRange ? defaultTimeRange(preset?.minutes || 5) : { start: startTime, end: endTime };
    if (shouldRefreshRange) {
      setStartTime(range.start);
      setEndTime(range.end);
    }

    if (mode === "manual") {
      setLiveState("off");
      setRevisionChanges([]);
    } else if (liveState === "off" && !liveDecision) {
      await api(`/api/sessions/${sessionId}/results`, { method: "DELETE" });
      setResults([]);
      setActiveLogId("");
    }

    setBusy("fetch");
    setError("");
    setStatus("");
    try {
      await saveSettingsPayload(settings, "fetch", true);
      const payload = await api<{ results: FetchResult[]; revision_changes: RevisionChange[] }>("/api/logs/fetch-format", {
        method: "POST",
        body: JSON.stringify({
          session_id: sessionId,
          settings,
          log_group_id: settings.selected_log_group_id,
          log_group_name: settings.selected_log_group_name,
          logs: selected.map((log) => ({ id: log.id, name: log.name })),
          start_time: toIsoUtc(range.start),
          end_time: toIsoUtc(range.end),
          mode,
          live_decision: liveDecision,
        }),
      });
      setResults(payload.results);
      setActiveLogId(payload.results[0]?.result_id || payload.results[0]?.log_id || "");
      const successCount = payload.results.filter((result) => result.status === "success").length;
      if (payload.revision_changes.length) {
        setRevisionChanges(payload.revision_changes);
        setLiveState("paused");
        setStatus("Live polling paused for a newer deployment.");
      } else if (mode === "live") {
        setRevisionChanges([]);
        setLiveState("running");
        setStatus(`Live logs updated: ${successCount} selected log(s).`);
      } else {
        setStatus(`Formatted ${successCount} of ${payload.results.length} selected log(s).`);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function exportAll() {
    const resultIds = results
      .filter((result) => result.status === "success" && result.result_id)
      .map((result) => result.result_id as string);
    if (!resultIds.length || !sessionId) {
      setError("No formatted files are available to export.");
      return;
    }

    setBusy("zip");
    setError("");
    try {
      const response = await fetch("/api/files/export-zip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, result_ids: resultIds }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "formatted_logs.zip";
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy("");
    }
  }

  function onLogGroupChange(event: ChangeEvent<HTMLSelectElement>) {
    const id = event.target.value;
    const group = logGroups.find((candidate) => candidate.id === id);
    void activateLogGroup(group, settings);
  }

  function toggleSelectedLog(logId: string) {
    setSelectedLogs((current) => (current.includes(logId) ? current.filter((id) => id !== logId) : [...current, logId]));
  }

  function selectAllVisibleLogs() {
    setSelectedLogs((current) => Array.from(new Set([...current, ...filteredLogs.map((log) => log.id)])));
  }

  function clearSelectedLogs() {
    setSelectedLogs([]);
  }

  function applyTimePreset(nextPreset: TimePreset) {
    if (nextPreset !== "live" && liveState !== "off") {
      stopLive();
    }
    setTimePreset(nextPreset);
    const preset = timePresets.find((item) => item.value === nextPreset);
    if (!preset?.minutes) {
      return;
    }
    const range = defaultTimeRange(preset.minutes);
    setStartTime(range.start);
    setEndTime(range.end);
  }

  function onTerminalScroll(event: UIEvent<HTMLPreElement>) {
    if (!terminalHasMore || viewerLoading || !activeResult?.result_id || !sessionId) {
      return;
    }
    const element = event.currentTarget;
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    if (distanceFromBottom <= 160) {
      setViewerLoading(true);
      void api<TerminalPage>(
        `/api/sessions/${sessionId}/results/${activeResult.result_id}/lines?offset=${viewerLines.length}&limit=${TERMINAL_CHUNK_SIZE}&query=${encodeURIComponent(viewerSearch)}`,
      )
        .then((payload) => {
          setViewerLines((current) => [...current, ...payload.lines]);
          setViewerTotal(payload.total);
        })
        .catch((err) => setError((err as Error).message))
        .finally(() => setViewerLoading(false));
    }
  }

  async function clearFormattedLogs() {
    if (!sessionId) {
      return;
    }
    setBusy("clear");
    try {
      await api(`/api/sessions/${sessionId}/results`, { method: "DELETE" });
      setResults([]);
      setActiveLogId("");
      setViewerLines([]);
      setViewerTotal(0);
      setLiveState("off");
      setRevisionChanges([]);
      setStatus("Formatted logs cleared.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function copyActiveResult() {
    if (!activeResult?.result_id || !sessionId) {
      return;
    }
    setBusy("copy");
    try {
      const response = await fetch(`/api/sessions/${sessionId}/results/${activeResult.result_id}/content`);
      if (!response.ok) {
        throw new Error(await response.text());
      }
      await navigator.clipboard.writeText(await response.text());
      setStatus("Full formatted output copied.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy("");
    }
  }

  function stopLive() {
    setLiveState("off");
    setRevisionChanges([]);
    setStatus("Live polling stopped.");
  }

  useEffect(() => {
    if (liveState !== "running") {
      return undefined;
    }
    const interval = window.setInterval(() => {
      void fetchAndFormat("live");
    }, 120_000);
    return () => window.clearInterval(interval);
  }, [liveState]);

  function toggleSection(key: string) {
    setOpenSections((current) => ({ ...current, [key]: !current[key] }));
  }

  const providerLabel = check
    ? `${check.sdk_ready ? "SDK ready" : "SDK not ready"} / ${check.cli_ready ? "CLI ready" : "CLI missing"}`
    : "Not checked";

  return (
    <div className={`app-shell ${settings.sidebar_collapsed ? "sidebar-collapsed" : ""}`} data-theme={settings.theme}>
      <AppSidebar
        page={page}
        setPage={setPage}
        collapsed={settings.sidebar_collapsed}
        toggleSidebar={toggleSidebar}
        setupComplete={setupComplete}
        connectionLabel={providerLabel}
      />

      <main className="workspace">
        {(status || error) && (
          <div className={`notice ${error ? "error" : "success"}`}>
            {error ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
            <span>{error || status}</span>
          </div>
        )}

        {page === "home" && (
          <HomePage
            setupComplete={setupComplete}
            setPage={setPage}
            check={check}
            resultCount={results.length}
            selectedTheme={settings.theme}
          />
        )}

        {page === "search" && (
          <SearchPage
            setupComplete={setupComplete}
            setPage={setPage}
            settings={settings}
            logGroups={logGroups}
            logs={logs}
            filteredLogs={filteredLogs}
            selectedLogs={selectedLogs}
            startTime={startTime}
            endTime={endTime}
            timePreset={timePreset}
            logsLoadedFor={logsLoadedFor}
            sessionId={sessionId}
            liveState={liveState}
            revisionChanges={revisionChanges}
            logFilter={logFilter}
            results={results}
            activeResult={activeResult}
            displayedContent={displayedContent}
            terminalVisibleCount={terminalVisibleCount}
            terminalTotalCount={viewerTotal}
            terminalHasMore={terminalHasMore}
            viewerLoading={viewerLoading}
            viewerSearch={viewerSearch}
            busy={busy}
            loadLogGroups={loadLogGroups}
            loadLogs={loadLogs}
            fetchAndFormat={fetchAndFormat}
            exportAll={exportAll}
            clearFormattedLogs={clearFormattedLogs}
            copyActiveResult={copyActiveResult}
            stopLive={stopLive}
            onLogGroupChange={onLogGroupChange}
            toggleSelectedLog={toggleSelectedLog}
            selectAllVisibleLogs={selectAllVisibleLogs}
            clearSelectedLogs={clearSelectedLogs}
            setStartTime={setStartTime}
            setEndTime={setEndTime}
            applyTimePreset={applyTimePreset}
            setLogFilter={setLogFilter}
            setViewerSearch={setViewerSearch}
            setActiveLogId={setActiveLogId}
            onTerminalScroll={onTerminalScroll}
          />
        )}

        {page === "settings" && (
          <SettingsPage
            settings={settings}
            check={check}
            busy={busy}
            openSections={openSections}
            setupComplete={setupComplete}
            patchSettings={patchSettings}
            selectProfile={selectProfile}
            selectThemeStyle={selectThemeStyle}
            selectTheme={selectTheme}
            saveCurrentSettings={saveCurrentSettings}
            runConnectionCheck={runConnectionCheck}
            profileOptions={profileOptions}
            regionOptions={regionOptions}
            compartmentOptions={compartmentOptions}
            reloadProfileOptions={reloadProfileOptions}
            toggleSection={toggleSection}
          />
        )}
      </main>
    </div>
  );
}

function AppSidebar({
  page,
  setPage,
  collapsed,
  toggleSidebar,
  setupComplete,
  connectionLabel,
}: {
  page: Page;
  setPage: (page: Page) => void;
  collapsed: boolean;
  toggleSidebar: () => void;
  setupComplete: boolean;
  connectionLabel: string;
}) {
  return (
    <aside className="app-sidebar">
      <div className="sidebar-top">
        <button className="brand-row brand-button" title={collapsed ? "Expand sidebar" : "Collapse sidebar"} onClick={toggleSidebar}>
          <div className="brand-mark">
            <Terminal size={20} />
          </div>
          <div className="brand-copy">
            <h1>OCI Log Organizer</h1>
            <p>Application log operations</p>
          </div>
        </button>
        {!collapsed && (
          <button className="sidebar-icon-button" title="Collapse sidebar" onClick={toggleSidebar}>
            <ChevronLeft size={18} />
          </button>
        )}
      </div>

      <nav className="sidebar-nav">
        <NavButton collapsed={collapsed} active={page === "home"} icon={<Home size={18} />} label="Home" onClick={() => setPage("home")} />
        <NavButton
          collapsed={collapsed}
          active={page === "search"}
          icon={<Search size={18} />}
          label="Search Logs"
          onClick={() => setPage("search")}
        />
        <NavButton
          collapsed={collapsed}
          active={page === "settings"}
          icon={<Settings size={18} />}
          label="Settings"
          onClick={() => setPage("settings")}
        />
      </nav>

      <div className="sidebar-bottom">
        <div className={`setup-pill ${setupComplete ? "ready" : "needs-setup"}`}>
          {setupComplete ? <ShieldCheck size={15} /> : <AlertCircle size={15} />}
          <span>{setupComplete ? connectionLabel : "Setup required"}</span>
        </div>
        <div className="credits" title="Karthik Sriram" aria-label="Crafted by Karthik Sriram. Built with Codex.">
          <div className="codex-badge" aria-hidden="true" title="Karthik Sriram">
            KS
          </div>
          <div className="credit-copy-wrap">
            <p className="credit-copy">
              <span className="credit-owner">Crafted by Karthik Sriram</span>
              {/* Legacy encoded credit line kept non-rendered after the copy refresh.
              © 2026 Karthik Sriram
              */}
              <span className="credit-meta">Built with Codex</span>
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
}

function NavButton({
  collapsed,
  active,
  icon,
  label,
  onClick,
}: {
  collapsed: boolean;
  active: boolean;
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button className={`nav-button ${active ? "active" : ""}`} title={collapsed ? label : undefined} onClick={onClick}>
      {icon}
      <span className="nav-label">{label}</span>
    </button>
  );
}

function HomePage({
  setupComplete,
  setPage,
  check,
  resultCount,
  selectedTheme,
}: {
  setupComplete: boolean;
  setPage: (page: Page) => void;
  check: OciCheck | null;
  resultCount: number;
  selectedTheme: ThemeId;
}) {
  const themeName = themes.find((theme) => theme.id === selectedTheme)?.name ?? "Frosted Light";
  return (
    <section className="home-page">
      <div className="hero-glass">
        <div className="hero-content">
          <p className="eyebrow">Local OCI log workspace</p>
          <h2>Search, clean, and review OCI application logs without leaving localhost.</h2>
          <p className="hero-copy">
            Configure OCI once, select logs from a group, and format each export with app-timestamp sorting and latest-revision filtering.
          </p>
          <div className="hero-actions">
            <button className="primary-button" onClick={() => setPage(setupComplete ? "search" : "settings")}>
              {setupComplete ? <Search size={17} /> : <Settings size={17} />}
              {setupComplete ? "Open Search Logs" : "Complete Setup"}
            </button>
            <button className="secondary-button" onClick={() => setPage("settings")}>
              <SlidersHorizontal size={17} />
              Preferences
            </button>
          </div>
        </div>
      </div>

      <div className="home-metrics">
        <InfoTile icon={<ShieldCheck size={18} />} label="Setup" value={setupComplete ? "Ready" : "Needs setup"} />
        <InfoTile icon={<ServerCog size={18} />} label="Provider" value={check ? (check.remote_ok === false ? "Local only" : "Checked") : "Not checked"} />
        <InfoTile icon={<Layers size={18} />} label="Theme" value={themeName} />
        <InfoTile icon={<Terminal size={18} />} label="Formatted runs" value={String(resultCount)} />
      </div>
    </section>
  );
}

function SearchPage(props: {
  setupComplete: boolean;
  setPage: (page: Page) => void;
  settings: AppSettings;
  logGroups: LogGroup[];
  logs: LogItem[];
  logsLoadedFor: string;
  filteredLogs: LogItem[];
  selectedLogs: string[];
  startTime: string;
  endTime: string;
  timePreset: TimePreset;
  sessionId: string;
  liveState: "off" | "running" | "paused";
  revisionChanges: RevisionChange[];
  logFilter: string;
  results: FetchResult[];
  activeResult: FetchResult | null;
  displayedContent: string;
  terminalVisibleCount: number;
  terminalTotalCount: number;
  terminalHasMore: boolean;
  viewerLoading: boolean;
  viewerSearch: string;
  busy: string;
  loadLogGroups: () => void;
  loadLogs: () => void;
  fetchAndFormat: (mode?: "manual" | "live", liveDecision?: "switch" | "keep") => void;
  exportAll: () => void;
  clearFormattedLogs: () => void;
  copyActiveResult: () => void;
  stopLive: () => void;
  onLogGroupChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  toggleSelectedLog: (logId: string) => void;
  selectAllVisibleLogs: () => void;
  clearSelectedLogs: () => void;
  setStartTime: (value: string) => void;
  setEndTime: (value: string) => void;
  applyTimePreset: (value: TimePreset) => void;
  setLogFilter: (value: string) => void;
  setViewerSearch: (value: string) => void;
  setActiveLogId: (value: string) => void;
  onTerminalScroll: (event: UIEvent<HTMLPreElement>) => void;
}) {
  const [logsCollapsed, setLogsCollapsed] = useState(false);
  const [terminalFullscreen, setTerminalFullscreen] = useState(false);
  const selectedLogItems = props.logs.filter((log) => props.selectedLogs.includes(log.id));
  const compactLogName = (value: string) => (value.length > 54 ? `${value.slice(0, 30)}...${value.slice(-20)}` : value);
  const compactCompartment = (value: string) => (value.length > 34 ? `${value.slice(0, 17)}...${value.slice(-12)}` : value || "No compartment");

  useEffect(() => {
    if (!terminalFullscreen) {
      return undefined;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setTerminalFullscreen(false);
      }
    };
    document.body.classList.add("terminal-fullscreen-open");
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.classList.remove("terminal-fullscreen-open");
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [terminalFullscreen]);

  if (!props.setupComplete) {
    return (
      <section className="setup-empty">
        <div className="glass-card setup-card">
          <Sparkles size={24} />
          <h2>Finish one-time setup first</h2>
          <p>Add your OCI profile, region, and compartment OCID before loading log groups.</p>
          <button className="primary-button" onClick={() => props.setPage("settings")}>
            <Settings size={17} />
            Open Settings
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="search-page">
      <PageHeader
        eyebrow="Search Logs"
        title="Fetch and format OCI logs"
        description="Choose a log group, select one or more logs, and review each formatted output independently."
        actions={
          <div className="connection-context" title={`${props.settings.profile} · ${props.settings.region || "profile region"} · ${props.settings.compartment_id}`}>
            <ServerCog size={15} />
            <span>{props.settings.profile}</span>
            <span>{props.settings.region || "Profile region"}</span>
            <span>{compactCompartment(props.settings.compartment_id)}</span>
          </div>
        }
      />
      {props.busy === "fetch" && (props.timePreset !== "live" || props.liveState === "off") && <FetchLoadingOverlay selectedCount={props.selectedLogs.length} />}

      <section className="glass-card controls-grid">
        <div className="control-block">
          <label>
            <span className="surface-section-title">Log group</span>
            <select value={props.settings.selected_log_group_id} onChange={props.onLogGroupChange}>
              <option value="">Select log group</option>
              {props.logGroups.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.name || group.id}
                </option>
              ))}
            </select>
          </label>
          <button
            className="icon-button"
            title="Reload log groups"
            onClick={props.loadLogGroups}
            disabled={props.busy === "groups"}
          >
            {props.busy === "groups" ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
          </button>
        </div>

        <div className="time-row">
          <label>
            Start UTC
            <input
              type="datetime-local"
              value={props.startTime}
              disabled={props.timePreset === "live"}
              onChange={(event) => {
                props.setStartTime(event.target.value);
                props.applyTimePreset("custom");
              }}
            />
          </label>
          <label>
            End UTC
            <input
              type="datetime-local"
              value={props.endTime}
              disabled={props.timePreset === "live"}
              onChange={(event) => {
                props.setEndTime(event.target.value);
                props.applyTimePreset("custom");
              }}
            />
          </label>
          <label className="time-preset-field">
            Quick range
            <select
              value={props.timePreset}
              onClick={() => {
                if (props.timePreset !== "custom") {
                  props.applyTimePreset(props.timePreset);
                }
              }}
              onChange={(event) => props.applyTimePreset(event.target.value as TimePreset)}
            >
              {timePresets.map((preset) => (
                <option key={preset.value} value={preset.value}>
                  {preset.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      <section className="glass-card log-selection">
        <div className="selection-header">
          <div>
            <h3 className="surface-section-title">Logs in group</h3>
            <p>Select one or more logs. Each selected log is fetched and formatted separately.</p>
          </div>
          <div className="selection-actions">
            <button
              className="secondary-button compact-button"
              onClick={() => props.loadLogs()}
              disabled={!props.settings.selected_log_group_id || props.busy === "logs"}
            >
              {props.busy === "logs" ? <Loader2 className="spin" size={16} /> : <FolderOpen size={16} />}
              {props.logsLoadedFor === props.settings.selected_log_group_id ? "Reload logs" : "Load logs"}
            </button>
            {!logsCollapsed && (
              <>
                <button className="secondary-button compact-button" onClick={props.selectAllVisibleLogs} disabled={!props.filteredLogs.length}>
                  <ListChecks size={16} />
                  Select visible
                </button>
                <button className="secondary-button compact-button" onClick={props.clearSelectedLogs} disabled={!props.selectedLogs.length}>
                  <X size={16} />
                  Clear
                </button>
              </>
            )}
            <span>{props.selectedLogs.length} selected</span>
            <button
              className="icon-button log-collapse-button"
              title={logsCollapsed ? "Expand logs" : "Collapse logs"}
              aria-expanded={!logsCollapsed}
              onClick={() => setLogsCollapsed((current) => !current)}
            >
              <ChevronDown className={logsCollapsed ? "log-collapse-icon collapsed" : "log-collapse-icon"} size={17} />
            </button>
          </div>
        </div>
        {logsCollapsed ? (
          <div className="collapsed-log-summary">
            {selectedLogItems.length ? (
              selectedLogItems.slice(0, 4).map((log) => (
                <span key={log.id} title={log.name || log.id}>{compactLogName(log.name || log.id)}</span>
              ))
            ) : (
              <span>No logs selected yet.</span>
            )}
            {selectedLogItems.length > 4 && <strong>+{selectedLogItems.length - 4} more</strong>}
          </div>
        ) : (
          <>
            <div className="log-picker-toolbar">
              <label className="search-box log-search-box">
                <Search size={15} />
                <input value={props.logFilter} onChange={(event) => props.setLogFilter(event.target.value)} placeholder="Filter log names" />
              </label>
            </div>
            <div className="log-card-list" role="listbox" aria-label="Logs in selected group" aria-multiselectable="true">
              {props.filteredLogs.length === 0 ? (
                <div className="empty-state">
                  {props.logs.length
                    ? "No logs match this filter."
                    : props.settings.selected_log_group_id
                      ? "Load this log group to see available logs."
                      : "Select a log group to load its logs."}
                </div>
              ) : (
                props.filteredLogs.map((log) => {
                  const selected = props.selectedLogs.includes(log.id);
                  const state = log.is_enabled === false ? "Disabled" : log.lifecycle_state || "Enabled";
                  return (
                    <button
                      key={log.id}
                      className={`log-card-row ${selected ? "selected" : ""}`}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      onClick={() => props.toggleSelectedLog(log.id)}
                    >
                      <span className="log-check">{selected ? <CheckCircle2 size={16} /> : null}</span>
                      <span className="log-card-main">
                        <strong title={log.name || log.id}>{compactLogName(log.name || log.id)}</strong>
                        <small>
                          {log.log_type || "Application log"} - {state}
                        </small>
                      </span>
                    </button>
                  );
                })
              )}
            </div>
          </>
        )}
      </section>

      <section className="results-layout">
        <div className="glass-card result-list">
          <div className="result-list-header">
            <span className="surface-section-title">Formatted logs</span>
            <div className="result-list-actions">
              <button className="icon-button" title="Export all formatted logs" onClick={props.exportAll} disabled={!props.results.length || props.busy === "zip"}>
                {props.busy === "zip" ? <Loader2 className="spin" size={16} /> : <FileArchive size={16} />}
              </button>
              <button className="icon-button" title="Clear formatted logs" onClick={props.clearFormattedLogs} disabled={!props.results.length || props.busy === "clear"}>
                {props.busy === "clear" ? <Loader2 className="spin" size={16} /> : <Trash2 size={16} />}
              </button>
            </div>
          </div>
          {props.results.length === 0 ? (
            <div className="empty-state">No formatted runs yet.</div>
          ) : (
            props.results.map((result) => (
              <button
                key={result.result_id || result.log_id}
                className={`result-item ${props.activeResult?.result_id === result.result_id ? "active" : ""} ${result.status}`}
                onClick={() => props.setActiveLogId(result.result_id || result.log_id)}
              >
                <span>{result.log_name}</span>
                <small>{result.status === "success" ? `${result.stats?.output_count ?? 0} lines` : "error"}</small>
              </button>
            ))
          )}
        </div>

        <div className="glass-card viewer-panel">
          <div className="viewer-toolbar">
            <div>
              <h3>{props.activeResult?.log_name || "Terminal viewer"}</h3>
              <p>{props.activeResult ? "Session-scoped formatted output" : "Formatted output will appear here."}</p>
            </div>
            <label className="search-box viewer-filter">
              <Search size={15} />
              <input value={props.viewerSearch} onChange={(event) => props.setViewerSearch(event.target.value)} placeholder="Filter lines" />
            </label>
            <div className="viewer-actions">
              <button
                className="primary-button compact-run-button"
                onClick={() => {
                  if (props.timePreset === "live" && props.liveState === "running") {
                    props.stopLive();
                  } else {
                    props.fetchAndFormat(props.timePreset === "live" ? "live" : "manual");
                  }
                }}
                disabled={!props.selectedLogs.length || props.busy === "fetch" || props.liveState === "paused"}
              >
                {props.busy === "fetch" ? <Loader2 className="spin" size={16} /> : props.timePreset === "live" ? <Radio size={16} /> : <Play size={16} />}
                {props.timePreset === "live" ? (props.liveState === "running" ? "Stop live" : "Start live") : "Run"}
              </button>
              <button
                className="icon-button"
                title="Copy full formatted text"
                onClick={props.copyActiveResult}
                disabled={!props.activeResult?.result_id || props.busy === "copy"}
              >
                {props.busy === "copy" ? <Loader2 className="spin" size={16} /> : <Clipboard size={16} />}
              </button>
              {props.activeResult?.result_id && props.sessionId && (
                <a className="icon-button" title="Download current log" href={`/api/sessions/${props.sessionId}/results/${props.activeResult.result_id}/download`}>
                  <Download size={16} />
                </a>
              )}
            </div>
          </div>

          {props.activeResult?.status === "error" ? (
            <div className="error-box">{props.activeResult.message}</div>
          ) : (
            <>
              <StatsStrip result={props.activeResult} />
              <div className="terminal-surface">
                <pre className="terminal-window" onScroll={props.onTerminalScroll}>
                  {props.displayedContent || (props.viewerLoading ? "Loading log lines..." : "No log lines to display.")}
                </pre>
                <button
                  className="terminal-expand-button"
                  type="button"
                  title="Expand log viewer"
                  aria-label="Expand log viewer"
                  onClick={() => setTerminalFullscreen(true)}
                  disabled={!props.activeResult?.result_id}
                >
                  <Maximize2 size={17} />
                </button>
              </div>
              {props.terminalTotalCount > TERMINAL_CHUNK_SIZE && (
                <div className="terminal-window-status">
                  Showing {props.terminalVisibleCount} of {props.terminalTotalCount} lines
                  {props.terminalHasMore ? " - scroll to load more" : ""}
                </div>
              )}
            </>
          )}
          {props.liveState === "paused" && props.revisionChanges.length > 0 && (
            <div className="live-change-prompt" role="dialog" aria-live="assertive">
              <div>
                <strong>Newer deployment detected</strong>
                <span>{props.revisionChanges.map((change) => `${change.log_name} (${change.changes.length})`).join(", ")}</span>
              </div>
              <div className="live-change-actions">
                <button className="primary-button compact-button" onClick={() => props.fetchAndFormat("live", "switch")}>Switch to latest</button>
                <button className="secondary-button compact-button" onClick={() => props.fetchAndFormat("live", "keep")}>Keep current</button>
                <button className="secondary-button compact-button" onClick={props.stopLive}>Stop live</button>
              </div>
            </div>
          )}
        </div>
      </section>
      {terminalFullscreen && (
        <div className="terminal-fullscreen-overlay" role="dialog" aria-modal="true" aria-label="Fullscreen log viewer">
          <div className="terminal-fullscreen-shell">
            <header className="terminal-fullscreen-header">
              <div>
                <h2>{props.activeResult?.log_name || "Terminal viewer"}</h2>
              </div>
              <div className="terminal-fullscreen-actions">
                <label className="search-box fullscreen-search-box">
                  <Search size={15} />
                  <input value={props.viewerSearch} onChange={(event) => props.setViewerSearch(event.target.value)} placeholder="Filter lines" />
                </label>
                <button className="icon-button" title="Copy full formatted text" onClick={props.copyActiveResult} disabled={!props.activeResult?.result_id || props.busy === "copy"}>
                  {props.busy === "copy" ? <Loader2 className="spin" size={16} /> : <Clipboard size={16} />}
                </button>
                <button className="icon-button" type="button" title="Return to normal view" aria-label="Return to normal view" onClick={() => setTerminalFullscreen(false)}>
                  <Minimize2 size={17} />
                </button>
              </div>
            </header>
            <div className="terminal-fullscreen-surface">
              <pre className="terminal-window terminal-window-fullscreen" onScroll={props.onTerminalScroll}>
                {props.displayedContent || (props.viewerLoading ? "Loading log lines..." : "No log lines to display.")}
              </pre>
            </div>
            {props.terminalTotalCount > TERMINAL_CHUNK_SIZE && (
              <div className="terminal-window-status">
                Showing {props.terminalVisibleCount} of {props.terminalTotalCount} lines
                {props.terminalHasMore ? " - scroll to load more" : ""}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function FetchLoadingOverlay({ selectedCount }: { selectedCount: number }) {
  return (
    <div className="fetch-overlay" role="status" aria-live="polite">
      <div className="fetch-loading-card">
        <div className="loading-orbit" aria-hidden="true">
          <Loader2 className="spin" size={24} />
        </div>
        <div>
          <strong>Fetching and formatting logs</strong>
          <span>{selectedCount} selected log{selectedCount === 1 ? "" : "s"} will appear as separate formatted outputs.</span>
        </div>
      </div>
    </div>
  );
}

function SettingsPage({
  settings,
  check,
  busy,
  openSections,
  setupComplete,
  patchSettings,
  selectProfile,
  selectThemeStyle,
  selectTheme,
  saveCurrentSettings,
  runConnectionCheck,
  profileOptions,
  regionOptions,
  compartmentOptions,
  reloadProfileOptions,
  toggleSection,
}: {
  settings: AppSettings;
  check: OciCheck | null;
  busy: string;
  openSections: Record<string, boolean>;
  setupComplete: boolean;
  patchSettings: <T extends keyof AppSettings>(key: T, value: AppSettings[T]) => void;
  selectProfile: (profile: string) => void;
  selectThemeStyle: (style: ThemeStyleId) => void;
  selectTheme: (theme: ThemeId) => void;
  saveCurrentSettings: () => void;
  runConnectionCheck: () => void;
  profileOptions: string[];
  regionOptions: string[];
  compartmentOptions: string[];
  reloadProfileOptions: () => void;
  toggleSection: (key: string) => void;
}) {
  return (
    <section className="settings-page">
      <PageHeader
        eyebrow="Settings"
        title="One-time setup and preferences"
        description="Keep connection details, formatter defaults, and appearance preferences in one place."
        actions={
          <>
            <button className="secondary-button" onClick={() => runConnectionCheck()} disabled={busy === "check"}>
              {busy === "check" ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
              Check connection
            </button>
            <button className="primary-button" onClick={saveCurrentSettings} disabled={busy === "settings"}>
              {busy === "settings" ? <Loader2 className="spin" size={16} /> : <Save size={16} />}
              Save settings
            </button>
          </>
        }
      />

      {(!setupComplete || check?.remote_ok === false) && (
        <div className={`setup-banner ${setupComplete ? "ready" : "needs-setup"}`}>
          {setupComplete ? <ShieldCheck size={18} /> : <AlertCircle size={18} />}
          <span>
            {setupComplete
              ? "OCI settings are saved, but the last connection check could not query OCI."
              : "Add profile, config file, and compartment OCID to enable log search."}
          </span>
        </div>
      )}

      <div className="settings-stack">
        <SettingsSection id="oci" title="OCI Connection" icon={<ServerCog size={18} />} open={openSections.oci} toggleSection={toggleSection}>
          <div className="settings-grid">
            <label>
              Config file
              <input value={settings.config_file} onChange={(event) => patchSettings("config_file", event.target.value)} />
            </label>
            <label>
              Profile
              <SelectControl
                value={settings.profile}
                onChange={(event) => selectProfile(event.target.value)}
                onFocus={reloadProfileOptions}
              >
                {profileOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </SelectControl>
            </label>
            <label>
              Region
              <SavedSettingSelect
                label="region"
                value={settings.region}
                options={regionOptions}
                onChange={(value) => patchSettings("region", value)}
                placeholder="ap-hyderabad-1"
              />
            </label>
            <label>
              Provider
              <SelectControl value={settings.provider_mode} onChange={(event) => patchSettings("provider_mode", event.target.value as ProviderMode)}>
                <option value="auto">Auto</option>
                <option value="sdk">SDK only</option>
                <option value="cli">CLI only</option>
              </SelectControl>
            </label>
            <label className="full-span">
              Compartment OCID
              <SavedSettingSelect
                label="compartment OCID"
                value={settings.compartment_id}
                options={compartmentOptions}
                onChange={(value) => patchSettings("compartment_id", value)}
                placeholder="ocid1.compartment.oc1..."
              />
            </label>
          </div>
        </SettingsSection>

        <SettingsSection id="formatter" title="Formatter" icon={<SlidersHorizontal size={18} />} open={openSections.formatter} toggleSection={toggleSection}>
          <div className="settings-grid">
            <label>
              Output
              <select value={settings.output_format} onChange={(event) => patchSettings("output_format", event.target.value as OutputFormat)}>
                <option value="text">Text</option>
                <option value="jsonl">JSONL</option>
              </select>
            </label>
            <label>
              Revision scope
              <select value={settings.latest_revision_scope} onChange={(event) => patchSettings("latest_revision_scope", event.target.value as RevisionScope)}>
                <option value="workload">Per workload</option>
                <option value="global">Global latest</option>
              </select>
            </label>
            <Toggle label="Latest revision only" checked={settings.filter_latest_revision} onChange={(value) => patchSettings("filter_latest_revision", value)} />
            <Toggle label="Merge OCI partial logs" checked={settings.merge_partial_oci_logs} onChange={(value) => patchSettings("merge_partial_oci_logs", value)} />
            <Toggle label="Sort by app timestamp" checked={settings.sort_by_timestamp} onChange={(value) => patchSettings("sort_by_timestamp", value)} />
            <Toggle
              label="Remove timestamp in message"
              checked={settings.remove_timestamp_from_message}
              onChange={(value) => patchSettings("remove_timestamp_from_message", value)}
            />
          </div>
        </SettingsSection>

        <SettingsSection id="appearance" title="Appearance" icon={<Paintbrush size={18} />} open={openSections.appearance} toggleSection={toggleSection}>
          <label className="theme-style-field">
            Theme style
            <select value={settings.theme_style} onChange={(event) => selectThemeStyle(event.target.value as ThemeStyleId)}>
              {themeStyles.map((style) => (
                <option key={style.id} value={style.id}>
                  {style.name}
                </option>
              ))}
            </select>
            <small>{themeStyles.find((style) => style.id === settings.theme_style)?.description}</small>
          </label>
          <div className="theme-grid">
            {themes.filter((theme) => theme.style === settings.theme_style).map((theme) => (
              <button
                key={theme.id}
                className={`theme-option theme-preview-${theme.id} ${settings.theme === theme.id ? "selected" : ""}`}
                type="button"
                aria-pressed={settings.theme === theme.id}
                onClick={() => selectTheme(theme.id)}
              >
                <span className="theme-swatch" />
                <strong>{theme.name}</strong>
                <small>{theme.description}</small>
              </button>
            ))}
          </div>
        </SettingsSection>

        <SettingsSection id="diagnostics" title="Diagnostics" icon={<ShieldCheck size={18} />} open={openSections.diagnostics} toggleSection={toggleSection}>
          <div className="diagnostics-grid">
            <InfoTile icon={<ServerCog size={18} />} label="SDK" value={check ? (check.sdk_ready ? "Ready" : "Not ready") : "Not checked"} />
            <InfoTile icon={<Terminal size={18} />} label="CLI" value={check ? (check.cli_ready ? "Ready" : "Missing") : "Not checked"} />
            <InfoTile
              icon={<ShieldCheck size={18} />}
              label="Remote"
              value={check ? (check.remote_ok === false ? "Failed" : check.remote_ok ? "Ready" : "Not queried") : "Not checked"}
            />
          </div>
          {check?.sdk_error && <div className="error-box">{check.sdk_error}</div>}
          {check?.remote_error && <div className="error-box">{check.remote_error}</div>}
        </SettingsSection>
      </div>
    </section>
  );
}

function PageHeader({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description: string; actions?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

function SelectControl({
  value,
  onChange,
  onFocus,
  children,
}: {
  value: string;
  onChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  onFocus?: () => void;
  children: ReactNode;
}) {
  return (
    <span className="select-control">
      <select value={value} onChange={onChange} onFocus={onFocus}>
        {children}
      </select>
      <ChevronDown size={16} aria-hidden="true" />
    </span>
  );
}

function SavedSettingSelect({
  label,
  value,
  options,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
  placeholder: string;
}) {
  const [isEnteringValue, setIsEnteringValue] = useState(false);
  const hasCurrentOption = options.includes(value);

  if (isEnteringValue) {
    return (
      <input
        autoFocus
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onBlur={() => setIsEnteringValue(false)}
        placeholder={placeholder}
      />
    );
  }

  return (
    <SelectControl
      value={value}
      onChange={(event) => {
        if (event.target.value === ENTER_NEW_VALUE) {
          setIsEnteringValue(true);
          return;
        }
        onChange(event.target.value);
      }}
    >
      {!hasCurrentOption && value && <option value={value}>{value}</option>}
      {!value && <option value="">Select a {label}</option>}
      {options.map((option) => (
        <option key={option} value={option}>
          {option}
        </option>
      ))}
      <option value={ENTER_NEW_VALUE}>Enter a new {label}...</option>
    </SelectControl>
  );
}

function SettingsSection({
  id,
  title,
  icon,
  open,
  toggleSection,
  children,
}: {
  id: string;
  title: string;
  icon: ReactNode;
  open: boolean;
  toggleSection: (key: string) => void;
  children: ReactNode;
}) {
  return (
    <section className="glass-card settings-section">
      <button className="section-toggle" onClick={() => toggleSection(id)}>
        <span>
          {icon}
          {title}
        </span>
        <ChevronDown className={open ? "section-open" : ""} size={18} />
      </button>
      {open && <div className="section-content">{children}</div>}
    </section>
  );
}

function InfoTile({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="info-tile">
      <div className="info-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="toggle-row">
      <span>{label}</span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}

function StatsStrip({ result }: { result: FetchResult | null }) {
  const [metadataOpen, setMetadataOpen] = useState(false);
  if (!result?.stats) {
    return <div className="stats-strip muted">No formatter stats yet.</div>;
  }

  const selections = Object.entries(result.stats.selections || {});
  const detail = (value: unknown, fallback = "Not available") => String(value || fallback);
  const candidateGroups = Object.entries(result.stats.deployment_candidates || {});
  const candidates: DeploymentCandidate[] = candidateGroups.flatMap(([workload, items]) =>
    items.map((item) => ({ workload, ...item }) as DeploymentCandidate),
  );
  const currentCandidates = candidates.filter((candidate) => candidate.is_current === true);
  const filteredCandidates = candidates.filter((candidate) => candidate.is_filtered_out === true);
  const formattedCandidates: DeploymentCandidate[] = currentCandidates.length
    ? currentCandidates
    : selections.map(([workload, selection]) => ({ workload, ...selection }) as DeploymentCandidate);
  const compact = (value: unknown, fallback = "Not available") => {
    const full = detail(value, fallback);
    return full.length > 38 ? `${full.slice(0, 17)}...${full.slice(-15)}` : full;
  };
  const metadataEntry = (candidate: DeploymentCandidate, index: number) => (
    <div className="metadata-entry" key={`${candidate.workload}-${candidate.revision || candidate.image_digest || candidate.container_image || index}`}>
      <div>
        <span>Revision</span>
        <code title={detail(candidate.revision, "Revision metadata unavailable")}>{compact(candidate.revision, "Revision metadata unavailable")}</code>
      </div>
      <div>
        <span>Image digest</span>
        <code title={detail(candidate.image_digest || candidate.container_image, "Image metadata unavailable")}>
          {compact(candidate.image_digest || candidate.container_image, "Image metadata unavailable")}
        </code>
      </div>
      <div>
        <span>Container</span>
        <code title={detail(candidate.container_name, "Container metadata unavailable")}>{compact(candidate.container_name, "Container metadata unavailable")}</code>
      </div>
    </div>
  );

  return (
    <div className="stats-area">
      <div className="stats-strip">
        <span>Raw {result.stats.raw_count}</span>
        <span>Filtered {result.stats.filtered_count}</span>
        <span>Output {result.stats.output_count}</span>
        {result.stats.live_added_count !== undefined && result.stats.live_added_count !== null && <span>New {result.stats.live_added_count}</span>}
        <span>{result.provider}</span>
        {(formattedCandidates.length > 0 || filteredCandidates.length > 0) && (
          <button
            className={`metadata-chip ${metadataOpen ? "open" : ""}`}
            type="button"
            aria-expanded={metadataOpen}
            onClick={() => setMetadataOpen((current) => !current)}
          >
            <Layers size={14} />
            Revision metadata
            {filteredCandidates.length > 0 && <b>+{filteredCandidates.length}</b>}
            <ChevronDown className={metadataOpen ? "metadata-chevron open" : "metadata-chevron"} size={14} />
          </button>
        )}
      </div>
      {metadataOpen && (
        <div className="metadata-inspector">
          {formattedCandidates.length > 0 && (
            <section>
              <div className="metadata-section-heading">
                <strong>Formatted now</strong>
                <span>{formattedCandidates.length} active</span>
              </div>
              <div className="metadata-entry-list">
                {formattedCandidates.map(metadataEntry)}
              </div>
            </section>
          )}
          {filteredCandidates.length > 0 && (
            <section>
              <div className="metadata-section-heading muted-heading">
                <strong>Filtered out</strong>
                <span>{filteredCandidates.length} earlier revision{filteredCandidates.length === 1 ? "" : "s"}</span>
              </div>
              <div className="metadata-entry-list">
                {filteredCandidates.map(metadataEntry)}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
