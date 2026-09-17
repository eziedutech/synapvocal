import { Badge, Button, Card, Flex, Heading, Skeleton, Text } from "@radix-ui/themes";

import type { Route } from "./+types/bridge";
import { InfoTip } from "~/components/InfoTip";
import { SentenceCard } from "~/components/SentenceCard";
import { VoiceOrb } from "~/components/VoiceOrb";
import { Notice } from "~/components/Notice";
import { useSentences } from "~/lib/bridge/useSentences";
import { useSpeech } from "~/lib/bridge/useSpeech";
import { type SttStatus, useRealtimeTranscription } from "~/lib/stt/useRealtimeTranscription";
import { cleanForDisplay } from "~/lib/text";

export function meta({}: Route.MetaArgs) {
  return [{ title: "SynapVocal" }];
}

const STATUS_LABEL: Record<SttStatus, { text: string; color: "gray" | "teal" | "amber" | "tomato" }> = {
  idle: { text: "Not listening", color: "gray" },
  connecting: { text: "Connecting", color: "amber" },
  listening: { text: "Listening", color: "teal" },
  stopping: { text: "Stopping", color: "amber" },
  error: { text: "Stopped with an error", color: "tomato" },
};

export default function Bridge() {
  const { status, turns, sessionId, analyser, error, start, stop, endTurn } = useRealtimeTranscription();
  const { sentences, confirm, retry } = useSentences(turns, sessionId);
  const speech = useSpeech();
  const active = status === "listening";
  const busy = status === "connecting" || status === "stopping";
  const current = [...turns].reverse().find((turn) => !turn.final);
  const label = STATUS_LABEL[status];

  return (
    <Flex direction="column" gap="5">
      <Heading size="7">Bridge</Heading>

      {error && <Notice tone="error" title="Listening stopped" detail={error} />}

      <Card size="3">
        <Flex align="center" justify="between" wrap="wrap" gap="5">
          <Flex align="center" gap="4">
            <VoiceOrb
              analyser={analyser}
              mode={active ? "active" : busy ? "busy" : "idle"}
              label="Microphone level"
            />
            <Badge size="2" color={label.color} variant="soft" aria-live="polite">
              {label.text}
            </Badge>
          </Flex>
          <Flex gap="3" wrap="wrap" align="center">
            {active || busy ? (
              <Button size="4" color="gray" variant="soft" onClick={stop} disabled={busy}>
                Stop listening
              </Button>
            ) : (
              <Button size="4" onClick={start}>
                Start listening
              </Button>
            )}
            <Flex align="center" gap="2">
              <Button size="4" variant="outline" onClick={endTurn} disabled={!active}>
                I'm done speaking
              </Button>
              <InfoTip label="I'm done speaking">
                Ends your sentence now instead of waiting for a pause to be detected. Useful when
                you pause in the middle of speaking.
              </InfoTip>
            </Flex>
          </Flex>
        </Flex>
      </Card>

      <Card size="3">
        <Flex direction="column" gap="3">
          <Flex align="center" gap="2">
            <Heading as="h2" size="4">
              Hearing now
            </Heading>
            <InfoTip label="hearing now">
              What speech recognition hears while you speak. It may change until the sentence ends.
            </InfoTip>
          </Flex>
          <div aria-live="polite">
            {status === "connecting" ? (
              <Skeleton>
                <Text size="6">Waiting for the first words to arrive</Text>
              </Skeleton>
            ) : (
              <Text size="6" color={current?.text ? undefined : "gray"}>
                {current?.text ? cleanForDisplay(current.text) : active ? "Speak when you are ready." : "Start listening to begin."}
              </Text>
            )}
          </div>
        </Flex>
      </Card>

      <Card size="3">
        <Flex direction="column" gap="3">
          <Flex align="center" gap="2">
            <Heading as="h2" size="4">
              Sentences
            </Heading>
            <InfoTip label="sentences">
              Each sentence you finish, with suggestions for what you meant. Pick one, edit it, then confirm.
              Newest first.
            </InfoTip>
          </Flex>
          {sentences.length === 0 ? (
            <Text color="gray">No finished sentences yet.</Text>
          ) : (
            <Flex direction="column" gap="3" asChild>
              <ol className="sv-sentences">
                {[...sentences].reverse().map((sentence) => (
                  <SentenceCard
                    key={sentence.key}
                    sentence={sentence}
                    speech={speech.state?.key === sentence.key ? speech.state : null}
                    onConfirm={(text) => {
                      confirm(sentence.key, text);
                      speech.speak(sentence.key, text);
                    }}
                    onRetry={() => retry(sentence.key)}
                    onSpeak={(text) => speech.speak(sentence.key, text)}
                  />
                ))}
              </ol>
            </Flex>
          )}
        </Flex>
      </Card>
    </Flex>
  );
}
