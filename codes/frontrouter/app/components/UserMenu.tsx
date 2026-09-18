import { ExitIcon, HeartIcon, SpeakerLoudIcon } from "@radix-ui/react-icons";
import { Avatar, DropdownMenu, Flex, Text } from "@radix-ui/themes";
import { Link, useNavigate, useRevalidator } from "react-router";

export type ShellUser = { email: string; name: string; contributing: boolean };

function initials(user: ShellUser): string {
  const source = user.name.trim() || user.email;
  const parts = source.split(/[\s@._-]+/).filter(Boolean);
  return (parts[0]?.[0] ?? "?").concat(parts[1]?.[0] ?? "").toUpperCase();
}

// Top-right account menu. Signed-out visitors see a quiet sign-in link: signing in is
// only for people who choose to contribute.
export function UserMenu({ user }: { user: ShellUser | null }) {
  const navigate = useNavigate();
  const revalidator = useRevalidator();

  if (!user) {
    return (
      <Text asChild size="2" color="gray">
        <Link to="/contribute" className="sv-nav-link">
          Sign in
        </Link>
      </Text>
    );
  }

  const signOut = async () => {
    await fetch("/auth/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ signOut: true }),
    });
    navigate("/", { state: { fresh: true } });
    revalidator.revalidate();
  };

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger>
        <button type="button" className="sv-avatar-button" aria-label={`Account menu for ${user.email}`}>
          <Avatar size="2" radius="full" fallback={initials(user)} color="teal" variant="solid" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Content align="end" sideOffset={6}>
        <Flex direction="column" px="3" py="2" gap="1">
          {user.name && (
            <Text size="2" weight="medium">
              {user.name}
            </Text>
          )}
          <Text size="1" color="gray">
            {user.email}
          </Text>
          {user.contributing && (
            <Text size="1" color="jade">
              Contributing
            </Text>
          )}
        </Flex>
        <DropdownMenu.Separator />
        {user.contributing && (
          <DropdownMenu.Item asChild>
            <Link to="/contribute/session">
              <SpeakerLoudIcon /> Contribution session
            </Link>
          </DropdownMenu.Item>
        )}
        <DropdownMenu.Item asChild>
          <Link to="/contribute">
            <HeartIcon /> My contributions
          </Link>
        </DropdownMenu.Item>
        <DropdownMenu.Separator />
        <DropdownMenu.Item onSelect={signOut}>
          <ExitIcon /> Sign out
        </DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
}
