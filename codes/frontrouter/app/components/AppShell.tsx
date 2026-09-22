import { Box, Container, Flex, Text } from "@radix-ui/themes";
import { Link, NavLink } from "react-router";

import { type ShellUser, UserMenu } from "~/components/UserMenu";

const NAV = [
  { to: "/", label: "Bridge" },
  { to: "/contribute", label: "Contribute" },
  { to: "/benchmark", label: "Benchmark" },
];

export function AppShell({ children, user = null }: { children: React.ReactNode; user?: ShellUser | null }) {
  return (
    <div className="sv-page">
      <div className="sv-band" />
      <Box asChild className="sv-header" px="4" py="3">
        <header>
          <Container size="3">
            <Flex align="center" justify="between" gap="4" wrap="wrap">
              <Link to="/" state={{ fresh: true }} className="sv-brand">
                <Flex align="center" gap="3">
                  {/* Decorative: the product name sits right beside it. */}
                  <img src="/logo-synap.png" alt="" width={40} height={40} className="sv-brand-logo" />
                  <Flex direction="column">
                    <Text size="4" weight="bold">
                      SynapVocal
                    </Text>
                    <Text size="1" color="gray">
                      Realtime Voice Accessibility Bridge
                    </Text>
                  </Flex>
                </Flex>
              </Link>
              <Flex align="center" gap="5" wrap="wrap">
              <Flex asChild gap="5">
                <nav aria-label="Main">
                  {NAV.map((item) => (
                    <Text key={item.to} asChild size="3" weight="medium">
                      <NavLink to={item.to} end className="sv-nav-link">
                        {item.label}
                      </NavLink>
                    </Text>
                  ))}
                </nav>
              </Flex>
              <UserMenu user={user} />
              </Flex>
            </Flex>
          </Container>
        </header>
      </Box>
      <Container size="3" px="4" py="6" asChild>
        <main>{children}</main>
      </Container>
    </div>
  );
}
