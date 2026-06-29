# Example Questions

This file lists example questions supported by the IPL SQL Agent.

---

## Batting Leaderboards

```text
top 10 run scorers in 2026
top 10 run scorers in 2018
who are top 10 run scorers for CSK in 2026
top 10 run scorers at Wankhede
top 10 run scorers in Wankhede
who has the most runs at Wankhede
Wankhede top 10 run scorers
```

---

## Bowling Leaderboards

```text
top 10 wicket takers in 2026
who are the top 10 wicket takers in IPL
top 10 wicket takers for CSK in 2026
top 10 wicket takers at Wankhede
top 10 wicket takers in Wankhede
who has the most wickets at Wankhede
```

---

## Fastest Milestones

```text
who has the fastest 50 in IPL history
who has the fastest 100 in IPL history
fastest 50 for CSK
fastest 100 in 2026
```

---

## Player Profiles

```text
analyse Bumrah
analyse Kohli
analyse Narine
profile Rohit
tell me about Dhoni
```

Player profiles include:

- Batting summary
- Bowling summary
- Batting season trend
- Bowling season trend

---

## Fifties and Hundreds

```text
how many fifties does Kohli have
how many hundreds does Kohli have
how many fifties does Kohli have against CSK
how many hundreds does Kohli have against CSK
how many fifties does Kohli have at Wankhede
how many hundreds does Kohli have against MI in 2018
```

---

## Wickets Against Teams

```text
who has taken the most wickets against CSK
who has taken the most wickets against MI
top 10 wicket takers against RCB
who has taken the most wickets against CSK in 2026
who has taken the most wickets against RCB at Wankhede
```

---

## Team Analytics

```text
who has won the most trophies
which team has the best win percentage
who are top 10 run scorers for CSK in 2026
top 10 wicket takers for CSK in 2026
```

---

## Venue Analysis

```text
venue profile for Wankhede
top 10 run scorers at Wankhede
top 10 wicket takers at Wankhede
who has the most runs in Wankhede
who has the most wickets in Wankhede
```

---

## Tactical Questions

```text
how can GT beat RR at Narendra Modi Stadium
analyse squad for CSK
tactical matchups for GT vs RR
best bowlers against Kohli for Delhi Capitals
best bowlers against Gaikwad for KKR
```

---

## Ambiguous Team Names

The agent treats `DC` as ambiguous because it can mean:

- Delhi Capitals
- Deccan Chargers

For these questions, use the full name.

Example:

```text
best bowlers against Kohli for Delhi Capitals
```

instead of:

```text
best bowlers against Kohli for dc
```
