/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import { useState } from "react";
import { Box, Card, CardContent, Tab, Tabs, Typography } from "@mui/material";
import SnakeGame from "@/components/games/SnakeGame";
import SpaceInvaders from "@/components/games/SpaceInvaders";
import BreakoutGame from "@/components/games/BreakoutGame";
import LeaderboardTab from "@/components/games/LeaderboardTab";

type GamesTab = "snake" | "invaders" | "breakout" | "leaderboard";

const TABS: Array<{ id: GamesTab; label: string }> = [
  { id: "snake", label: "Snake" },
  { id: "invaders", label: "Invaders" },
  { id: "breakout", label: "Breakout" },
  { id: "leaderboard", label: "Leaderboard" },
];

export default function GamesPage() {
  const [tab, setTab] = useState<GamesTab>("snake");

  return (
    <Box sx={{ maxWidth: 1200, mx: "auto", py: 4, px: 3 }}>
      <Typography variant="h5" component="h1" sx={{ fontWeight: 700, mb: 1 }}>
        Games
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Arcade games and score leaderboard are hosted here as a dedicated top-level area.
      </Typography>

      <Card>
        <CardContent sx={{ p: 2 }}>
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v as GamesTab)}
            sx={{ mb: 2 }}
          >
            {TABS.map((t) => (
              <Tab key={t.id} value={t.id} label={t.label} />
            ))}
          </Tabs>

          {tab === "snake" && <SnakeGame />}
          {tab === "invaders" && <SpaceInvaders />}
          {tab === "breakout" && <BreakoutGame />}
          {tab === "leaderboard" && <LeaderboardTab />}
        </CardContent>
      </Card>
    </Box>
  );
}
