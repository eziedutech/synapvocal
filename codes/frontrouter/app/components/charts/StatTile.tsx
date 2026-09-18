import { Card, Flex, Text } from "@radix-ui/themes";

import { InfoTip } from "~/components/InfoTip";

export function StatTile({ label, value, context, about }: { label: string; value: string; context: string; about: string }) {
  return (
    <Card size="2">
      <Flex direction="column" gap="1">
        <Flex align="center" gap="2">
          <Text size="2" color="gray">
            {label}
          </Text>
          <InfoTip label={label}>{about}</InfoTip>
        </Flex>
        <Text size="5" weight="bold">
          {value}
        </Text>
        <Text size="1" color="gray">
          {context}
        </Text>
      </Flex>
    </Card>
  );
}
