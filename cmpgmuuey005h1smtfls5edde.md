---
title: "AI Agent Evaluation: What, How, When"
seoTitle: "3 Axes for AI Agent Evaluation: Target, Method, Stage"
seoDescription: "50+ AI agent evaluation tools, no shared map. Three axes (Target, Method, Stage) navigate the landscape, plus a benchmark on three execution models."
datePublished: 2026-05-22T08:03:37.984Z
cuid: cmpgmuuey005h1smtfls5edde
slug: ai-agent-evaluation-what-how-when
ogImage: https://cdn.hashnode.com/uploads/og-images/69d1f25c6792e486f60903fd/0c816d30-43f9-428f-8bd1-55b458139484.png
tags: testing, evaluation, llm, ai-agents, agentic-ai

---

Most teams pick the AI agent evaluation tool their framework integrates with, then a quarter later notice that one corner of the evaluation space is covered and the rest is exposed. The market has 50+ tools and no shared map. The problem is rarely the tools themselves. The axes are missing.

Here is one shape of the gap, drawn from an agent platform I work with. The team is moving from a single agent to a router-style supervisor in front of a multi-agent fleet, where the supervisor and each worker can independently decide they need the same web search or KB lookup. Per-call cost is small enough to slip under any single alarm; aggregated across thousands of sessions a day, that becomes the actual monthly bill. The current tooling is excellent at telling them whether the final answer was correct. It has nothing to say about whether the trajectory was wasteful. That gap is not a tool defect. It is a missing axis: nobody had named "redundant tool calls across a multi-agent topology" as a thing to assert on, so no tool was reaching for it.

Mark Brooker has [a useful framing](http://brooker.co.za/blog/2026/01/12/agent-box.html): treat an LLM-driven agent as a probabilistic box. We can specify what goes in and what comes out, but the internal sampling and reasoning are observable only through their effects. That shift makes the rest of the question tractable. Whatever happens inside, the outside world only sees a small set of surfaces, and any evaluation tool you can buy or build operates on some combination of those.

This is the first post in a short series on AI agent evaluation at scale. Here I lay out a map: three independent axes for navigating the tooling, a clear split between testing and evaluation as different design instincts, and a measured comparison of three execution models on identical assertions to ground the abstractions in numbers.

> **TL;DR**
> 
> 1.  **Three axes navigate the space: Target, Method, Stage.** *Target* is what to evaluate (response quality, goal achievement, execution trajectory, resource consumption, safety). *Method* is who scores (Code, LLM, or Human). *Stage* is when it runs (local dev, CI, pre-release, runtime, online monitoring, incident review). Red-teaming and runtime guardrails are modifiers on the three core methods, not separate methods.
>     
> 2.  **Testing and evaluation are different design instincts, not competing implementations of the same idea.** Evaluation platforms put an LLM-as-a-Judge at the spine; test primitives put a deterministic assertion at the spine. They land in different quadrants of the 3-axis frame and belong to different stages of a CI pipeline: deterministic tests gate every PR, judge-driven evaluations gate staging or canary releases.
>     
> 3.  **Three execution models, identical assertions: wall time, cost, and trial count land in measurably different quadrants.** Cassette replay, live LLM, and trace-based evaluator do not form a tool ranking. They form a category boundary that decides which execution models can realistically sit on a per-PR CI gate.
>     

> **Where I'm coming from.** I maintain [agentverify](https://github.com/simukappu/agentverify), an OSS pytest plugin that sits in the deterministic-test category this post defines, and the Section 3 benchmark includes it as one of three execution models. The methodology and harness live in a public repository, so the numbers are auditable rather than just stated. Readers should still bring the usual scepticism that comes with an author writing about the space their own tool is in.

## 1\. Three axes: Target × Method × Stage

Each evaluation tool occupies a quadrant defined by *what it evaluates*, *who scores*, and *when it runs*. The three axes move independently, which is what makes the landscape navigable. Most tooling-comparison posts mix these together, which is what produces the "X tool is better than Y tool" arguments where both speakers are right about different axes.

### Target: what to evaluate

Treating the agent as a probabilistic box, the outside world sees five things.

| # | Target | Family | What you observe | The question it answers |
| --- | --- | --- | --- | --- |
| T1 | Response quality | Outcome | Final answer's accuracy, relevance, hallucination rate | Was the answer right? |
| T2 | Goal achievement | Outcome | Multi-step or multi-turn task completion | Did the user get what they came for? |
| T3 | Execution trajectory | Process | Tool selection, arguments, step outcomes, inter-step data flow | How did it get there? |
| T4 | Resource consumption | Non-functional | Cost, latency, token spend, API call count | Did it stay inside the budget and SLO? |
| T5 | Safety and governance | Non-functional | Policy violations, unauthorized tool calls, adversarial robustness | Did it avoid the things it must not do? |

T1 and T2 are about the outcome and tend to merge for single-turn agents; they diverge in multi-step or multi-turn settings. T3 is about the process. T4 and T5 are non-functional constraints that ride on top of both.

T3 is the one that gets under-counted, so it is worth pulling out. You can pass T2 (the user's task got done) while T3 silently degrades: a different tool was called and the LLM smoothed it over in the final reply, retries doubled, the order of two tool calls flipped. None of that is visible at the outcome layer until you see the bill at month end or chase a regression that snuck in three deploys ago. T3 is also the most amenable to deterministic checking. Tool names, arguments, ordering, and step outcomes are structured signals; once you fix the non-determinism around them (more on that under Method), they fall to the same kind of assertion you would write in any other unit test.

Inside T3 it helps to be specific. Open-source libraries for evaluating LLM-driven agents (DeepEval, for example) carve T3 along similar lines. The carving is the same one any test of a multi-step agent will end up using:

| Sub-target | What it covers | Typical failure |
| --- | --- | --- |
| T3a Tool selection | Right tool, no extras | `Calculator` instead of `WebSearch` |
| T3b Argument correctness | Values consistent with input and prior steps | `{"location": "SF"}` when the schema asks for `city: "San Francisco"` |
| T3c Tool invocation outcome | Call returned a usable result | Silent 5xx, timeout, expired credentials |
| T3d Inter-step data flow | Step N actually used step M's output | `list_issues` returns ids, `get_issue` is called with a different id |
| T3e Step efficiency | No redundant or detoured calls | The same search runs twice |

Across the agent designs I've reviewed, these sub-targets are not abstract. T3a (tool selection) shows up first as a deliberate architectural lever. Agents embedded in consumer-facing internet services often bypass MCP and implement tool calls as in-process functions, because the latency budget for an agent step is tight enough that a network hop matters. General-purpose agents like coding assistants and IT helpers go the other way and lean on MCP, since the tool surface they need to cover is too wide to ship in-process. Once that choice is made, "did the agent pick the right tool" becomes a CI-time invariant on a specific function rather than a runtime concern.

T3e (step efficiency) is the one I expect to bite next, even though I have not yet seen a production incident around it. The router-style supervisor from the opening of this post lives here. Per-call cost stays small enough to slip under any single alarm, but redundant tool calls compound across the fleet, and the only way to see them coming is to make the trajectory itself an assertion target before the rollout. That is the pipeline we are building now.

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
    
*   *Runtime application* takes an evaluator and inserts it synchronously into the inference path. This lines up with stage S4 below. [Bedrock Guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html) (M1 + M2 on model outputs), [AgentCore Policy / Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html) (M1 on tool calls), and OSS counterparts like [NeMo Guardrails](https://github.com/NVIDIA/NeMo-Guardrails) and [Llama Guard](https://huggingface.co/meta-llama/Llama-Guard-3-8B) all operate as runtime modifiers.
    

Two further modifiers, *statistical aggregation* (running the same input N times and reading the distribution) and *composite evaluation* (weighting M1, M2, and M3 verdicts), are most useful when discussing the deterministic / probabilistic boundary. The next post in this series goes there in detail; for the rest of this article they sit in the background.

Code, LLM, or Human. Those are the three evaluators. Red-teaming, sampling, composites, and runtime guardrails are how each of the three gets wielded.

### Stage: when it runs

Three phases, six stages. The split into Offline / Online / Feedback loop matches the framing in [LangSmith's Evaluation concepts](https://docs.smith.langchain.com/evaluation) and the [Evaluation-Driven Development of LLM Agents paper](https://arxiv.org/html/2411.13768v2).

| Phase | # | Stage | Where | Reference data | Purpose | Method bias |
| --- | --- | --- | --- | --- | --- | --- |
| Offline | S1 | Local dev | Developer machine | Yes | Tight feedback, iteration | M1 heavy, light M2 |
|  | S2 | CI/CD | PR gate | Yes | Regression detection, deterministic gating | M1 heavy |
|  | S3 | Pre-release / staging | Pre-launch canary | Yes | Quality gate including human review | M1 + M2 + M3 |
| Online | S4 | Runtime guardrails | Production, synchronous, blocking | No | Safety enforcement, immediate refusal | M1 + low-latency M2 |
|  | S5 | Online monitoring | Production, async sampling | No | Drift, anomaly, production feedback | Async M2, heuristics |
| Feedback loop | S6 | Incident review | Post-incident batch | Generated here | Root cause, failure → dataset | M3 review, then back into S1-S3 |

S2 and S3 share the Offline category and could collapse into one in some teams. They are split here because their cost and time budgets are different by an order of magnitude. S4 and S5 share Online but differ in synchronicity: S4 blocks the response, S5 watches it go by. S6 is not parallel to the others; it is the loop that feeds failures back into the dataset that S1-S3 run against.

Comparing two tools gets easier with this check: write down the (Target, Method, Stage) triplet each one occupies. Triplets that don't match mean the tools aren't really competing; they're aiming at different parts of the same landscape.

## 2\. Testing and evaluation are different design instincts

The cleanest way to see the difference is to read the concepts page of any mature evaluation platform. [LangSmith's docs](https://docs.smith.langchain.com/evaluation) put it directly: "Testing asserts correctness. Evaluation measures performance according to metrics." That distinction predates LLM agents; it lines up with how the rest of software engineering has always split unit tests from A/B tests, integration tests from quality monitoring. Each side has its own legitimate job, and pretending one of them subsumes the other tends to produce a tool that disappoints both audiences.

Two design instincts run through the agent tooling. One puts an LLM-as-a-Judge at the spine and builds the rest of the platform around it: dataset curation, trace observability, shared dashboards, production sampling. [DeepEval](https://github.com/confident-ai/deepeval), [LangSmith](https://docs.smith.langchain.com/), and [Amazon Bedrock AgentCore Evaluations](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluations.html) are three of the better-known ones, with several other managed platforms in the same shape. The other puts a deterministic assertion at the spine and builds the rest of the test loop around it: SDK patching or trace replay, in-process execution, no API key in CI, the existing pytest fixture model. [Agent VCR](https://github.com/Jarvis2021/agent-vcr), [agentverify](https://github.com/simukappu/agentverify), and [pytest-evals](https://github.com/AlmogBaku/pytest-evals) live in this second category. Specialized tools fill in the corners: runtime guardrails, red-team toolchains, RAG-specific quality (such as [Ragas](https://github.com/explodinggradients/ragas)), and the memory and observability substrates ([AgentCore Memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html), [AgentCore Observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html)) that everything else reads from.

The two instincts split cleanly:

*   *Tests* check whether the spec-defined behavior still holds. Pass/fail. They block PRs. They live next to the code they describe.
    
*   *Evaluations* measure quality on continuous metrics. They support comparison across systems and across time. They live in datasets that experts curate.
    

In a CI/CD pipeline the natural shape is to run them as different stages. Deterministic unit tests on every PR, each finishing in seconds and the suite in minutes. Quality gates with judge-LLM scoring on staging or release candidates, finishing in minutes to hours. The gates can sit in the same pipeline; they should not pretend to be the same step.

> **A note on the snapshot.** The market is moving in quarter-scale steps and the position of any one tool may have shifted by the time you read this. [Hasan et al.](https://arxiv.org/abs/2509.19185) ("An Empirical Study of Testing Practices in Open Source AI Agent Frameworks and Agentic Applications") report that agent-specific testing methods are adopted by around 1% of OSS agent projects; the rest reach for traditional unit testing. Tooling is well ahead of practice, which is part of why the design-instinct split is more durable than any tool-by-tool comparison.

### The 3-axis view of the difference

**Axis 1, Target.** Platforms emphasize T1 and T2: "how good was it?" Test primitives emphasize T3, T4, T5-basic: "did it match the spec?" Even when both look at T3, DeepEval's `PlanQualityMetric` / `ArgumentCorrectnessMetric` / `StepEfficiencyMetric` returns a continuous quality score, while a test primitive on the same trajectory returns a binary pass/fail. The verbs are different.

**Axis 2, Method.** DeepEval is M2 first; the deterministic mode of `ToolCorrectnessMetric` is the exception. AgentCore Evaluations is M2 first with M1 reachable via a Custom code-based evaluator delegated to Lambda. Test primitives in the deterministic camp are M1 first by construction; cassette replay or similar mechanisms pin the non-determinism so assertions can run with no LLM call at all. None of this is one being better than another. They are optimized along different axes.

**Axis 3, Stage.** Platforms shine at S2 through S5, especially S5, exchanging per-run cost and latency for live-LLM coverage. Inline test primitives shine at S1 and S2, especially S2, exchanging live-LLM coverage at test time for per-test feedback in seconds.

### What the structural conflict looks like

Trying to merge the two sides into one tool runs into design choices that pull in opposite directions:

*   *Instrumentation.* Platforms want `@observe` decorators wrapping agent functions to emit traces. Primitives want to patch the LLM SDK so agent code is unchanged. Either choice is reasonable; both as defaults is not.
    
*   *CLI surface.* Platforms want their own CLI for dataset management, cloud sync, shared reports. Primitives want pytest-native, so existing CI templates, pytest-xdist, and pytest-cov plug in unchanged.
    
*   *Where the spec lives.* Evaluation puts the spec in the dataset (curated by humans, often domain experts, hosted in the cloud). Testing puts the spec in the assertion (in git, reviewed in PRs, versioned with the code).
    

Both designs are defensible. Choosing a default for one steers the framework's whole personality. The result is two viable categories that are most useful when paired, not when one of them tries to absorb the other.

The boundary between these two execution models is not frozen. Managed platforms are extending toward inline / local-dev workflows. Test primitives are reaching into production observability. The DNA stays distinct as the surface areas grow.

## 3\. A 3-execution-model benchmark on identical assertions

Numbers help. I ran a benchmark on three execution models against two agent subjects: a Strands single-agent weather forecaster on Bedrock Anthropic Claude Sonnet 4.6, and a LangGraph multi-agent supervisor on OpenAI gpt-5.4-mini. Identical T3 assertions ran on each subject:

*   **A — Inline cassette replay**: pytest with SDK patching (run here on agentverify). Under the *dev* scenario A drives a live LLM to record the cassette; under the *ci* scenario the same test replays the cassette and skips the LLM call entirely. The A-dev numbers therefore double as a control: comparing A-dev against A-ci isolates what cassette replay actually saves, holding the assertion library constant.
    
*   **B — Decorator + judge**: trace decorator with an LLM-as-a-Judge metric, live LLM under both scenarios (run here on DeepEval `@observe` + `ToolCorrectnessMetric`).
    
*   **C — Trace export + Custom evaluator**: OTLP push of agent traces to a code-based evaluator on Lambda, live LLM under both scenarios (run here on AgentCore Evaluations Custom code-based evaluator).
    

Two scenarios per cell: *dev* (first run, no cassette, cold cache) and *ci* (PR-time repeat, with cassette / cache). Five trials each, trimmed mean of the middle three runs.

![](https://cdn.hashnode.com/uploads/covers/69d1f25c6792e486f60903fd/81e61b92-75e1-48c1-97cc-b17d1f3b75aa.png align="center")

The CI scenario is where the design DNA shows: A drops to ~1.7s per test on both subjects because the cassette replaces the LLM call, while B and C stay at the live-LLM round-trip cost (8.9-16.8s). The control comparison makes the source of the gap concrete: turn the cassette off and run A against a live LLM, and A's wall time lands at 8.7s on the LangGraph subject and 16.5s on the Strands subject, in the same band as B and C. The order-of-magnitude gap on the CI path tracks the cassette, not the library or the assertion API. The dev scenario is close across all three (within roughly 1s of each other on each subject), because every model has to call the real LLM at least once to populate caches, fixtures, or cassettes.

Cost lines up the same way. Per-run dollar cost, taken from the cassette token aggregates against current public pricing: A on CI is exactly $0 because cassette replay does not call the LLM. B and C invoke the live LLM the same way per run, landing at $0.0468 on the Strands subject and $0.0054 on the LangGraph subject. At 1000 PRs per month per subject, B and C come to roughly $5-$50 in LLM charges; A stays at zero. The figures multiply across subjects and tests in any real agent codebase.

The trial-count column is its own story. For each cell the harness ran until five trials passed; with cassette replay this happens on the first attempt, but live invocations of the LangGraph supervisor do not always converge in five tries. On the LangGraph subject, A needed 5 attempts for 5 passes in both dev and CI, B needed 9 attempts in dev and 5 in CI, and C needed 7 attempts in both dev and CI. The Strands subject's simpler trajectory needed 5 attempts for 5 passes in every cell. The flakiness is concentrated where a live LLM has to pick a routing decision in a multi-agent supervisor.

What I had not predicted was the failure mode that surfaced under a model upgrade. The first canonical run of this benchmark used `gpt-4o-mini`, and the LangGraph supervisor's assertions hit 5 attempts for 5 passes reliably. After OpenAI [released](https://openai.com/index/introducing-gpt-5-4-mini-and-nano/) `gpt-5.4-mini` in March 2026 as a higher-capability successor to the gpt-4o-mini class, I rerecorded the cassettes against the new model and reran. The assertion code was unchanged, the agent topology was unchanged, the cassettes were freshly recorded against `gpt-5.4-mini`. B and C nonetheless started needing 7-9 live trials to collect 5 passes per cell. A still hit 5 attempts for 5 passes because the cassette pinned the trajectory at record time. The flakiness was not a property of LangGraph or of the assertions. It was a property of moving from one model generation to the next, and any team that runs live-LLM assertions in CI will hit some version of this on every model upgrade cycle.

There is a related and increasingly relevant point to flag. Reasoning-class models (the GPT-5 series and earlier reasoning models like o1, o3, and o4-mini) accept `temperature` only at its default value; passing 0 or any specific value is rejected by the API. That removes a knob teams used to rely on for keeping live-agent assertions stable, and it is a directional shift across providers, not just one model line. Cassette replay sidesteps the issue, because the LLM is not in the hot path at test time. This is not the kind of claim a single benchmark can carry on its own; one subject in one round is too narrow a basis for general conclusions. It is worth flagging because the operational pressure goes one way.

The cassette's strength in this story is also its boundary, and that boundary should be named directly. Pinning the trajectory at record time means the cassette does not see drift in the model's behavior between recordings: if the LLM starts routing differently tomorrow, a cassette recorded today will keep the test green until someone re-records it. The assertion a cassette enables is "did the agent code call the expected tool with the expected arguments given the recorded trajectory," not "did the LLM make the right judgment in the first place." That second question is exactly what an LLM-as-a-Judge metric on a live trace is built to answer. The practical move, then, is to pair the two execution models rather than rank them. A team running only cassette replay will miss model-level regressions and need a separate process (manual canary, scheduled re-recording with a judge in the loop, production sampling) to catch them. A team running only live judging at the PR gate will pay for it on every push.

A few caveats on the numbers, in line with the data's actual fidelity:

*   The wall-time figures include pytest startup and subprocess overhead because they are measured around `subprocess.run`. The 1.7-second figure is "what the developer sees on a PR," not "the assertion engine in isolation."
    
*   The hardware was a 12-CPU macOS arm64 box on Python 3.14. Absolute seconds shift on different hardware, but the order-of-magnitude gap on CI does not.
    
*   AgentCore Evaluations may carry an additional per-evaluation charge whose price is not yet publicly documented; the dollar figures here cover the LLM portion only.
    

The full results, methodology, and counting rules live with the [agentverify execution-model trajectory benchmark](https://github.com/simukappu/agentverify/tree/main/benchmarks/execution-model-trajectory) (this run: `results-2026-05-17T232008.md`).

Reading these numbers as "agentverify is faster" misses what the data shows. The three execution models occupy measurably different design quadrants. Cassette replay behaves like a test, trace decorator and trace export behave like evaluations, and the right move on a real PR is to combine them rather than choose between them. A team would reasonably want to layer:

*   a deterministic test primitive on T3 × M1 × S2 for trajectory regressions
    
*   AgentCore Evaluations or DeepEval on T1 × M2 × S3 for response-quality regressions
    
*   Bedrock Guardrails on T1 + T5 × M1+M2 (Runtime modifier) × S4 for content-level filtering of model outputs
    
*   AgentCore Policy on T5 × M1 (Runtime modifier) × S4 for authorization on tool calls
    
*   observability across all of them.
    

## Closing — design the CI before picking the tool

AI agents are about to live in the same CI/CD pipelines that everything else lives in. PRs need to merge in minutes, with cost that scales linearly with the number of PRs and not with the size of the team. Quality gates that depend on a live LLM at every push come under cost and latency pressure that some teams will not absorb at scale, especially as agent fleets grow and per-PR test counts compound. Quality measurement, the slower kind, is still valuable, but it tends to belong at staging or in production sampling rather than at the PR gate.

For some teams, a live LLM in CI is workable: small agents whose end-to-end run completes in seconds, low PR volume, an existing operational story for handling API keys in CI, or a willingness to absorb the per-PR LLM bill in exchange for not maintaining a separate determinism layer. The point is that as the agent surface grows, the deterministic layer becomes the cheaper path to keep the PR gate fast and cost-bounded.

That implies a deterministic layer for teams that need one. Some way to fix the agent's non-determinism long enough to write a normal assertion against it. Cassette replay is one approach (the one taken by the test primitive I work on); careful mocking is another; pinning to lower-temperature deterministic modes is a third where it remains available, though that knob is going away in newer model lines. Whichever approach a team picks, the CI needs to keep working without an LLM API key in the pipeline and without a per-PR bill that compounds.

The thread tying this article to the [Architecture Dojo posts](https://blog.simukappu.com/series/architecture-dojo) on this blog is one I keep coming back to. The 2024 post argued for bulkheads and shock absorbers as two complementary primitives: one to statically bound failure, the other to dynamically contain it. The composition was the point. Agent evaluation has the same shape. Testing pins the deterministic layer (tool calls, arguments, trajectory structure) where assertion is cheap; evaluation contains the probabilistic layer (response quality under variance) where a judge LLM is the only available verdict. Trying to make one absorb the other produces tools that disappoint both audiences, just as protecting only the write path produced services that went down on the read path. The next post in this series goes deeper into the deterministic side: where cassette replay's boundary actually sits, why the disappearance of the temperature knob shifts the design constraints rather than just the implementation, and how to think about the CI strategy when one half of an agent's behavior is reproducible and the other half is not.

So the question I would put to readers is concrete. How are you running CI for your agents today? Are PRs gated on a live LLM, on a cassette or trace replay, on a mock, on something else? Where does the test for "the agent did the right thing" live in your pipeline, and how often does it false-fail? If you have a CI design that has held up at scale, or one that broke in an interesting way, I'd like to hear about it.