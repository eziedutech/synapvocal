import { Badge, Card, Code, DataList, Flex, Heading } from "@radix-ui/themes";

import type { Route } from "./+types/home";
import { InfoTip } from "~/components/InfoTip";
import { Notice } from "~/components/Notice";
import { getBackpyHealth } from "~/lib/backpy.server";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "SynapVocal" },
    { name: "description", content: "Realtime Voice Accessibility Bridge" },
  ];
}

export async function loader() {
  try {
    return { backpy: await getBackpyHealth(), error: null };
  } catch (error) {
    return { backpy: null, error: error instanceof Error ? error.message : String(error) };
  }
}

function KeyBadge({ present }: { present: boolean }) {
  return (
    <Badge color={present ? "jade" : "amber"} variant="soft">
      {present ? "Configured" : "Missing"}
    </Badge>
  );
}

export default function Home({ loaderData }: Route.ComponentProps) {
  const { backpy, error } = loaderData;

  return (
    <Flex direction="column" gap="5">
      <Heading size="7">System status</Heading>

      {backpy ? (
        <Notice tone="ok" title="Frontend and backend are connected" />
      ) : (
        <Notice tone="error" title="Backend is not reachable" detail={error ?? undefined} />
      )}

      <Card size="3">
        <DataList.Root>
          <DataList.Item>
            <DataList.Label>
              <Flex align="center" gap="2">
                Frontend build
                <InfoTip label="frontend build">Commit the browser bundle was built from.</InfoTip>
              </Flex>
            </DataList.Label>
            <DataList.Value>
              <Code variant="ghost">{__APP_SHA__}</Code>
            </DataList.Value>
          </DataList.Item>

          <DataList.Item>
            <DataList.Label>
              <Flex align="center" gap="2">
                Backend build
                <InfoTip label="backend build">
                  Commit the backend is running, read through the internal network.
                </InfoTip>
              </Flex>
            </DataList.Label>
            <DataList.Value>
              <Code variant="ghost">{backpy?.git_sha ?? "Unavailable"}</Code>
            </DataList.Value>
          </DataList.Item>

          <DataList.Item>
            <DataList.Label>Environment</DataList.Label>
            <DataList.Value>{backpy?.env ?? "Unavailable"}</DataList.Value>
          </DataList.Item>

          <DataList.Item>
            <DataList.Label>
              <Flex align="center" gap="2">
                Speech recognition key
                <InfoTip label="speech recognition key">
                  AssemblyAI key presence on the backend. The key itself never leaves the server.
                </InfoTip>
              </Flex>
            </DataList.Label>
            <DataList.Value>
              {backpy ? <KeyBadge present={backpy.configured.assemblyai} /> : "Unavailable"}
            </DataList.Value>
          </DataList.Item>

          <DataList.Item>
            <DataList.Label>
              <Flex align="center" gap="2">
                Voice output key
                <InfoTip label="voice output key">
                  Deepgram key presence on the backend. The key itself never leaves the server.
                </InfoTip>
              </Flex>
            </DataList.Label>
            <DataList.Value>
              {backpy ? <KeyBadge present={backpy.configured.deepgram} /> : "Unavailable"}
            </DataList.Value>
          </DataList.Item>
        </DataList.Root>
      </Card>
    </Flex>
  );
}
