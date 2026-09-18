import { useEffect, useState } from "react";

export type MicPermission = "granted" | "prompt" | "denied" | "unknown";

// Reads the microphone permission without asking for it, so the page can explain what
// will happen before the browser's own dialog appears. "unknown" where the browser does
// not expose it; the dialog on Start still works there.
export function useMicPermission(): MicPermission {
  const [state, setState] = useState<MicPermission>("unknown");

  useEffect(() => {
    let status: PermissionStatus | null = null;
    let cancelled = false;
    const update = () => status && setState(status.state as MicPermission);
    navigator.permissions
      ?.query({ name: "microphone" as PermissionName })
      .then((result) => {
        if (cancelled) return;
        status = result;
        update();
        result.addEventListener("change", update);
      })
      .catch(() => setState("unknown"));
    return () => {
      cancelled = true;
      status?.removeEventListener("change", update);
    };
  }, []);

  return state;
}
