---
title: "AI Agent Evaluation: What, How, When"
seoTitle: "3 Axes for AI Agent Evaluation: Target, Method, Stage"
seoDescription: "A crowded field of AI agent evaluation tools, no shared map. Three axes (Target, Method, Stage) navigate it, plus a 3-execution-model benchmark."
datePublished: 2026-05-22T08:03:37.984Z
cuid: cmpgmuuey005h1smtfls5edde
slug: ai-agent-evaluation-what-how-when
ogImage: https://cdn.hashnode.com/uploads/og-images/69d1f25c6792e486f60903fd/0c816d30-43f9-428f-8bd1-55b458139484.png
tags: testing, evaluation, llm, ai-agents, agentic-ai

---

Most teams pick the AI agent evaluation tool their framework integrates with, then a quarter later notice that one corner of the evaluation space is covered and the rest is exposed. The market has no shortage of tools and no shared map. The problem is rarely the tools themselves. The axes are missing.

Here is one shape of the gap, drawn from an agent platform I work with. The team is moving from a single agent to a router-style supervisor in front of a multi-agent fleet, where the supervisor and each worker can independently decide they need the same web search or KB lookup. Per-call cost slips under any single alarm, but aggregated across thousands of sessions a day it becomes the actual monthly bill. The current tooling is excellent at telling them whether the final answer was correct. It has nothing to say about whether the trajectory was wasteful. The gap is a missing axis: nobody had named "redundant tool calls across a multi-agent topology" as a thing to assert on, so no tool was reaching for it.

Mark Brooker has [a useful framing](http://brooker.co.za/blog/2026/01/12/agent-box.html): treat an LLM-driven agent as a probabilistic box. We can specify what goes in and what comes out, but the internal sampling and reasoning are observable only through their effects. That shift makes the rest tractable: whatever happens inside, the outside world sees only a small set of surfaces, and any evaluation tool operates on some combination of those.

This is the first post in a short series on AI agent evaluation at scale. Here is the map.

> **TL;DR**
> 
> 1.  **Three axes navigate the space: Target, Method, Stage.** *Target* is what to evaluate, *Method* is who scores, *Stage* is when it runs. The three move independently, and most "X tool beats Y tool" arguments are really two people standing on different axes.
>     
> 2.  **Testing and evaluation are different design instincts, not competing implementations of the same idea.** Evaluation platforms put an LLM-as-a-Judge at the spine; test primitives put a deterministic assertion at the spine. They land in different cells of the 3-axis frame and belong to different stages of a CI pipeline: deterministic tests gate every PR, judge-driven evaluations gate staging or canary releases.
>     
> 3.  **Three execution models, identical assertions: wall time, cost, and trial count land in measurably different cells.** Cassette replay, live LLM, and trace-based evaluator do not form a tool ranking. They form a category boundary that decides which execution models can realistically sit on a per-PR CI gate.
>     

*Where I'm coming from.* I maintain [agentverify](https://github.com/simukappu/agentverify), an OSS pytest plugin that sits in the deterministic-test category this post defines, and the Section 3 benchmark includes it as one of three execution models. The methodology and harness are in a public repository, so the numbers are auditable, but readers should still bring the usual scepticism that comes with an author writing about the space their own tool is in.

## 1\. Three axes: Target × Method × Stage

Each evaluation tool occupies a cell defined by *what it evaluates*, *who scores*, and *when it runs*. Naming all three is what keeps the landscape navigable; the three subsections below take the axes one at a time.

### Target: what to evaluate

Treating the agent as a probabilistic box, the outside world sees five things.

| # | Target | Family | What you observe | The question it answers |
| --- | --- | --- | --- | --- |
| T1 | Response quality | Outcome | Final answer's accuracy, relevance, hallucination rate | Was the answer right? |
| T2 | Goal achievement | Outcome | Multi-step or multi-turn task completion | Did the user get what they came for? |
| T3 | Execution trajectory | Process | Tool selection, arguments, step outcomes, inter-step data flow | How did it get there? |
| T4 | Resource consumption | Non-functional | Cost, latency, token spend, API call count | Did it stay inside the budget and SLO? |
| T5 | Safety and governance | Non-functional | Policy violations, unauthorized tool calls, adversarial robustness | Did it avoid the things it must not do? |

T1 and T2 are about the outcome and merge for single-turn agents, diverging in multi-step or multi-turn settings. T3 is about the process. T4 and T5 are non-functional constraints riding on top of both.

T3 is the one that gets under-counted, so it is worth pulling out. You can pass T2 (the user's task got done) while T3 silently degrades: a different tool was called and the LLM smoothed it over in the final reply, retries doubled, the order of two tool calls flipped. None of that is visible at the outcome layer until you see the bill at month end or chase a regression that snuck in three deploys ago. T3 is also the most amenable to deterministic checking: tool names, arguments, ordering, and step outcomes are structured signals, and once you fix the non-determinism around them (more on that under Method), they fall to ordinary unit-test assertions.

Inside T3 it helps to be specific. Open-source libraries (DeepEval, for example) carve T3 along similar lines, the same carving any test of a multi-step agent ends up using:

| Sub-target | What it covers | Typical failure |
| --- | --- | --- |
| T3a Tool selection | Right tool, no extras | `Calculator` instead of `WebSearch` |
| T3b Argument correctness | Values consistent with input and prior steps | `{"location": "SF"}` when the schema asks for `city: "San Francisco"` |
| T3c Tool invocation outcome | Call returned a usable result | Silent 5xx, timeout, expired credentials |
| T3d Inter-step data flow | Step N actually used step M's output | `list_issues` returns ids, `get_issue` is called with a different id |
| T3e Step efficiency | No redundant or detoured calls | The same search runs twice |

Across the agent designs I've reviewed, these aren't abstract. T3a (tool selection) shows up first as an architectural lever: agents embedded in consumer-facing services often bypass MCP and implement tool calls in-process, because an agent step's latency budget is tight enough that a network hop matters, while general-purpose agents (coding assistants, IT helpers) lean on MCP because their tool surface is too wide to ship in-process. Once that choice is made, "did the agent pick the right tool" becomes a CI-time invariant on a specific function rather than a runtime concern.

T3e (step efficiency) is the one I expect to bite next, even though I have not yet seen a production incident around it. The router-style supervisor from the opening of this post lives here: the redundant calls never trip an alarm individually, and the only way to see them coming is to make the trajectory itself an assertion target before the rollout. That is the pipeline we are building now.

Splitting T3b from T3c matters in production, because the failure boundary between "the agent's responsibility" and "the dependency's responsibility" runs right between them. T3b is a bug in the agent. T3c is usually a bug in the world.

### Method: who scores

Three core evaluators, plus modifiers that ride on top of them. The cores are mutually exclusive; the modifiers compose with one of M1-M3.

| # | Evaluator | How it works | Strength | Weakness |
| --- | --- | --- | --- | --- |
| M1 | Code-based | Assertions, schema validation, regex, exact match, trajectory diff, classifiers | Fast, cheap, reproducible, binary verdict | Only sees what the rule can express |
| M2 | LLM-based judge | A judge LLM scoring against a rubric, reference-based or reference-free, sometimes pairwise | Subjective criteria scale up, criteria written in natural language | Cost, bias, variance, judge drift |
| M3 | Human-based | Expert review, annotation queues, pairwise human, end-user feedback | Gold standard, picks up subtle issues | Slow, expensive, inter-rater variance |

Two modifiers worth pulling out here:

*   *Adversarial input generation* expands the input side, not the verdict side. Red-team toolchains like [Garak](https://github.com/NVIDIA/garak) (NVIDIA), [PyRIT](https://github.com/Azure/PyRIT) (Microsoft), and [DeepTeam](https://github.com/confident-ai/deepteam) (Confident AI) generate jailbreaks, prompt injections, and other attack inputs; the verdict on each input is still M1 (forbidden-pattern hit) or M2 (judge scoring safety).
    
*   *Runtime application* takes an evaluator and inserts it synchronously into the inference path (stage S4 below). [Bedrock Guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html) (M1 + M2 on model outputs), [AgentCore Policy / Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html) (M1 on tool calls), and OSS counterparts like [NeMo Guardrails](https://github.com/NVIDIA/NeMo-Guardrails) and [Llama Guard](https://huggingface.co/meta-llama/Llama-Guard-3-8B) all operate as runtime modifiers.
    

Two further modifiers sit in the background here and get the next post's attention: *statistical aggregation* (running the same input N times and reading the distribution) and *composite evaluation* (weighting M1, M2, and M3 verdicts), both most useful at the deterministic/probabilistic boundary.

Code, LLM, or Human are the three evaluators. Red-teaming, sampling, composites, and runtime guardrails are how each of them gets wielded.

### Stage: when it runs

Three phases, six stages. The split into Offline / Online / Feedback loop matches [LangSmith's Evaluation concepts](https://docs.smith.langchain.com/evaluation) and the [Evaluation-Driven Development of LLM Agents paper](https://arxiv.org/html/2411.13768v2).

| Phase | # | Stage | Where | Reference data | Purpose | Method bias |
| --- | --- | --- | --- | --- | --- | --- |
| Offline | S1 | Local dev | Developer machine | Yes | Tight feedback, iteration | M1 heavy, light M2 |
|  | S2 | CI/CD | PR gate | Yes | Regression detection, deterministic gating | M1 heavy |
|  | S3 | Pre-release / staging | Pre-launch canary | Yes | Quality gate including human review | M1 + M2 + M3 |
| Online | S4 | Runtime guardrails | Production, synchronous, blocking | No | Safety enforcement, immediate refusal | M1 + low-latency M2 |
|  | S5 | Online monitoring | Production, async sampling | No | Drift, anomaly, production feedback | Async M2, heuristics |
| Feedback loop | S6 | Incident review | Post-incident batch | Generated here | Root cause, failure → dataset | M3 review, then back into S1-S3 |

S2 and S3 share the Offline category but split here because their cost and time budgets differ by an order of magnitude. S4 and S5 share Online but differ in synchronicity: S4 blocks the response, S5 watches it go by. S6 isn't parallel to the others; it's the loop that feeds failures back into the dataset S1-S3 run against.

Comparing two tools gets easier with one check: write down the (Target, Method, Stage) triplet each occupies. Triplets that don't match mean the tools aren't really competing, they're aiming at different parts of the same landscape.

## 2\. Testing and evaluation are different design instincts

[LangSmith's docs](https://docs.smith.langchain.com/evaluation) put the difference directly: "Testing asserts correctness. Evaluation measures performance according to metrics." The distinction predates LLM agents, lining up with how software engineering has always split unit tests from A/B tests, integration tests from quality monitoring. Each side has its own legitimate job, and pretending one subsumes the other tends to produce a tool that disappoints both audiences.

Two design instincts run through the agent tooling. One puts an LLM-as-a-Judge at the spine and builds the rest of the platform around it: dataset curation, trace observability, shared dashboards, production sampling. [DeepEval](https://github.com/confident-ai/deepeval), [LangSmith](https://docs.smith.langchain.com/), and [Amazon Bedrock AgentCore Evaluations](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluations.html) are three of the better-known ones. The other puts a deterministic assertion at the spine and builds the test loop around it: SDK patching or trace replay, in-process execution, no API key in CI, the existing pytest fixture model. [Agent VCR](https://github.com/Jarvis2021/agent-vcr), [agentverify](https://github.com/simukappu/agentverify), and [pytest-evals](https://github.com/AlmogBaku/pytest-evals) live in this second category. Specialized tools fill in the corners: runtime guardrails, red-team toolchains, RAG-specific quality (such as [Ragas](https://github.com/explodinggradients/ragas)), and the memory and observability substrates ([AgentCore Memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html), [AgentCore Observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html)).

The two instincts split cleanly:

*   *Tests* check whether the spec-defined behavior still holds. Pass/fail. They block PRs. They live next to the code they describe.
    
*   *Evaluations* measure quality on continuous metrics. They support comparison across systems and across time. They live in datasets that experts curate.
    

In a CI/CD pipeline the natural shape is to run them as different stages. Deterministic unit tests on every PR, each finishing in seconds and the suite in minutes. Quality gates with judge-LLM scoring on staging or release candidates, finishing in minutes to hours. The gates can sit in the same pipeline; they should not pretend to be the same step.

*A note on the snapshot.* The market moves in quarter-scale steps, so any one tool's position may have shifted by the time you read this. [Hasan et al.](https://arxiv.org/abs/2509.19185) report that agent-specific testing methods are adopted by around 1% of OSS agent projects; the rest reach for traditional unit testing. Tooling is well ahead of practice, which is part of why the design-instinct split is more durable than any tool-by-tool comparison.

### The 3-axis view of the difference

The split maps onto all three axes. On Target, platforms emphasize T1 and T2 ("how good was it?") while test primitives emphasize T3-T5 ("did it match the spec?"); even on the same T3 trajectory, a platform returns a continuous quality score and a test primitive returns a binary pass/fail. On Method, platforms are M2 first and test primitives are M1 first by construction, pinning the non-determinism so assertions run with no LLM call at all. On Stage, platforms shine at S2 through S5, especially S5, trading per-run cost for live-LLM coverage, while inline primitives shine at S1 and S2, trading that coverage for per-test feedback in seconds.

### What the structural conflict looks like

Trying to merge the two sides into one tool runs into design choices that pull in opposite directions:

*   *Instrumentation.* Platforms want `@observe` decorators wrapping agent functions to emit traces. Primitives want to patch the LLM SDK so agent code is unchanged. Either choice is reasonable; both as defaults is not.
    
*   *CLI surface.* Platforms want their own CLI for dataset management, cloud sync, shared reports. Primitives want pytest-native, so existing CI templates, pytest-xdist, and pytest-cov plug in unchanged.
    
*   *Where the spec lives.* Evaluation puts the spec in the dataset (curated by humans, often domain experts, hosted in the cloud). Testing puts the spec in the assertion (in git, reviewed in PRs, versioned with the code).
    

Both designs are defensible, and choosing a default for one steers the framework's whole personality; the two categories are most useful paired, not when one tries to absorb the other. The boundary between them isn't frozen, managed platforms are extending toward inline / local-dev workflows and test primitives are reaching into production observability, but the DNA stays distinct as the surface areas grow.

## 3\. A 3-execution-model benchmark on identical assertions

Numbers help. I ran a benchmark on three execution models against two agent subjects: a Strands single-agent weather forecaster on Bedrock Anthropic Claude Sonnet 4.6, and a LangGraph multi-agent supervisor on OpenAI gpt-5.4-mini. Identical T3 assertions ran on each subject:

*   **A — Inline cassette replay**: pytest with SDK patching (run here on agentverify). Under the *dev* scenario A drives a live LLM to record the cassette; under the *ci* scenario the same test replays the cassette and skips the LLM call entirely. The A-dev numbers double as a control: A-dev versus A-ci isolates what cassette replay saves, holding the assertion library constant.
    
*   **B — Decorator + judge**: trace decorator with an LLM-as-a-Judge metric, live LLM under both scenarios (run here on DeepEval `@observe` + `ToolCorrectnessMetric`).
    
*   **C — Trace export + Custom evaluator**: OTLP push of agent traces to a code-based evaluator on Lambda, live LLM under both scenarios (run here on AgentCore Evaluations Custom code-based evaluator).
    

Two scenarios per cell: *dev* (first run, no cassette, cold cache) and *ci* (PR-time repeat, with cassette / cache). Five trials each, trimmed mean of the middle three runs.

![](https://cdn.hashnode.com/uploads/covers/69d1f25c6792e486f60903fd/db027340-4df0-4100-8607-3e308e2edb60.png align="center")

The CI scenario is where the design DNA shows: A drops to ~1.7s per test on both subjects because the cassette replaces the LLM call, while B and C stay at the live-LLM round-trip cost (8.9-16.8s). The control comparison makes the source of the gap concrete: turn the cassette off and run A against a live LLM, and A's wall time lands at 8.7s on the LangGraph subject and 16.5s on the Strands subject, in the same band as B and C. The order-of-magnitude gap on the CI path tracks the cassette, not the library or the assertion API. The dev scenario is close across all three (within ~1s on each subject), because every model calls the real LLM at least once to populate caches, fixtures, or cassettes.

Cost lines up the same way. Per-run dollar cost, from the cassette token aggregates against current public pricing: A on CI is exactly $0 (cassette replay doesn't call the LLM); B and C invoke the live LLM the same way per run, landing at $0.0468 on the Strands subject and $0.0054 on the LangGraph subject. At 1000 PRs per month per subject, B and C come to roughly $5 on the LangGraph subject and ~$47 on the Strands subject in LLM charges while A stays at zero, and the figures multiply across subjects and tests in any real agent codebase.

The trial-count column is its own story. For each cell the harness ran until five trials passed; with cassette replay this happens on the first attempt, but live invocations of the LangGraph supervisor do not always converge in five tries. On the LangGraph subject, A needed 5 attempts for 5 passes in both dev and CI, B needed 9 attempts in dev and 5 in CI, and C needed 7 attempts in both dev and CI. The Strands subject's simpler trajectory needed 5 attempts for 5 passes in every cell. The flakiness is concentrated where a live LLM has to pick a routing decision in a multi-agent supervisor.

What I hadn't predicted surfaced under a model upgrade. The first canonical run used `gpt-4o-mini`, and the LangGraph supervisor's assertions hit 5-for-5 reliably across B and C. After OpenAI [released](https://openai.com/index/introducing-gpt-5-4-mini-and-nano/) `gpt-5.4-mini` in March 2026, I rerecorded the cassettes against it and reran, with assertion code and agent topology unchanged. That single change is what introduced the live-trial flakiness reported above; A still hit 5-for-5, because the cassette pinned the trajectory at record time. The flakiness wasn't a property of LangGraph or of the assertions. It was a property of moving from one model generation to the next, and any team that runs live-LLM assertions in CI will hit some version of this on every model-upgrade cycle.

A second, independent pressure points in the same direction. Reasoning-class models (the GPT-5 series, and earlier ones like o1, o3, and o4-mini) accept `temperature` only at its default; passing a specific value is rejected by the API. That removes a knob teams relied on to keep live-agent assertions stable, and it's a directional shift across providers, not one model line. One subject in one round is too narrow to prove this, but the operational pressure on keeping a live LLM stable in CI is mounting from more than one angle.

The cassette's strength here is also its boundary. Pinning the trajectory at record time means the cassette doesn't see drift in the model's behavior between recordings: if the LLM starts routing differently tomorrow, a cassette recorded today keeps the test green until someone re-records it. What a cassette asserts is "did the agent code call the expected tool with the expected arguments given the recorded trajectory," not "did the LLM make the right judgment in the first place," which is exactly what an LLM-as-a-Judge metric on a live trace is built to answer. That boundary has a direct operational consequence: a team running only cassette replay misses model-level regressions and needs a separate process (manual canary, scheduled re-recording with a judge in the loop, production sampling) to catch them, while a team running only live judging at the PR gate pays for it on every push.

A few caveats on the numbers:

*   The wall-time figures include pytest startup and subprocess overhead because they are measured around `subprocess.run`. The 1.7-second figure is "what the developer sees on a PR," not "the assertion engine in isolation."
    
*   The hardware was a 12-CPU macOS arm64 box on Python 3.14. Absolute seconds shift on different hardware, but the order-of-magnitude gap on CI does not.
    
*   AgentCore Evaluations may carry an additional per-evaluation charge whose price is not yet publicly documented; the dollar figures here cover the LLM portion only.
    

The full results, methodology, and counting rules live with the [agentverify execution-model trajectory benchmark](https://github.com/simukappu/agentverify/tree/main/benchmarks/execution-model-trajectory) (this run: `results-2026-05-17T232008.md`).

Reading these numbers as "agentverify is faster" misses the point. The three execution models occupy measurably different design cells: cassette replay behaves like a test, trace decorator and trace export behave like evaluations, and the right move on a real PR is to combine them. A team would reasonably layer:

*   a deterministic test primitive on T3 × M1 × S2 for trajectory regressions
    
*   AgentCore Evaluations or DeepEval on T1 × M2 × S3 for response-quality regressions
    
*   Bedrock Guardrails on T1 + T5 × M1+M2 (Runtime modifier) × S4 for content-level filtering of model outputs
    
*   AgentCore Policy on T5 × M1 (Runtime modifier) × S4 for authorization on tool calls
    
*   observability across all of them.
    

## Closing — design the CI before picking the tool

AI agents are about to live in the same CI/CD pipelines as everything else, where PRs merge in minutes at a cost that scales with the number of PRs, not the size of the team. A live LLM on every push works for some teams and stops working as the agent surface grows; the durable shape is a deterministic layer holding the PR gate fast and cost-bounded, with judge-driven measurement moved to staging or production sampling. Whichever way a team fixes the non-determinism long enough to assert against it, CI has to keep working without an LLM API key in the pipeline and without a per-PR bill that compounds.

The series goes in two directions from here. The next post stays on the deterministic side, going deeper into where cassette replay holds and where its boundary forces a different approach. A later one crosses to the online side of this frame, the production stages where there is no reference dataset to assert against and the interesting failures are the ones only live traffic reveals.

So the question I'd put to readers is concrete. How are you running CI for your agents today, on a live LLM, a cassette or trace replay, a mock, something else? Where does the test for "the agent did the right thing" live in your pipeline, and how often does it false-fail? If you have a CI design that's held up at scale, or one that broke in an interesting way, I'd like to hear about it.