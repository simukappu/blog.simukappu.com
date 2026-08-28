---
title: "The Unit Economics of an AI Agent — Budgeting Before You Build"
seoTitle: "AI Agent Unit Economics: the Budget Decides the Design"
seoDescription: "Business arithmetic sets what an AI agent may spend per request. How one design hit a third of a US cent, and the one role where self-hosting pays."
datePublished: 2026-08-27T14:57:37.937Z
cuid: cmtbncvp7000009ksg32kfhlp
slug: the-unit-economics-of-an-ai-agent-budgeting-before-you-build
ogImage: https://cdn.hashnode.com/uploads/og-images/69d1f25c6792e486f60903fd/899043f7-2fc7-46d2-bcd6-34bd52bee60f.png
tags: aws, system-architecture, gpu, unit-economics, llms, agentic-ai

---

Same workload, same tools, one model swapped: the cost per request moves by 96x. Somewhere in that range sits a budget your business has already decided, and you can compute it before you write a line of code. Agreeing on that number early matters more than getting it exactly right: a stated target can be corrected when conditions move, and an unstated one keeps the argument open.

This is the economics side of a design problem from [Architecture Dojo 2026](https://blog.simukappu.com/three-responses-to-ai-s-probabilistic-core-architecture-dojo-2026), the AWS Summit Japan session I host: build a shopping assistant on top of a probabilistic model and hold it to a fixed cost per request. I wrote the problem, re-ran [Tomoya Okuno](https://www.linkedin.com/in/tomoya-okuno/)'s measurements, and generalized them into the decision rule below. The measurements are his; the retelling and any errors are mine. The [session deck](https://pages.awscloud.com/rs/112-TZM-766/images/R01-03_0626_ARC446_v2.pdf) (in Japanese) reports where the finished design landed: 0.49 yen per request, 2.15s time to first token (TTFT) at P50, 3.4% quality degradation. The budget was met; this article is about how it decided the design.

> **TL;DR**
> 
> 1.  **The budget is arithmetic.** Four business numbers and grade-school arithmetic set the cost per request you are allowed to spend before any code exists, and because the budget closes per request, no traffic forecast is needed. Ours came to 0.5 yen, a third of a US cent, against a measured spread of 96x between the cheapest and the most expensive model on the same workload.
>     
> 2.  **Getting inside the budget is an allocation problem.** A semantic cache is worth less as a discount than as spare budget: every request it absorbs at near-zero cost funds one that has to go to the expensive model. That makes the escalation ceiling a dependent variable, set by how cheap the rest of the traffic is.
>     
> 3.  **Self-hosting an open model pays off on one kind of role; managed inference is the right default everywhere else.** Three conditions decide whether a role can clear the break-even rate: the traffic is steady and high-volume, the model fits one GPU, and the input is mostly fixed prefix. A 4B router model met all three and matched the cheapest managed models on cost while beating them on quality. Outside those conditions the cost arithmetic points back to managed inference, which prices in capacity elasticity and the operational surface you would otherwise own. And managed prices keep falling as open models improve: one frontier tier's price fell 80% three weeks after it launched.
>     

## The budget is arithmetic

Begin with what you can afford to spend per request, not with what a model happens to cost. For a shopping assistant whose job is to lift conversion, that number comes out of business planning.

Every yen figure here converts at 150 yen to the dollar. Suppose an average order value of 5,000 yen ($33), a 3% conversion rate, and a 5% margin. That is 7.5 yen of expected profit per session. If the assistant lifts conversion by 20%, it creates 1.5 yen of new headroom per session. A session runs a median of 3 turns. Under those assumptions the budget is 0.5 yen per request: four business numbers, three multiplications, and one division. No modeling, no forecast.

The part that matters for your own build is what the arithmetic leaves out. The budget closes per request, so business scale cancels out of it. You do not need to know how many requests you will serve to know what each one is allowed to cost. That closure is Okuno-san's, and the part of this verification I have reused most. The target is fixed before the first line of code, which is what lets it order every design decision that follows.

Only one input is really a guess. Move the conversion lift across a conservative 12%, a central 20%, and an aggressive 30%, and the budget moves to 0.30, 0.50, and 0.75 yen. The shipped design cost 0.49 yen per request, or 1.47 yen per session, so the lift that makes it break even is 1.47 divided by 7.5, about 19.6%. This design is a bet that the assistant lifts conversion by roughly 20%, which published figures make look conservative: Amazon Rufus users convert at [2.74x non-users](https://sensortower.com/blog/scroll-to-sold-what-amazon-rufus-tells-us-about-shopper-intent) on a 60,000-shopper panel, though those users self-select. The budget is a break-even line drawn from the whole of the incremental margin, not a profit target, so a design that just clears it is not yet making money. It is not losing it.

Now the distance. On the same workload, measured with each model's own token structure rather than a price-sheet comparison, the cheapest and the most expensive model sit 96x apart: Amazon Nova Micro at about 0.076 yen per request, Claude Sonnet at about 7.3 yen. Those two mark the ends of the range, not the design's answer. The cheapest single model that cleared the quality bar on its own was Claude Haiku 4.5, at 2.43 yen, which by itself is 4.9x over the 0.5 yen budget.

The cost itself comes from one place. Input tokens dominate, and input is set by tool round-trips and by how many products the search returns, not by how long the user's query is. A search turn in this design carries a fixed prefix plus roughly 14,000 tokens of results, and each additional product adds about 1,000. The optimization order that falls out of that is model choice first, then trimming round-trips and tool definitions, then returning fewer products. "Make the prompt shorter," the suggestion I hear most often, is not on the list.

Model choice is a trade-off against quality, though. A straight swap to a lighter model drops Correctness, an LLM-judged quality axis in [AgentCore Evaluations](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluations.html), from Haiku's 0.89 to 0.67 for Amazon Nova 2 Lite and to 0.33 for Qwen3.5-4B. Haiku's score is averaged over a different scenario set (192 versus 200), so the exact gaps are not directly comparable; read them only as the direction quality moves as the model gets lighter. The point is narrower anyway: a 96x spread is not a problem you solve by picking one model.

The 4.9x was measured against Haiku at alpha time. On 2026-07-30, OpenAI's GPT-5.6 Luna fell 80%, from $1.00/$6.00 to $0.20/$1.20 per million tokens ([OpenAI's announcement](https://openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6/), [AWS What's New](https://aws.amazon.com/about-aws/whats-new/2026/07/openai-gpt-terra-luna-pricing-bedrock/)). Applied to this workload's token structure, that projects to about 0.50 yen per request, or 0.36 with prompt caching, which would put a single frontier model on the budget line. Two caveats keep this from being an answer. That 0.50 yen is Luna's list price multiplied by the tokens measured here; its quality on this workload is not measured, and the constraint is quality within 10% of alpha. And Luna launched only three weeks earlier, on 2026-07-09, so the price we would have designed around had already changed. Model prices change between one design review and the next; the business numbers behind the budget move on a slower clock.

## The budget decides the escalation ceiling

The naive reading of a cache is that it makes things cheaper. The reading I found useful is that it frees up budget for the expensive model.

A semantic cache lands on the use cases whose answers are stable (policy FAQs, greetings) rather than those whose answers move with the data (open-ended search), where a hit expires with the results. Stability decides what you can cache; cost decides what caching is worth. Stability can also be designed: FAQ-type questions return a templated pointer to the FAQ page instead of a generated answer, the same choice Rufus makes.

The stable answers are also the cheap ones, so a hit rate of 22.6% turns into an effective cost reduction of only 14% and a mean TTFT reduction of about 11%. Both figures are the cache's own contribution to the blended cost, not a first step down from Haiku's 2.43 yen. Read as freed-up budget, though, that 14% decides what fraction of traffic Haiku can take.

That reframes the escalation threshold. It becomes a dependent variable derived from the budget, not a knob you tune. This is the same fact as the budget closing per request, one step on: whatever the cheap paths leave unspent is the escalation budget.

The shipped design routes each request out through one of four exits: the semantic cache, a template, the lightweight model, or Haiku. Break the finished 0.49 yen down by exit path and the split is stark. A semantic-cache hit and a templated FAQ answer together take 23% of requests and reach no generation model, so their response-generation cost is zero. They are not literally free: a cache hit still pays for an embedding lookup, which costs a small fraction of one generation call and sits outside the 0.49.

The 77% that do reach a model split unevenly. The lightweight model, Nova 2 Lite, handles 66.3% of traffic and accounts for 54.1% of the cost. Haiku takes 10.7% of traffic but 44.6% of the cost, at about 2.05 yen per escalated request. That is under the 2.43 yen Haiku costs across all traffic, because the requests that escalate carry fewer input tokens than average. The 10.7% is what the budget allows: one request in ten can cost four times the budget because the cheap paths spend nothing. The router model's one-shot classify-and-extract step, which runs on every uncached request, adds 0.006 yen amortized across all traffic. The traffic shares are a design assumption; the real figures, including the infrastructure cost of the zero-inference paths, would need production measurement.

![](https://cdn.hashnode.com/uploads/covers/69d1f25c6792e486f60903fd/0f353d66-017c-4fa3-afd9-288a70faadfa.png align="center")

Which requests should escalate is its own decision, and answering it well is one of the reasons this design runs a model of its own. Escalating the highest-scoring 20% of traffic caught 20 of the 38 failing queries, precision 50.0% and recall 52.6%, about 2.6 times what escalating the same share at random would find against a base error rate of 19.0%. That 20% is about double what the budget allows, so the shipped ceiling catches fewer failures.

The query's intent alone does not predict response quality. Neither do the router's own [log probabilities](https://developers.openai.com/cookbook/examples/using_logprobs) (how confident the model was in each token it generated) over its tool-planning tokens, which score AUC 0.561, barely above chance. Pair those probabilities with the shape of the tool-use output (which tools it called, how long the output ran, whether it left a reference unresolved) and the AUC rises to 0.818. That pairing needs the per-token confidence scores, which most managed APIs do not expose but a self-hosted model does.

The same budget logic decides a latency trade. Splitting intent classification and tool-argument extraction into two parallel inferences cuts the router model's median latency from 2,432 ms to 1,182 ms, and the p99 tail falls further than the median. Each call re-sends its own system prompt, so the step pays about 2.3x its input tokens, which is why the 0.006 yen above covers two calls rather than one. At that scale the increase does not move the request total.

Here is the whole system in one view.

![](https://cdn.hashnode.com/uploads/covers/69d1f25c6792e486f60903fd/f439431e-89ae-4024-b14e-f57affd2d472.png align="center")

## Where the break-even sits

The 4B model that failed as a response generator, at Correctness 0.33, is nonetheless the best fit in the whole design for one specific job: the router model that fronts every uncached request, classifying intent and extracting tool arguments.

Qwen3.5-4B scored 0.33 because it tended to answer directly instead of calling tools: inside a ReAct loop it could not judge when to reach for one. The router never needs that judgment. It runs a one-shot classify-and-extract with a fixed output format, reading the query and page context and emitting an intent label and the tool arguments, once.

On that job the small model is not just adequate, it is ahead of the cheapest managed models. On the same [200 scenarios](https://github.com/simukappu/selfhost-vs-bedrock-router-model-quality/blob/main/dataset/how-it-was-built.md) and prompt, with the same deterministic grader (exact intent match, tool-name set match), self-hosted Qwen3.5-4B scores 90.5% on intent and 85.5% on tool match, against Nova Micro at 84.5% / 71.5% and Nova 2 Lite at 86.0% / 74.0%. These are single runs, and guided JSON decoding gives Qwen an edge the numbers do not separate out: its output is schema-valid by construction, which flatters its tool-match number. Claude Haiku (92.5% / 89.0%) and GPT-5.6 Luna (93.0% / 89.5%) score higher still, but they sit in a different price class even after Luna's cut; on this task Haiku costs roughly 60x what the self-hosted 4B does.

This invites the objection self-hosting gets first: isn't a GPU expensive? By the hour, yes. A p5.4xlarge, a single H100, on a one-year all-upfront Savings Plan runs about 607 yen an hour. But for the router model's workload it sustains a ceiling of roughly 49 requests per second, the last rate step before the queue starts growing. At 607 yen an hour spread over 49 requests a second, that comes to about 0.0034 yen per request. On this one-shot task Nova Micro costs 0.0055, so self-hosting is about 1.6x cheaper. That ratio was the number I expected to matter, and it turned out to be the least interesting one in the comparison: this step is only 0.006 yen of a 0.49 yen request, so cutting it by 1.6x barely changes the total. Treat the two as level on cost, then, and what you bank on this role is the accuracy.

Plotted across all five models, the cheapest point is also one of the most accurate.

![](https://cdn.hashnode.com/uploads/covers/69d1f25c6792e486f60903fd/c5a23dc0-8e56-4ace-8c7a-0de87b5d3e30.png align="center")

The router model is one role. The rule I took away from re-running this verification is that self-hosting breaks even at the role, not at the size of the company. Three conditions decide which roles qualify. The role has to take a steady, high volume of traffic, which makes a step on the path of nearly all requests the natural candidate. The model has to be small enough to fit one GPU. And the input has to be mostly fixed prefix. A router model that classifies and extracts meets all three; a full response generator fails the last two.

The third condition is the one that decides the cost. A fixed prefix means the front of the prompt (the instructions and the output format) does not change from request to request, and only the query at the tail does. When the prefix repeats, the GPU reuses the key-value cache it already computed and only processes the tail, which decides how many requests one instance sustains. The router model runs about 90% fixed prefix, because its instructions pass the thirteen tools as one-line signatures and only the query varies. The full agent carries the tool definitions in full, several thousand tokens of them, and then appends roughly 14,000 tokens of search results, which drops its fixed share closer to a quarter. So one instance handles many times more requests on the router-model workload than it would on the full agent.

Because self-hosting is billed per hour and managed inference per request, the comparison reduces to how full the role keeps the GPU. Solve the same equation the other way, with Nova Micro's 0.0055 yen as the target, and it returns a sustained rate to hold your workload against.

|  | Unit cost | Break-even rate |
| --- | --- | --- |
| 1 instance | 0.0034 yen | ~31 rps (ceiling is 49) |
| 2 instances, for redundancy | ~0.0069 yen | ~61 rps, ~5.3M inferences a day |
| 2 instances, managed price halved | ~0.0069 yen | ~123 rps (two sustain 98) |

Redundancy cancels the cost advantage. Production wants two instances rather than one, so at the load that fills a single one, each runs at half capacity and the bar doubles. Redundancy therefore needs more than a 2x advantage on one instance to survive, and this role has 1.6x. Level on cost arrives by a second route, from the other side: a GPU held half idle costs a little more than the managed call does. On this role the unit cost was not the reason; the accuracy was. The budget needed no traffic forecast. Self-hosting does. The three conditions get you to where the arithmetic is worth running; the utilization the role actually sees decides the answer.

Which side of that equation the market moves is the part I would watch. The break-even rate is set by the managed price, so every cut there raises the bar the GPU has to clear, and the last row shows one halving putting it out of reach. Open models improving is also what pulls managed prices down, so the force that makes self-hosting viable keeps shrinking the set of roles where it pays.

## What the break-even does not price

The break-even math is inviting. What it does not count is the work of standing one up and keeping it running.

Getting it running takes only three steps: bring up a GPU instance with vLLM behind an OpenAI-compatible endpoint, register it behind an internal load balancer, and point the agent's inference URL at it. The costs that setup does not include:

*   **Capacity becomes something you plan.** Even in a test environment the instances were hard to get, so the setup reused existing ones and co-located models on one GPU rather than assuming it could recreate them from infrastructure code. There are ways around that, and each one is a choice you now own.
    
*   **Serving-stack support for each GPU generation matures on its own schedule.** On Blackwell, vLLM's sampler JIT misread the architecture and crashed, so it had to be disabled and eager execution forced, while another stack ran the same card without that; the H100 needed a different workaround. Getting a model to start assumes you are tracking a layer that moves month to month.
    
*   **The surface around the model is all yours.** Tool-call parser selection, prefix caching, tuning max sequence length against GPU memory, health checks and target registration, a rollback path when you swap a model. A managed API hides all of these; self-hosting means you own them.
    
*   **The work does not end at launch.** Model updates, scaling, and on-call all continue. What used to be included in a per-token price becomes staff time.
    

The other side of that trade has its own entries. This design's routing reads per-token confidence scores, which most managed APIs do not expose; choosing managed can remove a signal the architecture was built on. Model versions also move on the provider's schedule: when one is retired you inherit the migration, and the quality evaluation and routing thresholds tuned against the old version come due on a date someone else chose. For a design whose business case is settled and whose numbers are measured, the cheapest thing to do is leave the model where it is. Self-hosting allows that; a retirement schedule does not. That option is a reason to self-host that the break-even does not price.

So with both sides in the break-even math, managed inference is still the right choice for most of the teams I work with. Those four costs are what a service like Bedrock folds into a per-request price, together with the elasticity to absorb a quiet hour or a spike. On cost, self-hosting earns its place only on a role that clears the three conditions, the utilization test, and the operational costs above. Running the break-even is worth it either way, because it tells you which of the two cases you are in and why.

## Closing

Unit economics is a design discipline rather than a one-time estimate: derive the budget from the business, decompose the cost with measurement, and keep re-running both as the inputs move. While this article was being written, Luna's published rate fell 80%. The price moved; the arithmetic did not.

Coding agent adoption often ran ahead of a formal business case. An agent inside a customer-facing product usually needs one, and that case is harder to write. Someone has to say what the spend buys, and a cost per request is an unfamiliar line item. I wrote the first section for the people who have to make that case.

One boundary is worth marking. The arithmetic works because the feature sits on a revenue stream: cost comes out of margin. An agent your own employees use displaces staff time instead, with a value side much harder to measure than a conversion rate the business already tracks. The question of what a request can cost carries over; this way of answering it does not, and that is what I want to write up next.

Whichever case you are in, I would not plan on the price curve doing the work. The budget here came from a business, not from a price list, and the 4.9x gap to the model that passed the quality bar was closed by design decisions. Waiting for someone else's model to get cheap enough is a bet on another company's roadmap, on their schedule. Closing the same gap with an architecture you can reason about is a bet on your own engineering, and it is the one you can place this quarter. I would take that one, and I want more teams to have the choice.

The design, the dataset, and the measurements are Tomoya Okuno's; the analysis here is mine. If you want to check the numbers, the router-model quality and latency runs are in [selfhost-vs-bedrock-router-model-quality](https://github.com/simukappu/selfhost-vs-bedrock-router-model-quality) and the throughput and cost runs are in [selfhost-vs-bedrock-token-economics](https://github.com/oktomoya/selfhost-vs-bedrock-token-economics). Both ship the scenarios, the graders, and the token accounting, which is what let me re-run them rather than read them. The evaluation framing this builds on is in [AI Agent Evaluation: What, How, When](https://blog.simukappu.com/ai-agent-evaluation-what-how-when), and the full session is [Architecture Dojo 2026](https://blog.simukappu.com/three-responses-to-ai-s-probabilistic-core-architecture-dojo-2026).