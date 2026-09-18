import { useState } from "react";
import { Link } from "react-router";
import { AlertDialog, Badge, Button, Card, Flex, Grid, Heading, Skeleton, Text } from "@radix-ui/themes";

import { ContributePanel } from "~/components/ContributePanel";
import { InfoTip } from "~/components/InfoTip";
import { Notice } from "~/components/Notice";
import { SentenceCard } from "~/components/SentenceCard";
import { VoiceOrb } from "~/components/VoiceOrb";
import { useSentences } from "~/lib/bridge/useSentences";
import { useSpeech } from "~/lib/bridge/useSpeech";
import { useMicPermission } from "~/lib/stt/useMicPermission";
import { type SttStatus, useRealtimeTranscription } from "~/lib/stt/useRealtimeTranscription";
import { cleanForDisplay } from "~/lib/text";

// The Bridge and a contribution session share this workspace. Both send each sentence's
// audio to Gemini to interpret it, and neither stores it. They differ on purpose and
// visibly: only a contribution session offers "Contribute" to save a recording.
export type BridgeMode = "bridge" | "contribute";

const STATUS_LABEL: Record<SttStatus, { text: string; color: "gray" | "teal" | "amber" | "tomato" }> = {
  idle: { text: "Not listening", color: "gray" },
  connecting: { text: "Connecting", color: "amber" },
  listening: { text: "Listening", color: "teal" },
  stopping: { text: "Stopping", color: "amber" },
  error: { text: "Stopped with an error", color: "tomato" },
};

type Intro = { heading: [string, string]; lead: string; steps: { title: string; text: string }[]; note: string };

const INTRO: Record<BridgeMode, Intro> = {
  bridge: {
    heading: ["Speak in your own way.", "SynapVocal helps others understand."],
    lead: "A real-time voice bridge for people whose speech is hard for others to understand: people with dysarthria, and people speaking with Parkinson's disease, ALS, cerebral palsy, Down syndrome or after a stroke.",
    steps: [
      { title: "Speak", text: "Press Start, allow the microphone and say one sentence." },
      { title: "Choose", text: "Pick what was heard or a suggestion, and edit it if needed." },
      { title: "Confirm and speak", text: "Your sentence is said out loud in a clear voice." },
    ],
    note: "Nothing is spoken until you confirm. Audio is not stored. English only for now.",
  },
  contribute: {
    heading: ["Contribution session.", "Help speech recognition hear voices like yours."],
    lead: "This works like the Bridge. The difference: after you confirm a sentence, you can choose to contribute its recording.",
    steps: [
      { title: "Speak", text: "Press Start and say one sentence, as you normally would." },
      { title: "Confirm", text: "Choose or edit the sentence until it is what you meant." },
      { title: "Contribute or skip", text: "Save that one recording to your contributions, or skip it." },
    ],
    note: "Only sentences you contribute are saved. You can delete them any time. English only for now.",
  },
};

export function BridgeView({ mode }: { mode: BridgeMode }) {
  const contributing = mode === "contribute";
  const intro = INTRO[mode];
  const { status, turns, sessionId, analyser, error, start, stop, endTurn, getTurnAudio, forgetTurnAudio } =
    useRealtimeTranscription({ keepAudio: true });
  const { sentences, confirm, retry, clear, sayAgain, awaitingRetake } = useSentences(turns, sessionId, getTurnAudio);
  const speech = useSpeech();
  const active = status === "listening";
  const busy = status === "connecting" || status === "stopping";
  const current = [...turns].reverse().find((turn) => !turn.final);
  const label = STATUS_LABEL[status];
  const mic = useMicPermission();
  // The introduction is for someone arriving; it goes for good once they start listening.
  const [started, setStarted] = useState(false);
  const beginListening = () => {
    setStarted(true);
    start();
  };

  return (
    // No gap here: collapsed intro parts would still leave gaps behind. Spacing sits on the parts that stay.
    <Flex direction="column">
      {/* The introduction collapses upward on start, so the console below it slides into place. */}
      <div className={`sv-collapse${started ? " is-closed" : ""}`} aria-hidden={started || undefined}>
        <div className="sv-collapse-inner">
          <Flex direction="column" align="center" gap="8" className="sv-intro">
            <Flex direction="column" align="center" gap="4">
              {contributing && (
                <Badge size="2" color="amber" variant="soft">
                  Contribution session
                </Badge>
              )}
              <Heading as="h2" size="8" align="center">
                {intro.heading[0]}
                <br />
                {intro.heading[1]}
              </Heading>
              <Text size="4" color="gray" align="center" className="sv-intro-lead">
                {intro.lead}
              </Text>
            </Flex>
            <Grid columns={{ initial: "1", sm: "3" }} gap="6" width="100%" className="sv-intro-steps">
              {intro.steps.map((step) => (
                <Flex key={step.title} direction="column" align="center" gap="2">
                  <Text size="3" weight="bold" align="center">
                    {step.title}
                  </Text>
                  <Text size="2" color="gray" align="center">
                    {step.text}
                  </Text>
                </Flex>
              ))}
            </Grid>
          </Flex>
        </div>
      </div>

      {/* One console for both views: centred and borderless on arrival, a sticky bar while in use. */}
      <section
        className={`sv-console${started ? " is-live" : ""}${contributing ? " is-contribute" : ""}`}
        aria-label={contributing ? "Contribution session controls" : "Listening controls"}
      >
        <div className="sv-console-orb">
          <VoiceOrb
            analyser={analyser}
            mode={active ? "active" : busy ? "busy" : "idle"}
            label={started ? "Microphone level" : "Microphone, not listening yet"}
          />
          {started && (
            <Badge size="2" color={label.color} variant="soft" aria-live="polite">
              {label.text}
            </Badge>
          )}
          {started && contributing && (
            <Badge size="2" color="amber" variant="soft">
              Contribution session
            </Badge>
          )}
        </div>
        <Flex gap="3" wrap="wrap" align="center" justify="center">
          {active || busy ? (
            <Button size="4" color="gray" variant="soft" onClick={stop} disabled={busy} aria-label="Stop listening">
              Stop
            </Button>
          ) : (
            <Button size="4" onClick={beginListening} aria-label={started ? "Start listening again" : "Start listening"}>
              {started ? "Start again" : "Start"}
            </Button>
          )}
          {/* Hidden while listening: leaving the page would end the session mid-sentence. */}
          {!active && !busy && (
            <Button size="4" variant="outline" asChild>
              <Link to="/contribute">{contributing ? "My contributions" : "Contribute"}</Link>
            </Button>
          )}
          {started && (
            <Flex align="center" gap="2">
              <Button size="4" variant="outline" onClick={endTurn} disabled={!active}>
                End sentence
              </Button>
              <InfoTip label="End sentence">
                Ends your sentence now instead of waiting for a pause to be detected. The microphone stays on, so
                you can say the next sentence straight away.
              </InfoTip>
            </Flex>
          )}
        </Flex>
        {mic === "denied" ? (
          <Text size="2" color="tomato" align="center" className="sv-console-hint" role="status">
            The microphone is blocked for this site. Allow it from the icon at the left of the address bar, then press
            Start{started ? " again" : ""}.
          </Text>
        ) : (
          !started &&
          mic === "prompt" && (
            <Text size="2" color="gray" align="center" className="sv-console-hint">
              Your browser will ask to use the microphone once.
            </Text>
          )
        )}
      </section>

      <div className={`sv-collapse${started ? " is-closed" : ""}`} aria-hidden={started || undefined}>
        <div className="sv-collapse-inner">
          <Text as="p" size="1" color="gray" align="center" className="sv-intro-note">
            {intro.note}
          </Text>
        </div>
      </div>

      {error && (
        <div className="sv-stack-gap">
          <Notice tone="error" title="Listening stopped" detail={error} />
        </div>
      )}

      {started && (
        <Flex direction="column" gap="5" className="sv-reveal sv-stack-gap">
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
                    {current?.text ? cleanForDisplay(current.text) : active ? "Speak when you are ready." : "Press Start again to continue."}
                  </Text>
                )}
              </div>
            </Flex>
          </Card>

          <Card size="3">
            <Flex direction="column" gap="3">
              <Flex align="center" justify="between" gap="3">
                <Flex align="center" gap="2">
                  <Heading as="h2" size="4">
                    Sentences
                  </Heading>
                  <InfoTip label="sentences">
                    Each sentence you finish, with suggestions for what you meant. Pick one, edit it, then confirm.
                    Newest first.
                  </InfoTip>
                </Flex>
                <AlertDialog.Root>
                  <AlertDialog.Trigger>
                    <Button size="2" color="gray" variant="soft" disabled={sentences.length === 0}>
                      Clear sentences
                    </Button>
                  </AlertDialog.Trigger>
                  <AlertDialog.Content maxWidth="420px">
                    <AlertDialog.Title>Clear all sentences?</AlertDialog.Title>
                    <AlertDialog.Description size="2">
                      This removes every sentence on this page and starts a fresh conversation, so earlier sentences
                      no longer guide the suggestions. It cannot be undone.
                    </AlertDialog.Description>
                    <Flex gap="3" mt="4" justify="end">
                      <AlertDialog.Cancel>
                        <Button variant="soft" color="gray">
                          Keep them
                        </Button>
                      </AlertDialog.Cancel>
                      <AlertDialog.Action>
                        <Button
                          color="tomato"
                          onClick={() => {
                            speech.stop();
                            forgetTurnAudio();
                            clear();
                          }}
                        >
                          Clear sentences
                        </Button>
                      </AlertDialog.Action>
                    </Flex>
                  </AlertDialog.Content>
                </AlertDialog.Root>
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
                        onConfirm={(text, source) => {
                          confirm(sentence.key, text, source);
                          speech.speak(sentence.key, text);
                        }}
                        onRetry={() => retry(sentence.key)}
                        onSpeak={(text) => speech.speak(sentence.key, text)}
                        awaitingRetake={awaitingRetake === sentence.key}
                        onSayAgain={(on) => sayAgain(on ? sentence.key : null)}
                        contribute={
                          contributing && (
                            <ContributePanel
                              sentence={sentence}
                              audio={getTurnAudio(sentence.key)}
                              onDone={() => forgetTurnAudio(sentence.key)}
                            />
                          )
                        }
                      />
                    ))}
                  </ol>
                </Flex>
              )}
            </Flex>
          </Card>
        </Flex>
      )}
    </Flex>
  );
}
