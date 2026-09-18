import { Card, Flex, Heading, SegmentedControl, Text } from "@radix-ui/themes";
import { useState } from "react";

import { InfoTip } from "~/components/InfoTip";

// Every chart has a table twin, so no value is reachable only by hovering.
export function ChartCard({
  title,
  about,
  caption,
  chart,
  table,
}: {
  title: string;
  about: string;
  caption?: string;
  chart: React.ReactNode;
  table: React.ReactNode;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  return (
    <Card size="3" asChild>
      <figure className="sv-chart-card">
        <Flex direction="column" gap="4">
          <Flex align="center" justify="between" gap="3" wrap="wrap">
            <Flex align="center" gap="2">
              <Heading as="h2" size="4">
                {title}
              </Heading>
              <InfoTip label={title}>{about}</InfoTip>
            </Flex>
            <SegmentedControl.Root
              size="1"
              value={view}
              onValueChange={(value) => setView(value as "chart" | "table")}
              aria-label={`${title} view`}
            >
              <SegmentedControl.Item value="chart">Chart</SegmentedControl.Item>
              <SegmentedControl.Item value="table">Table</SegmentedControl.Item>
            </SegmentedControl.Root>
          </Flex>
          {view === "chart" ? chart : table}
          {caption && (
            <Text as="p" size="2" color="gray" asChild>
              <figcaption>{caption}</figcaption>
            </Text>
          )}
        </Flex>
      </figure>
    </Card>
  );
}
