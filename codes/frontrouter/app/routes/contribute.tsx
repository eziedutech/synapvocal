import { CheckIcon, TrashIcon } from "@radix-ui/react-icons";
import { AlertDialog, Badge, Button, Card, Checkbox, Flex, Heading, Text } from "@radix-ui/themes";
import { useState } from "react";
import { data, Form, Link, useNavigation, useRevalidator } from "react-router";

import type { Route } from "./+types/contribute";
import { Notice } from "~/components/Notice";
import { BackpyError } from "~/lib/backpy.server";
import { CONSENT_SECTIONS, CONSENT_VERSION } from "~/lib/contrib/consent";
import { contrib, contributionsConfigured, type ContributionView, type Me } from "~/lib/contrib/contrib.server";
import { firebasePublicConfig } from "~/lib/contrib/firebase.server";
import { getUserId, sessionConfigured, signOut } from "~/lib/session.server";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "Contribute - SynapVocal" },
    { name: "description", content: "Voluntarily contribute recordings to help speech recognition understand more voices." },
  ];
}

export async function loader({ request }: Route.LoaderArgs) {
  const firebase = firebasePublicConfig();
  const available = Boolean(firebase) && sessionConfigured() && contributionsConfigured();
  const userId = available ? await getUserId(request) : null;
  if (!userId) return { available, firebase, me: null as Me | null, contributions: [] as ContributionView[] };
  try {
    const [me, contributions] = await Promise.all([contrib.me(userId), contrib.list(userId)]);
    return { available, firebase, me, contributions };
  } catch (error) {
    // The account may have been deleted elsewhere: forget the cookie rather than loop on errors.
    console.warn("[contribute] could not load account", error instanceof Error ? error.message : error);
    return data(
      { available, firebase, me: null as Me | null, contributions: [] as ContributionView[] },
      { headers: { "Set-Cookie": await signOut(request) } },
    );
  }
}

export async function action({ request }: Route.ActionArgs) {
  const userId = await getUserId(request);
  if (!userId) return { error: "Sign in first." };
  const form = await request.formData();
  const intent = form.get("intent");
  try {
    if (intent === "consent") {
      if (form.get("adult") !== "on" || form.get("agree") !== "on") return { error: "Please tick both boxes to continue." };
      await contrib.consent(userId, CONSENT_VERSION);
    } else if (intent === "withdraw") {
      await contrib.withdraw(userId, form.get("delete") === "on");
    } else if (intent === "delete-one") {
      await contrib.remove(userId, String(form.get("id")));
    } else if (intent === "delete-account") {
      await contrib.deleteAccount(userId);
      return data({ error: null }, { headers: { "Set-Cookie": await signOut(request) } });
    } else if (intent === "sign-out") {
      return data({ error: null }, { headers: { "Set-Cookie": await signOut(request) } });
    }
    return { error: null };
  } catch (error) {
    return { error: error instanceof BackpyError ? (error.detail ?? error.message) : "Something went wrong. Please try again." };
  }
}

function SignIn({ firebase }: { firebase: NonNullable<Route.ComponentProps["loaderData"]["firebase"]> }) {
  const revalidator = useRevalidator();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const signInWithGoogle = async () => {
    setBusy(true);
    setError(null);
    try {
      const { googleIdToken } = await import("~/lib/contrib/firebase.client");
      const idToken = await googleIdToken(firebase);
      const response = await fetch("/auth/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idToken }),
      });
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "Sign-in failed");
      revalidator.revalidate();
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      // Closing the popup is a choice, not an error worth shouting about.
      if (!message.includes("popup-closed-by-user") && !message.includes("cancelled-popup-request")) setError(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Flex direction="column" align="start" gap="3">
      <Text size="3">Sign in first, then read what contributing means before deciding.</Text>
      <Button size="3" onClick={signInWithGoogle} loading={busy}>
        Sign in with Google
      </Button>
      {error && <Notice tone="error" title="Could not sign in" detail={error} />}
    </Flex>
  );
}

function ConsentText() {
  return (
    <Flex direction="column" gap="4">
      {CONSENT_SECTIONS.map((section) => (
        <Flex key={section.title} direction="column" gap="2">
          <Heading as="h3" size="3">
            {section.title}
          </Heading>
          <ul className="sv-consent-list">
            {section.points.map((point) => (
              <li key={point}>
                <Text size="2">{point}</Text>
              </li>
            ))}
          </ul>
        </Flex>
      ))}
      <Text size="1" color="gray">
        Consent version {CONSENT_VERSION}
      </Text>
    </Flex>
  );
}

function ConsentForm({ busy }: { busy: boolean }) {
  const [adult, setAdult] = useState(false);
  const [agree, setAgree] = useState(false);
  return (
    <Form method="post">
      <input type="hidden" name="intent" value="consent" />
      <Flex direction="column" gap="3">
        <Text as="label" size="2">
          <Flex gap="2" align="start">
            <Checkbox name="adult" checked={adult} onCheckedChange={(v) => setAdult(v === true)} />
            I am 18 or older.
          </Flex>
        </Text>
        <Text as="label" size="2">
          <Flex gap="2" align="start">
            <Checkbox name="agree" checked={agree} onCheckedChange={(v) => setAgree(v === true)} />
            I have read the above and agree to contribute recordings I choose, for the purposes described.
          </Flex>
        </Text>
        <Flex gap="3" wrap="wrap">
          <Button size="3" type="submit" disabled={!adult || !agree} loading={busy}>
            I agree, let me contribute
          </Button>
        </Flex>
      </Flex>
    </Form>
  );
}

function Contributions({ items }: { items: ContributionView[] }) {
  if (items.length === 0) {
    return <Text color="gray">Nothing yet. Start a contribution session, confirm a sentence, then choose Contribute.</Text>;
  }
  return (
    <ul className="sv-sentences">
      {items.map((item) => (
        <li key={item.id} className="sv-contribution">
          <Flex align="center" justify="between" gap="3">
            <Flex direction="column" gap="1">
              <Text size="3">{item.confirmed_text}</Text>
              <Flex gap="2" align="center">
                <Text size="1" color="gray">
                  {new Date(item.created_at).toLocaleString()} · {(item.duration_ms / 1000).toFixed(1)} s
                </Text>
                {item.exact && (
                  <Badge color="jade" variant="soft" size="1">
                    <CheckIcon /> Exactly what I said
                  </Badge>
                )}
              </Flex>
            </Flex>
            <Form method="post">
              <input type="hidden" name="intent" value="delete-one" />
              <input type="hidden" name="id" value={item.id} />
              <Button type="submit" size="2" variant="soft" color="gray" aria-label={`Delete "${item.confirmed_text}"`}>
                <TrashIcon /> Delete
              </Button>
            </Form>
          </Flex>
        </li>
      ))}
    </ul>
  );
}

function Manage({ me }: { me: Me }) {
  return (
    <Flex gap="3" wrap="wrap">
      <AlertDialog.Root>
        <AlertDialog.Trigger>
          <Button variant="soft" color="gray">
            Withdraw consent
          </Button>
        </AlertDialog.Trigger>
        <AlertDialog.Content maxWidth="460px">
          <Form method="post">
            <input type="hidden" name="intent" value="withdraw" />
            <AlertDialog.Title>Withdraw consent?</AlertDialog.Title>
            <AlertDialog.Description size="2">
              You will not be asked to contribute again unless you agree again. You can also delete everything you
              have contributed so far.
            </AlertDialog.Description>
            <Text as="label" size="2" mt="3">
              <Flex gap="2" mt="3">
                <Checkbox name="delete" defaultChecked />
                Also delete my {me.contributions} contributed recording{me.contributions === 1 ? "" : "s"}
              </Flex>
            </Text>
            <Flex gap="3" mt="4" justify="end">
              <AlertDialog.Cancel>
                <Button variant="soft" color="gray">
                  Cancel
                </Button>
              </AlertDialog.Cancel>
              <AlertDialog.Action>
                <Button type="submit" color="tomato">
                  Withdraw
                </Button>
              </AlertDialog.Action>
            </Flex>
          </Form>
        </AlertDialog.Content>
      </AlertDialog.Root>

      <AlertDialog.Root>
        <AlertDialog.Trigger>
          <Button variant="soft" color="tomato">
            Delete my account
          </Button>
        </AlertDialog.Trigger>
        <AlertDialog.Content maxWidth="460px">
          <Form method="post">
            <input type="hidden" name="intent" value="delete-account" />
            <AlertDialog.Title>Delete your account and all data?</AlertDialog.Title>
            <AlertDialog.Description size="2">
              Every recording, sentence and consent record linked to {me.email} is deleted permanently. This cannot be
              undone.
            </AlertDialog.Description>
            <Flex gap="3" mt="4" justify="end">
              <AlertDialog.Cancel>
                <Button variant="soft" color="gray">
                  Keep my account
                </Button>
              </AlertDialog.Cancel>
              <AlertDialog.Action>
                <Button type="submit" color="tomato">
                  Delete everything
                </Button>
              </AlertDialog.Action>
            </Flex>
          </Form>
        </AlertDialog.Content>
      </AlertDialog.Root>
    </Flex>
  );
}

export default function Contribute({ loaderData, actionData }: Route.ComponentProps) {
  const { available, firebase, me, contributions } = loaderData;
  const navigation = useNavigation();
  const busy = navigation.state !== "idle";
  const consented = Boolean(me?.consent);

  return (
    <Flex direction="column" gap="5">
      <Flex direction="column" gap="2">
        <Heading size="7">Contribute your voice</Heading>
        <Text size="3" color="gray">
          Optional. If you choose to, you can give recordings of sentences you confirm on the Bridge, so speech
          recognition can learn to understand voices like yours. The Bridge works the same whether or not you do.
        </Text>
      </Flex>

      {actionData?.error && <Notice tone="error" title="That did not work" detail={actionData.error} />}

      {!available || !firebase ? (
        <Notice tone="info" title="Not available here" detail="Contributions are not set up on this server." />
      ) : !me ? (
        <Card size="3">
          <Flex direction="column" gap="5">
            <ConsentText />
            <SignIn firebase={firebase} />
          </Flex>
        </Card>
      ) : !consented ? (
        <Card size="3">
          <Flex direction="column" gap="5">
            <Text size="2" color="gray">
              Signed in as {me.email}
            </Text>
            <ConsentText />
            <ConsentForm busy={busy} />
          </Flex>
        </Card>
      ) : (
        <>
          <Card size="3">
            <Flex direction="column" gap="3">
              <Flex align="center" gap="2" wrap="wrap">
                <Badge color="jade" variant="soft" size="2">
                  <CheckIcon /> Contributing
                </Badge>
                <Text size="2" color="gray">
                  {me.email} · consent given {new Date(me.consent!.accepted_at).toLocaleDateString()}
                </Text>
              </Flex>
              <Text size="3">
                Recordings are only collected in a <strong>contribution session</strong>, never on the ordinary Bridge.
                After you confirm a sentence there, you choose whether to contribute it.
              </Text>
              <Flex>
                <Button size="3" asChild>
                  <Link to="/contribute/session">Start a contribution session</Link>
                </Button>
              </Flex>
            </Flex>
          </Card>

          <Card size="3">
            <Flex direction="column" gap="3">
              <Heading as="h2" size="4">
                Your contributions ({contributions.length})
              </Heading>
              <Contributions items={contributions} />
            </Flex>
          </Card>

          <Card size="3">
            <Flex direction="column" gap="3">
              <Heading as="h2" size="4">
                Your choices
              </Heading>
              <Manage me={me} />
            </Flex>
          </Card>
        </>
      )}

    </Flex>
  );
}
