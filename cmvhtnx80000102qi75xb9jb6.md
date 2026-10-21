---
title: "AI-Driven Development Is a Diagnostic for Your Organization"
seoTitle: "AI-Driven Development: 3 Places the Constraint Moves"
seoDescription: "AI made producing faster. In three accounts, the constraint moved to work AI cannot do alone: the objective, the context, and the capacity to verify."
datePublished: 2026-10-21T08:00:12.537Z
cuid: cmvhtnx80000102qi75xb9jb6
slug: ai-driven-development-is-a-diagnostic-for-your-organization
ogImage: https://cdn.hashnode.com/uploads/og-images/69d1f25c6792e486f60903fd/c1f6b74a-4cd1-4b3f-8023-5bc5ba38ba0e.png
tags: software-development, devops, developer-experience, engineering-management, ai-driven-development

---

AI-driven development does make much of the development process faster. It does not remove the constraint, the bottleneck in that process. The constraint moves instead, and where it lands shows whether the organization was ready there or already thin before any agent arrived. That makes the speedup itself a diagnostic for an organization adopting AI.

Three companies published accounts this year that show where the constraint landed, two of them Japanese digital enterprises my team works alongside. At ASKUL Corporation, rebuilding after a major system incident, the then-CEO set the target past full recovery, as he explained in [his own AWS Summit Japan session](https://pages.awscloud.com/rs/112-TZM-766/images/R14_0626_3_AIM146_v2.pdf) (in Japanese). At LY Corporation, a principal architect [told a conference](https://speakerdeck.com/lycorptech_jp/yahoo-shopping-ai-dlc-initiative) (in Japanese) that generative AI had surfaced weaknesses the organization already had: authoritative documents that could not be maintained, API specifications whose location was unclear, a habit of finding the person who knew. The third, [Spotify](https://engineering.atspotify.com/2026/9/ai-changed-how-spotify-builds-what-we-learned-and-fixed-about-quality-at-higher-velocity), is not a company my team works with. It merged roughly 17,000 changes in August, up from about 8,100 a year earlier, and found that the volume of change had grown faster than some of its verification controls could adapt.

The three accounts put the constraint in three different places. Before the work starts, it moved to the objective: what the work is for. During the work, it moved to the context the agent needs. After the work, it moved to verification of what the faster process produced.

This picks up where my [previous article in this series](https://blog.simukappu.com/three-pivots-in-ai-driven-development) left off. There I argued that the productivity curve bends only once a team rebuilds how it works around the agent, and I still think so. I closed it suspecting that the hardest problems would turn out to be about the organization around the methodology. [DORA's 2025 report](https://dora.dev/research/2025/dora-report/) found the general pattern across the industry: AI amplifies the strengths and weaknesses an organization already has. These three accounts show where they surfaced, and what to check for each.

Every fact about the three companies comes from what they published themselves. The measurements are theirs and the reading across them is mine, as are any errors. The views are my own, not my employer's.

> **TL;DR**
> 
> 1.  **When nobody states the objective, an agent optimizes for one anyway.** ASKUL's then-CEO stated one: exceed the starting point rather than return to it. Write the objective and the price you accept for it in a short statement before the agent generates anything, and have two people write it separately to check that the team shares one.
>     
> 2.  **Reading the code is not the same as owning the context.** LY's first workshop on a 26-year-old platform did not go well and showed what information was missing. LY then built a design for that information, not a set of generated documents. Give every required artifact an owner and a refresh trigger, and budget people's time for deciding which version is authoritative, separately from the tools that generate documents from code.
>     
> 3.  **Producing got faster, but verifying did not keep up.** Spotify's merged changes doubled with no distinct AI-authored failure signature, and the doubling is what showed some of its verification controls to be the limit. In the incident review you already run, ask two questions: did AI-authored code contribute, and did the volume of change? Then track change volume against verification capacity, not tool use.
>     

## When nobody states the objective, an agent optimizes for one anyway

Over the past year or so, development workflows have kept adding stages to close the gaps they could see, and new stages have exposed the next gap. [AWS's AI-DLC v2](https://awslabs.github.io/aidlc-workflows/reference/diagrams/) is the most explicit example, with five phases and thirty-three stages as of October 2026. The previous article named three gaps AI-DLC did not yet cover: discovery, brown field code, and organization-wide visibility. At the time, after reading any existing code, the workflow went straight to requirements. The current specification has an Ideation phase with seven stages that covers the work from capturing intent through market research to an approved handoff.

A workflow that starts from intent has to be able to answer what the plan is for. Yet when nobody states the objective, an agent optimizes the plan for one it has guessed. A team of people in the same position usually stalls, and everyone can see the stall. The agent keeps going, so the workflow seems productive the whole time. AI-DLC's first stage now guards against this: it asks what success looks like and who decides scope or priority, and it has a person confirm anything it had to assume. That gets the question to a person, but AI cannot supply the answer.

ASKUL's talk describes the company's decision cycle with AI as one that starts and ends with people: people state the purpose and a hypothesis, AI researches, generates, and proposes at speed, and people judge and set the direction. The objective is the one input the AI does not produce, and at ASKUL it came as the then-CEO's directive. Recovery work, the slides say, only gets you back to where you were, so the target was set past full recovery, at new value created alongside it. A team told to restore optimizes differently from a team told to go beyond where the business was. That directive set the acceptance criteria for everything downstream, and no stage in the workflow produces it. Read as a diagnostic of the organization, ASKUL's account is the healthy result: the constraint moved to the objective, and the company could already state it explicitly.

LY's talk shows the constraint moving to the same place under normal operations. Lead time can improve, it says, and the next question is how to produce a good plan. That question has no answer inside a workflow. A workflow has no objective function that can rank several good plans by strategic value.

Both accounts show the constraint before the work moving to the objective. What differs is how hard that place is to fill. At ASKUL, the incident had already narrowed the options the company could take. At LY, choosing among plans is the work itself. I read that difference as one of condition, not maturity. So in either situation, before the agent generates options, someone with the authority to set the objective has to write down what the organization is optimizing for in this scope. ASKUL's then-CEO did it in a short statement.

Two properties make that statement usable. It defines the direction, and it defines what you are willing to pay to go that way. ASKUL's defined both: exceed the starting point, and do it alongside the recovery with the same limited staff. A statement with only the direction is an aspiration, and a workflow cannot tell it from an objective.

The second property is easy to leave out, and I have left it out myself more than once. On one control system I built for my own use, I told a coding agent the goal was stable operation, since sequences orchestrated by an external service kept failing or stalling. I did not state the price I had accepted: one central computer as a single point of failure, which is fine because it sits in the room with the devices and someone is always there when they are in use. Partway through, the agent's work exposed each control path as an API and left the sequence to external services, a design that follows the most common guideline for achieving stability: avoid a single point of failure. I stepped in and corrected it. In my experience, an agent fills what is left unstated with the most common design, so a trade-off made on purpose is the first thing it overrides.

Why the price is acceptable belongs in that short statement too. With the reason written down, an agent can propose other designs that respect it instead of overriding the price, and you can tell when the price itself needs revisiting.

There is a simple test for whether the team shares an objective: ask two or more people on the team, separately, to write down what this piece of work is optimizing for and what price it accepts and why. I ask the same question whenever I start an initiative within my organization. The agents I work with there are not always writing code, but a shared objective matters just as much.

If the written answers differ on a team working with an agent, the diagnosis has found the organization thin there: that agent has been optimizing toward an unclear objective all along, and every artifact downstream depends on what it produced. The process will narrow the options either way. What it narrows them toward is not in the process itself, so the first deliverable is a statement of the organization's objective and its price, written the same way by two or more people.

## Reading the code is not the same as owning the context

Brown field code, the second gap, did have a stage. Since the first version of AI-DLC's open-source workflow, a Reverse Engineering stage has read an existing codebase and generated architecture, API, and component documentation from it, and v2 makes it the first stage of the Inception phase. What was missing when I wrote the previous article was a way to manage context beyond the code in one workspace. On a large platform, that context spans many repositories, their change history, and the documents the organization already has. v2 now scans each repository a piece of work touches, but applying the process to a large existing platform is still a hard problem.

LY ran into this problem early. The slides label the August 2025 session an "AI-DLC Workshop" and say openly that it did not go well: participants saw value in the process but expected it to be difficult to use in brown field development. The scale explains why: the same slides report more than one hundred components, more than three thousand repositories, and a first release on 9 September 1999, making the platform 26 years old at the time of the talk.

Looking back, that workshop was a diagnostic of the organization as much as an attempt. LY's response, as described in the talk, was to look for where the process worked, define what was missing, and build the information platform it needed, the hard way, while repeating the trial. Building it took from October 2025 to February 2026.

The interesting output was two organizing axes, and the slides give the reason for each. A platform this size does not fit into an agent's context as it is, and each stage needs a different resolution. So LY split the information into layers by level of detail, and each stage uses the layer it needs: the system-wide view and user-manual equivalent for basic design, the external view of each system for detailed design, and source code for implementation. Related information is grouped by domain proximity, which lets an agent find related components and follow a sequence across several of them. The information platform spans component and repository inventories, system diagrams, interface specifications, and a ubiquitous language, exposed to agents through MCP.

Reverse engineering can extract syntax, symbols, call paths, and prose. But it cannot decide which document is authoritative, which concept deserves a shared name, which subsystem boundary matters to the next change, or what should be deleted because it is stale. Those are design decisions about organizational knowledge, and AI cannot make them on its own.

The context an agent depends on has to be kept current by someone who owns it. So whenever a piece of work starts, I make a point of putting four questions to the team:

| Field | Question |
| --- | --- |
| Artifact | What must an agent and a new team member be able to find? |
| Owner | Who is accountable for its accuracy? |
| Refresh trigger | What event makes the artifact stale enough to update? |
| Consumer | Which decision, review, or implementation depends on it? |

The two middle rows are where the conversation often stalls. Naming an artifact is easy, and so is naming its consumer. But who is accountable for its accuracy in day-to-day work, and what event tells that person it has gone stale? Those are the two questions that rarely get an answer the first time I ask them. A team that cannot answer them has good intentions, not a backlog anyone can check.

The trade-off is plain. Allocating engineers to context delays work on the next feature; leaving it informal makes every team pay the same discovery cost again, and the organization accumulates nothing durable. A cost is paid in both cases, and only the first leaves something behind.

## Producing got faster, but verifying did not keep up

Verification, the third place, is different in kind. The first two surfaced inside a workflow; this one surfaces when AI simply keeps increasing how much gets produced, with or without a workflow. The previous article listed organization-wide visibility as the third gap and recommended agreeing on a single output metric within the organization. But Spotify's account shows what a single output metric misses.

During its AI ramp-up, Spotify added two questions to its monthly review of major incidents: did AI-authored code directly contribute, and did the increased volume of change put pressure on review, testing, rollout, or observability. Across the incidents reviewed, the first answer was no material direct contribution; the second was yes. That is a sharper result than either "AI code is fine" or "AI code is risky." Read as a diagnostic of the organization, it shows where the organization was thin: its capacity to review, test, roll out, and observe change.

The company then looked further up the pipeline for a quality-for-velocity trade-off, and did not find a simple one. Quality and optimization work rose from 27% of merged changes to 31% while total volume doubled. A rebuilt rework-rate metric, weighted by the age of the code being changed rather than by raw churn (how much code is removed relative to what is added), showed no rise. Spotify reads that as a clear signal that it is not accumulating AI-induced quality debt.

Spotify also names two warning signals that are creeping up: PR size and code complexity. A larger PR may now just mean a human and an agent shipped a bigger unit safely together, and a complexity threshold calibrated for one person's head may no longer apply. Spotify is not convinced either way, so it is deliberately not rewriting the thresholds to make itself feel better. Keeping a metric that looks bad while you work out whether it still means what it used to is a discipline worth copying.

I think the failure mode they report generalizes. An automated dependency upgrade passed its checks and still failed in production. Spotify responded with three changes: it strengthened safeguards, expanded rollback capacity, and scheduled automated changes during the owning team's working hours. That last one is an organizational decision, not an engineering one. It places a person in the recovery loop rather than the generation loop, and it costs something real: automated changes can now run only while the owning team is at work.

I wrote a version of the same problem for [Architecture Dojo 2026](https://blog.simukappu.com/three-responses-to-ai-s-probabilistic-core-architecture-dojo-2026) earlier this year, as a design challenge: per-developer commits up about 20x, with pull-request review as the bottleneck. At Spotify, a doubling of merged changes was enough to show the same kind of pressure. The answer on stage split trust across AI for generation, deterministic machinery for judgment, and people for decisions. Spotify's account answers the same problem from a different angle: how an organization finds out whether verification kept up.

So measure across one team's flow of work, from review through rollout. Pick one real piece of work, and take a baseline before you change how the team works. Leaders often want to know which tools are in use and who uses them most. The signals worth tracking instead are the ratio of change volume to verification capacity, the rework rate on recently written code, and rollback success for automated changes. Count verification capacity in whatever your flow runs out of first: reviewer hours, test environments, or rollout windows.

Whether your ability to verify kept pace with your ability to produce is what a single output metric misses. It is a measurement you have to build yourself. Start with the two questions in a review you already hold: did AI-authored code contribute, and did the volume of change? Keep the answers apart, because the first points at code and the second at the organization's capacity.

## Closing

In all three accounts AI sped up the work it could do, and the constraint surfaced in work it could not do on its own. It moved to three jobs the organization owns: stating what the work is for, keeping the context current, and verifying what comes out. A team rarely looks there first.

So use the speedup to find where your organization is ready and where it is thin. That is what LY did: it looked for where the process worked, defined what was missing where it did not, and built the missing pieces while it kept testing. If an organization can treat the point where a process it changed stops working as a finding rather than a setback, then wherever the constraint moves, that organization can find a way to remove it.

One question this article leaves open is whether your own numbers are good. There is no public distribution of these signals to compare yourself against, and Spotify's absolute figures belong to 777 million monthly active users and nearly three thousand production services. That is the argument for starting now, because the first comparable baseline your organization will ever have is the one taken before you change anything.

One more limit. The stage changes I traced belong to only one workflow, AWS's AI-DLC. Skill-based workflows such as [Superpowers](https://github.com/obra/superpowers) and [gstack](https://github.com/garrytan/gstack) have no stages to trace, but the constraint seems to move without them too: Spotify's account describes no stage-based workflow at all.

In a later article in this series, I plan to go further into the third place, verification. Spotify described it better than I could: "The next constraint became our ability to verify it." That article will take up one part of the Dojo answer: verifying AI-written code against specifications instead of another model's judgment.

What I wrote this one for is more modest: three questions I now start with. In the scope where you plan to introduce an AI-driven development workflow next, what is the organization optimizing for and at what price, who owns the context it will need, and what ratio will tell you your ability to verify kept up?