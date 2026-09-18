import { redirect } from "react-router";

import type { Route } from "./+types/contribute.session";
import { BridgeView } from "~/components/BridgeView";
import { contrib } from "~/lib/contrib/contrib.server";
import { getUserId } from "~/lib/session.server";

export function meta({}: Route.MetaArgs) {
  return [{ title: "Contribution session - SynapVocal" }];
}

// Only for signed-in contributors with active consent; everyone else goes to the page
// that explains contributing and asks for consent first.
export async function loader({ request }: Route.LoaderArgs) {
  const userId = await getUserId(request);
  if (!userId) throw redirect("/contribute");
  const me = await contrib.me(userId).catch(() => null);
  if (!me?.consent) throw redirect("/contribute");
  return null;
}

export default function ContributionSession() {
  return <BridgeView mode="contribute" />;
}
