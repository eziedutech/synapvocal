import { Box, Container, Flex, Text } from "@radix-ui/themes";
import { Link, NavLink } from "react-router";

const NAV = [
  { to: "/", label: "Bridge" },
  { to: "/status", label: "Status" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="sv-page">
      <div className="sv-band" />
      <Box asChild className="sv-header" px="4" py="3">
        <header>
          <Container size="3">
            <Flex align="center" justify="between" gap="4" wrap="wrap">
              <Flex direction="column">
                <Text asChild size="4" weight="bold">
                  <Link to="/" style={{ color: "inherit", textDecoration: "none" }}>
                    SynapVocal
                  </Link>
                </Text>
                <Text size="1" color="gray">
                  Realtime Voice Accessibility Bridge
                </Text>
              </Flex>
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
