import { PlayIcon } from "@radix-ui/react-icons";
import { Badge, Button, Dialog, Flex, Text } from "@radix-ui/themes";

import examples from "~/data/torgoExamples.json";

export type TorgoExample = (typeof examples)[number];

const SEVERITY: Record<string, { label: string; color: "tomato" | "amber" | "jade" }> = {
  severe: { label: "Severe", color: "tomato" },
  moderate: { label: "Moderate", color: "amber" },
  mild: { label: "Mild", color: "jade" },
};

// Nine TORGO sentences from speakers with dysarthria, chosen from the benchmark where the
// app's first suggestion was exactly right. Each shows what happened in the benchmark;
// a live run can differ, and the benchmark page gives the rate over all 681 sentences.
export function TorgoExamples({ trigger, onPick }: { trigger: React.ReactNode; onPick: (example: TorgoExample) => void }) {
  return (
    <Dialog.Root>
      <Dialog.Trigger>{trigger}</Dialog.Trigger>
      <Dialog.Content maxWidth="640px">
        <Dialog.Title>TORGO examples</Dialog.Title>
        <Dialog.Description size="2" color="gray">
          Real recordings of speakers with dysarthria. Each plays aloud and goes through the same steps as your
          microphone. These are sentences the benchmark got right; across all 681 sentences the rate is lower, see
          Benchmark.
        </Dialog.Description>
        <Flex direction="column" gap="3" mt="4">
          {examples.map((example) => {
            const severity = SEVERITY[example.severity];
            return (
              <Flex key={example.id} align="center" justify="between" gap="3" className="sv-example">
                <Flex direction="column" gap="1">
                  <Flex align="center" gap="2">
                    <Badge color={severity.color} variant="soft">
                      {severity.label}
                    </Badge>
                    <Text size="1" color="gray">
                      Speaker {example.speaker} · {example.seconds.toFixed(1)} s
                    </Text>
                  </Flex>
                  <Text size="3" weight="medium">
                    {example.reference}
                  </Text>
                  <Text size="1" color="gray">
                    Benchmark: AssemblyAI heard "{example.benchmark_heard}"
                  </Text>
                </Flex>
                <Dialog.Close>
                  <Button size="2" variant="soft" onClick={() => onPick(example)} aria-label={`Play and recognise: ${example.reference}`}>
                    <PlayIcon /> Use
                  </Button>
                </Dialog.Close>
              </Flex>
            );
          })}
        </Flex>
        <Text as="p" size="1" color="gray" mt="4">
          Recordings from the TORGO database, used for academic, non-profit purposes: Rudzicz, F., Namasivayam, A.K.,
          Wolff, T. (2012). The TORGO database of acoustic and articulatory speech from speakers with dysarthria.
          Language Resources and Evaluation, 46(4), 523 to 541.
        </Text>
        <Flex justify="end" mt="3">
          <Dialog.Close>
            <Button variant="soft" color="gray">
              Close
            </Button>
          </Dialog.Close>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}
