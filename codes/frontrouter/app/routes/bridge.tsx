import { useEffect, useState } from "react";
import { useLocation } from "react-router";

import type { Route } from "./+types/bridge";
import { BridgeView } from "~/components/BridgeView";

export function meta({}: Route.MetaArgs) {
  return [{ title: "SynapVocal" }];
}

// The logo links here with state { fresh: true }. Each such visit remounts the page, which
// stops listening, drops the sentences and brings back the introduction. Other links to
// this page (the Bridge tab) keep whatever is in progress.
export default function Bridge() {
  const location = useLocation();
  const [resets, setResets] = useState(0);
  const fresh = (location.state as { fresh?: boolean } | null)?.fresh === true;
  useEffect(() => {
    if (fresh) setResets((n) => n + 1);
  }, [fresh, location.key]);
  return <BridgeView key={resets} mode="bridge" />;
}
