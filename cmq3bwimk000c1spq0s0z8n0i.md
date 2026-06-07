---
title: "Scaling Without Losing Count — Architecture Dojo 2022"
seoTitle: "2 Design Challenges, One Problem: Architecture Dojo 2022"
seoDescription: "The first Architecture Dojo, revisited: two design challenges that were one problem, and what nearly eight years maintaining one plugin"
datePublished: 2026-06-07T05:15:42.288Z
cuid: cmq3bwimk000c1spq0s0z8n0i
slug: scaling-without-losing-count-architecture-dojo-2022
ogImage: https://cdn.hashnode.com/uploads/og-images/69d1f25c6792e486f60903fd/43ff8385-e138-47c5-bdf5-64854c7b3069.jpg
tags: aws, software-architecture, scalability, system-design, distributed-systems

---

On stage, you declare a design correct. In production, you find out what that correctness was quietly resting on.

In 2022, at the first Architecture Dojo at AWS Summit Japan, I stood on stage and led the answer to one of two design challenges. I was confident in it. By the standards of a design review, it was correct. But by then I had already spent a few years on the other side of that confidence. Since 2018 I had been maintaining an open-source tool that sits inside thousands of production pipelines, which is a less common vantage point than the design-review seat. From there I kept watching the same class of guarantee I was declaring on stage get quietly broken in the field, not in that exact system, but in the same shape, again and again. That gap, between the correctness I declared and the correctness I observed, is the reason that when I hosted the Dojo in 2025, I changed the format.

This post goes back to where the series began. ([2022 session recording](https://youtu.be/C7trZIt5H3w), in Japanese.) The two challenges that year looked unrelated: a flash-sale inventory service and a SaaS metering system. Four years later, I think they were one problem wearing two faces, and the problem is the one in the title. How do you scale a system without losing count of the numbers you are forbidden to get wrong? The customer-facing specifics here are composites; the design choices and the open-source history are exact. The views are my own.

![](https://cdn.hashnode.com/uploads/covers/69d1f25c6792e486f60903fd/28824a60-945e-42de-9790-a656cf4e8678.jpg align="center")

That first edition ran as an online-only broadcast, the AWS Summit Japan of 2022 being a pandemic-era virtual event, with the three of us presenting to a camera rather than a hall. The series exists at all because of Eiichiro Uchiumi, who conceived Architecture Dojo and hosted it from that 2022 debut through 2024. I inherited the host's chair from him in 2025, and most of what I understand about how to run a design conversation on stage, I learned from watching him do it. This post is, in part, a note of thanks for the format he built.

> **TL;DR**
> 
> 1.  **The flash-sale challenge was about protecting one number under concentrated load.** Preventing oversell while a single hot item absorbs all the traffic pushes you through sharding, a read replica, and asynchronous reconciliation, each step trading one correctness risk for another.
>     
> 2.  **The metering challenge was the same problem, wearing the face of billing accuracy.** A heavy tenant is a hot item, double-counting is oversell, and the design starts by deciding who is responsible for which guarantee, not by drawing boxes.
>     
> 3.  **The guarantee in a design doc and the guarantee in production are different objects.** Years of maintaining the Kinesis output plugin those designs lean on taught me that the consumer-side idempotency the design assumes is the assumption production breaks first.
>     
> 4.  **That gap is why the 2025 Dojo dissected real systems instead of solving puzzles.** Taking a live system apart with the people who run it fits how I prefer to work, alongside the teams living with the constraints rather than handing down a finished answer.
>     

## Challenge 1: Protecting one number under concentrated load

The first challenge, presented by my colleague Tomoya Okuno, was a flash-sale inventory service. An apparel retailer runs sales where a limited number of popular sneakers go on sale at a fixed time, traffic spikes the instant the sale opens, and the rule is absolute: never oversell. The design has to absorb a flood of requests while keeping one number, the remaining stock for a hot item, exactly right.

The starting point is simple. Hold the stock count in Amazon DynamoDB, and decrement it with a conditional write that fails if stock would go negative. That single conditional write is the whole correctness story: the database refuses to oversell, atomically, no matter how many requests arrive at once.

The trouble is that "no matter how many requests arrive at once" runs into a physical limit. All those requests hit the same item, and a single DynamoDB partition has a throughput ceiling. Concentrate enough buyers on one sneaker and you exceed what one partition can serve. So the design shards: split a product's stock across multiple partition keys, decrement a randomly chosen shard, and let the write load spread across partitions instead of piling onto one. That fixes writes and creates a new problem, because now checking whether a product is in stock means looking across all its shards, which is expensive. A second table tracks which shards still hold stock, so an availability check no longer scans everything. And because reads concentrate too, a read replica fronted by DynamoDB Accelerator (DAX) absorbs the read traffic, kept loosely in sync because availability is allowed to be a beat behind reality.

One piece remains: when a shard hits zero, the shard-list table has to learn about it, and that update might fail. Wrapping the decrement and the list update in one synchronous transaction would put the spike back onto the hot path. Instead the design lets DynamoDB Streams carry the change to a Lambda that updates the list asynchronously, with a dead-letter queue for failures, so the system reaches a correct state eventually rather than perfectly in the same instant.

What I take from this challenge, looking back, is the rhythm of it. Each move to scale, the conditional write, the sharding, the replica, the stream, solves one bottleneck and opens a new place where the count could drift. Scaling was a sequence of decisions, each one about where and how the system re-establishes the number it cannot afford to get wrong. Challenge 2 walks the same sequence for a different number.

## Challenge 2: The same problem, wearing the face of billing

The second challenge was mine. A SaaS company building an expense-management product needs to meter usage per tenant and show it on a near-real-time dashboard. Some features bill per transaction, others by duration of use. Unit prices can change, and a charge must always reflect the latest price rather than the price at the time of use. Dashboard figures reset daily.

On the surface this has nothing to do with selling sneakers. Underneath, it is the same problem. A heavy tenant generating a flood of usage events is a hot item. Counting a usage event twice is oversell. And the number you are forbidden to get wrong is the billed amount.

So I did not start by drawing an architecture. I started by deciding who is responsible for which guarantee. The application side optimizes for serving its users: if reporting usage is delayed during an incident, that is acceptable, and it stamps each usage record with a unique ID. The billing side takes on everything hard: it counts usage that arrives late, and it never double-counts. Drawing that line first is what made the rest of the design fall out, because every later choice traces back to which side owns which promise.

From there the design moved in three steps, each answering a problem the previous step exposed. First, reporting every transaction synchronously to a database made the database the bottleneck, so the pipeline pre-aggregates into one-minute buckets before writing. To keep a heavy tenant from concentrating load on one place, usage events are partitioned by transaction ID, so throughput spreads regardless of how lopsided tenant volume is. This is the same instinct as sharding a hot product, applied to a hot tenant. Second, synchronous reporting failed whenever the application or billing system hiccuped, and events did not always arrive in order, so reporting became an asynchronous push, with aggregation keyed off processing time rather than event time to tolerate late and out-of-order arrivals. Third, asynchronous delivery meant a transaction could arrive twice, or a write could be retried, either of which would double-count. So the pipeline deduplicates on transaction ID and writes each aggregate against a rounded-timestamp primary key, letting the key constraint itself enforce idempotency.

The changing-price requirement drove one more separation. Rather than freezing a charge when usage happens, the pipeline stores raw usage as the durable fact and computes the charge at display time by joining against the current price table. A price change rewrites nothing; the next computation simply uses the new value. The whole thing runs on Kinesis Data Streams into Lambda for deduplication, Kinesis Data Analytics for the windowed aggregation, and Aurora behind RDS Proxy for the figures the dashboard reads. (AWS has since discontinued Kinesis Data Analytics for SQL; the windowed aggregation carries over to its successor, [Amazon Managed Service for Apache Flink](https://docs.aws.amazon.com/managed-flink/latest/java/what-is.html), without changing the design.)

![](https://cdn.hashnode.com/uploads/covers/69d1f25c6792e486f60903fd/7bc40d8b-617c-49ef-a201-07322fce83bc.png align="center")

Put the two challenges side by side and the shared skeleton is hard to miss.

| Challenge 1 (retail stock) | Challenge 2 (SaaS billing) | The shared problem |
| --- | --- | --- |
| Hot product | Heavy tenant | Load concentrating on a hot spot |
| Preventing oversell | Preventing double-counting | Protecting a number you cannot get wrong |
| Conditional write | Rounded-timestamp key constraint | Correctness enforced by a constraint |
| Streams plus Lambda, async | Kinesis pipeline, async | Crossing the limit of synchronous work |

Two SAs, two unrelated briefs, one problem solved twice. The two are not identical in strength: the flash-sale design enforces its number synchronously, in the instant of the conditional write, while the metering design settles its number eventually, once dedup and aggregation have run. But the move that matters is the same in both, naming the number you cannot get wrong and then deciding where the system re-establishes it. That symmetry is the part of the 2022 Dojo I keep coming back to.

## The guarantee on stage and the guarantee in production

Here is the thing the table does not show. The metering design rests on a sentence I said with confidence on stage: idempotency is guaranteed by the primary-key constraint, and consumers downstream are expected to be idempotent. As a design statement, that is correct. As a description of what happens in production, it is the assumption that breaks first.

I know this because I have maintained the [Fluent plugin for Amazon Kinesis](https://github.com/awslabs/aws-fluent-plugin-kinesis), an awslabs project, for nearly eight years. It has passed 20 million downloads and sits inside a great many production data pipelines built on exactly the kind of Kinesis stream my Dojo answer used. Maintaining one component across that many deployments shows you something no single design review can: the recurring gap between the guarantee a design declares and the behavior a system exhibits.

The plugin's contract is at-least-once delivery, with batching and retry, and an expectation that consumers are idempotent. Some of that resilience predates me. The retry-count default was raised after [an early report](https://github.com/awslabs/aws-fluent-plugin-kinesis/issues/69) (opened 2016, closed 2017) showed that too few retries let a throughput spike of only a few seconds drop records to a `ProvisionedThroughputExceededException`. The plugin resets its backoff whenever any record in a batch succeeds, after [another report](https://github.com/awslabs/aws-fluent-plugin-kinesis/issues/42) (opened 2015, closed 2016) showed a partially successful batch would otherwise keep lengthening its backoff until one unlucky node near a saturated shard crawled while its peers ran normally. Both were resolved by the previous maintainer, before I took over in 2018; I inherited the code with those fixes already baked into its defaults. The one I closed myself came later: [when a stream is over capacity](https://github.com/awslabs/aws-fluent-plugin-kinesis/issues/150) (opened 2018, closed 2021), the plugin absorbs the throttling inside its own retry loop, so the standard Fluentd output metrics a team would naturally watch can read zero while the plugin strains underneath. The layer doing the retrying was not the layer being monitored.

Each of those is a small thing. Together they make a point I did not fully appreciate when I was on stage in 2022. The library can enforce its own behavior, how it batches, how it retries, what it resets. It cannot enforce the consumer-side idempotency that its contract, and my Dojo design, assumes. A deployment whose consumers are not actually idempotent gets the duplicates the design said could not happen, and it gets them far from where anyone declared the guarantee. The correctness I asserted on stage was real, but it was conditional on a promise that lives in someone else's code, in a layer the design diagram does not draw.

There is a quieter point in those issue dates. The guarantee gets re-examined across maintainers, not just across layers. By the time I inherited the plugin, a previous maintainer had already met and closed the failure modes behind two of its defaults; the one I worked on myself surfaced years after the code that caused it shipped. The person who declares a design correct and the person who handles the moment that correctness gives way in production are often not the same person, and they may be years apart. I happened to play both roles, in different contexts, and seeing them up close from both sides is what made the gap legible to me.

## Why the 2025 Dojo dissected real systems instead of solving puzzles

The Dojo's usual format, the one we ran in 2022 and again in 2023 and 2024, hands the audience a fictional brief and builds an answer to it on stage. There is real value in that. But a fictional brief lets you choose your own constraints, and choosing your constraints is how you arrive at a design that is correct in the way a design review is correct, and untested in the way production tests you. After enough years watching declared correctness meet production from the maintainer's seat, I wanted, for once, to run the session the other way around.

So when I hosted the Dojo in 2025, we made it a one-time special edition. Instead of solving puzzles, we dissected two real production systems on stage and traced how each one actually holds its guarantees under real constraints. I wrote up what came out of that in a [separate post](https://blog.simukappu.com/4-lessons-from-dissecting-production-systems-at-scale-architecture-dojo-2025), so I will not repeat the lessons here. What matters for this story is the motive behind the format. Declaring an optimal answer to a fictional brief is a little like handing down a finished method; taking apart a system that is already alive, with the people who run it, is closer to how I actually like to work, which is alongside the teams living with the constraints rather than above them. That is the same reason I find the gap between stage and production worth writing about at all.

The through-line from 2022 runs straight into those lessons. Deciding who owns which guarantee before drawing boxes, and designing how the system reconciles when consistency slips rather than pretending it never will, were the moves that made the metering pipeline work. Seeing the same moves show up, years later, as the recurring shape of how real systems stay correct, was the quiet confirmation that the 2022 challenges had been about something more durable than the services we happened to choose.

## What's next

Architecture Dojo returns to AWS Summit Japan on June 26, 2026, and the theme is architecture in the AI era. For this one we are back to the usual fictional-brief format, the one the 2025 special edition stepped away from. Returning to it is the right tool for where the field is. You can dissect a live system only when the field has settled enough to have production systems worth dissecting, and for AI applications and agentic workflows, the settled best practices do not exist yet. There is not yet a canon of running designs to take apart, so we construct problems on stage and reason about a space that is still in motion.

What I want to bring to that stage is the question this post has really been about. When a probabilistic component enters the system, the same input stops guaranteeing the same output, and parts of what we used to declare correct move into the realm of things you observe and reconcile instead. But not everything changes. The 2022 challenges looked like a sneaker sale and an expense tracker, and underneath they were one problem about protecting a number under load. I suspect the AI era has its own invariants hiding under unfamiliar surfaces, and the work worth doing is telling them apart from what is genuinely new. The first Dojo asked how to scale without losing count; the next one asks which of those hard-won problems survive a shift to systems that no longer behave the same way twice.

Watch the 2022 session recording (Japanese): [https://youtu.be/C7trZIt5H3w](https://youtu.be/C7trZIt5H3w)  
Past sessions: [2025](https://youtu.be/L-NcmkkDJMI) | [2024](https://youtu.be/eoBlprMYx_E) | [2023](https://youtu.be/s9YqEELWutA)