---
title: "Scaling Peak Traffic: From Planned Offloads to Unpredictable Bursts"
seoTitle: "3 Peak Traffic Patterns: The 0-to-N Problem Load Tests Miss"
seoDescription: "From planned offloads to unpredictable bursts: three peak traffic patterns, and why the 0 → N arrival pattern breaks systems that pass every load test"
datePublished: 2026-04-14T13:26:07.045Z
cuid: cmnynn6wy00dx2ble67kjfex9
slug: scaling-peak-traffic-from-planned-offloads-to-unpredictable-bursts
ogImage: https://cdn.hashnode.com/uploads/og-images/69d1f25c6792e486f60903fd/0944b19c-c889-46f0-ae9e-5a1adb61cd2a.png
tags: aws, software-architecture, scalability, system-design, serverless

---

Your system can handle 10,000 requests per second. But can it handle going from zero to 10,000 in one second?

Peak traffic forces a design choice: what do you include in your scaling scope? Compute, data, or both? How do you handle the transition from normal to peak load? And what happens when the burst environment breaks?

Over the past few years, I've worked on peak traffic offloading designs across different systems: a large e-commerce platform handling tens of thousands of requests per second at peak, and a high-traffic web application serving millions of daily users. The patterns here are drawn from real systems I've worked on; specifics are generalized. What follows are three patterns that emerged from that work. They're presented in the order I encountered them, because each pattern's limitations motivated the next.

> **TL;DR**
> 
> 1.  **Compute + data offload.** Scale both application and database layers into a burst environment. Powerful but expensive: database replicas require continuous replication and warm-up time, making on-demand provisioning impractical for short-duration peaks.
>     
> 2.  **Compute-only shot scaling.** Remove the data layer from the burst scope. Cheaper, but "0 → N" service-in is harder than it looks. Load tests that ramp up gradually won't catch what happens when production traffic hits all at once.
>     
> 3.  **Serverless reactive scaling.** Change the scaling model itself. Don't replace containers; compose them with FaaS as a burst-only layer. You get per-second elasticity for unpredictable spikes, but you're now operating two runtimes.
>     

## Pattern 1: Compute + data offload, where the data layer changes the economics

*This pattern addresses predictable peaks such as sale events with days of lead time. Patterns 1 and 2 come from the same system; Pattern 1's cost lesson is what motivated Pattern 2.*

The context was a large e-commerce platform preparing for a major sale event. The baseline infrastructure, running on-premises, couldn't absorb the expected traffic spike. The goal: offload peak traffic to a burst environment on AWS, without touching the baseline system's architecture.

The design extracted read-path APIs into containers on Amazon ECS, with read replicas of the relevant databases deployed alongside them. We validated 50% traffic offload in production, with over a hundred container tasks and multiple database nodes handling their share of peak load. But the cost math killed it. Database replicas need to be running and replicating continuously; adding a replica takes minutes and replication sync adds further delay, too slow for short-duration peaks. When we modeled even a modest "keep 10% running at all times" configuration, the replica costs alone exceeded what it would cost to simply scale the baseline infrastructure. This is equally true in cloud-native setups: replicas that you want "only during peaks" still need warm-up time that makes truly on-demand provisioning impractical.

That was the first answer to "what do you scale?" and it taught me that **including the data layer in your burst scope fundamentally changes the cost structure.**

But cost wasn't the only lesson. Including the data layer introduced a failure mode that compute-only designs don't have: **the burst environment could serve stale or incorrect data if replication fell behind.** The burst environment had to be disposable. If it broke, the baseline had to handle 100% of traffic without intervention. The isolation mechanism we built for this turned out to be one of the more reusable ideas from this project: a dedicated health check endpoint, separate from the API paths, a control channel that could signal "drain me" without affecting API responses. When replication monitoring detected lag beyond a threshold, an automated process changed the ALB listener rule priority to route health check requests to a fixed 5xx response, causing the upstream load balancer to drain traffic from the burst environment. This happened without touching the API paths, without operator intervention, and without the burst environment needing to know it was being drained. The principle generalizes: in any environment where you can dynamically control health check or readiness probe responses, you have a clean, application-level circuit breaker that's independent of the failure detection mechanism.

What follows is what happened when we applied that cost lesson to the same system.

## Pattern 2: Compute-only shot scaling, the 0 → N problem

*Still addressing predictable peaks, but with a different cost structure. I call this "shot scaling": pre-provisioned capacity, switched on all at once rather than scaled gradually.*

Pattern 1's cost analysis made the answer clear: keep the database out of the burst environment. Pattern 2 scaled only the compute layer, ECS tasks spun up for the event period, connecting back to the existing baseline databases. No replica provisioning, no replication lag to manage, dramatically lower cost. The new problem was something we hadn't anticipated.

### The 0 → N service-in problem

"Service-in," the transition from zero to full production traffic, turned out to be the hard part. When the event started, traffic shifted from 0 RPS to thousands of RPS hitting the burst environment almost instantly. Some tasks spiked to near-100% CPU. 502 errors appeared. The system had enough capacity. The tasks were running. The health checks were passing. But the *pattern* of traffic arrival broke things, and no single factor was the cause. It was a compound failure: ALB target distribution skew, application-level cold-start costs, and health check timing, all triggered simultaneously by the step-function traffic pattern. A gradual ramp-up would have masked every one of these issues. That's exactly what our load tests did, and exactly why they passed.

Here's how we traced it. Pre-launch load testing had passed cleanly, but those tests ramped up traffic gradually, the default behavior of most load testing tools. They validated that the system could *sustain* the target RPS, not that it could *absorb* the target RPS arriving all at once. The production traffic pattern was a step function: zero to thousands in an instant. The load test pattern was a ramp: zero to thousands over minutes.

![](https://cdn.hashnode.com/uploads/covers/69d1f25c6792e486f60903fd/c9451550-7b08-4d26-bea4-593fe9966e7b.png align="center")

When the 502s started, we initially suspected the ALB. Maybe it couldn't distribute traffic evenly across newly registered targets. We checked the target health metrics and saw that some tasks were receiving disproportionately more requests than others during the first seconds after registration. That was part of it. But even the tasks with balanced traffic were showing high CPU. So we looked at the application layer: the first requests to each task were paying initialization costs (JIT compilation such as V8 optimization passes, connection pool establishment, local cache population) that subsequent requests didn't. The health checks had marked these tasks as healthy (they responded to the health check endpoint), but "healthy enough to respond to a lightweight health check" and "warm enough to handle production traffic" turned out to be different things.

The obvious mitigation is gradual traffic introduction: start at 0% weight on the burst environment, ramp to 1% → 5% → 10% → 50% over several minutes. In cloud-native environments with Route 53 weighted routing or ALB weighted target groups, this is straightforward. But in our case, the routing layer had a constraint: weight changes could only be applied once per day. Traffic arrived as a step function whether we wanted it to or not. That constraint is what made the 0 → N problem unavoidable.

I've since seen this same dynamic in cloud-native setups. Any auto-scaling configuration that goes from idle to full load (min capacity = 0, scale-to-zero serverless containers, even a Kubernetes HPA that's been sitting at minimum replicas overnight) faces the same risk. The question isn't whether you have enough capacity. It's whether your system can absorb the *arrival pattern* of that capacity being needed.

The lesson for load testing is concrete: test the ramp-up profile, not just the target throughput. For shot-scaling scenarios, you need a step-function test (full target RPS from second one) in addition to the standard gradual ramp. The gradual ramp tells you whether your system can handle the load. The step function tells you whether your system can *absorb* the load. Most load testing tools default to gradual ramp-up. You have to deliberately configure the step-function pattern, and it's the one that catches the bugs that matter.

**The lesson from Pattern 2: shot scaling requires designing for "service-in," the transition from zero to full load.** The arrival pattern of traffic, not the total capacity, is what breaks things. Shot scaling also exposed a secondary class of issues: implementation assumptions that hold within a single datacenter (HTTP keep-alive defaults, serialized backend calls) break when compute moves across a network boundary. The fixes are straightforward, but they reinforce the same point: placing compute in a new context surfaces problems that existing tests won't catch.

## Pattern 3: Serverless reactive scaling, composing two scaling models

*This pattern addresses unpredictable peaks, the kind where you have seconds, not hours.*

Pattern 2's shot scaling works when you have hours of lead time to pre-provision and warm up. But what happens when you don't? The context shifted to a different system entirely: a high-traffic web application serving millions of daily users. When an external event triggers (a natural disaster alert, a breaking news story), traffic spikes by an order of magnitude within seconds.

Patterns 1 and 2 are proactive: you provision capacity before traffic arrives. When the peak is unpredictable, you need a reactive model: one that scales in response to traffic, not in anticipation of it. But container orchestration's reactive scaling isn't fast enough. Even EC2 Auto Scaling Warm Pools (pre-initialized instances in a stopped or hibernated state) take tens of seconds from stopped state, and keeping them running defeats the cost advantage. This system needed to go from hundreds of containers to several times that, in under 10 seconds. When I looked at this problem, I realized the answer to "what do you scale?" had to change. Not just the scale target, but the scaling model itself.

### The idea: FaaS as a burst-only layer

Most serverless migration stories are about replacing containers with Lambda entirely. This design is different. The baseline workload stays on containers: stable, well-understood, cost-efficient for steady-state traffic. Lambda is added as a burst-only layer that absorbs unpredictable traffic spikes and scales back to near-zero when the spike passes. The baseline never changes. The burst layer is purely additive.

This is a composition of two scaling models, not a migration from one to the other. And that distinction matters, because it means you get Lambda's per-second elasticity without giving up the operational simplicity of containers for your steady-state traffic. But there is a trade-off: you're now operating both.

The existing SSR (server-side rendering) web application was adapted to run on Lambda using [`@codegenie/serverless-express`](https://github.com/CodeGenieApp/serverless-express), behind API Gateway. Backend API responses were cached in Amazon S3 and loaded into each Lambda execution environment's memory on initialization, isolating the burst path from backend load entirely. The design called for the baseline container environment to continue handling normal traffic, with weighted routing shifting overflow traffic to the Lambda path during a spike.

Lambda's scaling model is fundamentally different from containers. Each concurrent execution runs in its own isolated environment with dedicated resources: no CPU contention between requests, no shared thread pool, no noisy-neighbor effects. For example, the [burst concurrency quota](https://docs.aws.amazon.com/lambda/latest/dg/scaling-behavior.html) in the Tokyo region starts at 1,000 concurrent executions, with 1,000 additional environments every 10 seconds, per function. This per-function scaling (improved from the previous account-level limit) means you can split across multiple functions to multiply your scaling rate. It's worth noting that not all FaaS platforms offer this level of burst scaling; the specific concurrency quotas and scaling rates vary significantly across providers, and this design depends on them. The engineering that makes this scaling rate possible is largely invisible to callers. Werner Vogels' post on [the decade-long work behind Lambda's networking layer](https://www.allthingsdistributed.com/2026/04/the-invisible-engineering-behind-lambdas-network.html) traces how today's cold start and VPC behavior were built up incrementally.

### What the numbers told us

We built a prototype to validate this design before committing to production deployment, specifically to answer the questions that Pattern 2 raised: can this stack handle a step-function traffic pattern? What does cold start actually look like under burst conditions? And what happens when the cache layer fails?

> **Prototype conditions**: Node.js 18.x on arm64, 1024 MB memory, Tokyo region, ~50 KB cached payload per route. 5-second ramp to target concurrency, held for 10 minutes. Simulated 600ms backend API call. These numbers are from a prototype, not a production system, so performance characteristics will vary with different runtimes, memory configurations, and payload sizes.

**The scaling curve was flat.** This was the most important finding. Starting from zero concurrent executions (all cold starts), I expected some degradation knee as concurrency climbed. There wasn't one. From 100 to 980 concurrent executions, average latency held at 628ms with P99 at 650ms. This is the direct consequence of Lambda's isolation model: each execution environment handles exactly one request at a time with dedicated resources, so there's no contention between concurrent requests, unlike a container where multiple requests share the same process, thread pool, and in-process resources. At 980 concurrency, the system sustained 1,555 RPS over 10 minutes (~1.09 million requests, zero errors).

This was the answer to Pattern 2's 0 → N problem from a completely different angle. Pattern 2's compound failure (target distribution skew, initialization costs, health check timing) happened because multiple concurrent requests within each container competed for the same process resources, and the step-function arrival pattern overwhelmed a subset of them before they could warm up. With Lambda's one-request-per-environment model, that compound failure can't occur: each request gets a fully dedicated environment from the start.

**Cold starts were a one-time cost, not a per-request tax.** P99: 1.87 seconds. Average: 1.68 seconds (breakdown: ~350ms runtime init + ~850ms S3 cache fetch + ~600ms request processing). They clustered in the first few seconds, then virtually disappeared for the remaining 10 minutes. The S3 fetch dominates the cold start budget. Moving it into the Lambda init phase (before the handler is invoked) is possible but doesn't reduce the end-to-end cold start duration; the fetch still blocks the first request. Provisioned concurrency would eliminate cold starts entirely by pre-initializing environments, but that reintroduces always-on cost, exactly what this pattern is designed to avoid. For a burst-only layer where cold starts are a bounded one-time cost per environment, the 1.68s average was an acceptable trade-off.

![](https://cdn.hashnode.com/uploads/covers/69d1f25c6792e486f60903fd/8e6161ae-4398-4bba-b508-a4b2af4a46cf.png align="center")

**Implementation choices directly determined cold start performance.** This is where the design trade-off gets interesting:

| Approach | Avg cold start | Delta | Trade-off |
| --- | --- | --- | --- |
| Node.js + @codegenie/serverless-express + Webpack | 1.68s | baseline | Fastest; single bundled JS file |
| Docker + @codegenie/serverless-express | 1.92s | +240ms | Container image extraction overhead |
| Docker + Lambda Web Adapter | 2.19s | +510ms | Minimal code changes; longest cold start |

[Lambda Web Adapter](https://github.com/aws/aws-lambda-web-adapter) wraps an existing HTTP server (Express, Flask, etc.) inside a Lambda execution environment with minimal code changes, but the adapter's HTTP proxy layer adds initialization overhead.

Less code modification correlates with longer cold starts. For a burst-only layer where cold starts are a bounded one-time cost, the ~500ms difference between the fastest and slowest approach is unlikely to matter. Choose based on how much code modification your team can absorb, not on cold start delta alone. And that choice feeds directly into the biggest trade-off of this entire pattern.

**Cache fault tolerance surprised us.** Even at 50% S3 fetch error rate, overall error responses stayed below 0.6%. Once a Lambda environment loads its cache, it serves all subsequent requests from memory. Within ~20 seconds, all active environments had cached data and errors stopped. The per-environment memory model turns a transient infrastructure failure into a bounded, self-healing problem, something I hadn't expected to work this cleanly.

![](https://cdn.hashnode.com/uploads/covers/69d1f25c6792e486f60903fd/f58b2e00-b6a6-4791-90d5-4c50f3920113.png align="center")

**Cost for a 10-minute peak at ~13,000 RPS:** $160–$230 (Lambda + API Gateway). The point isn't the exact dollar amount; it's the cost *shape*: when traffic subsides, cost drops to near zero. For unpredictable peaks that happen a few times a month, the cost difference compared to always-on containers is orders of magnitude.

### The real trade-off: two runtimes

Here's what most "we moved to Lambda" articles skip, and what makes this pattern fundamentally different from a Lambda migration.

Because the baseline stays on containers and the burst layer runs on Lambda, you're maintaining two runtimes. Two deployment pipelines, each with its own build, test, and release process. Two sets of environment variable and secrets configurations. Two application log formats to aggregate and alert on. Two failure modes to triage during incidents, and when something breaks at 3 AM, the first question is "which runtime is this happening in?" before you can even start diagnosing. And a test matrix that doubles with every code change.

This is the real cost of Pattern 3. Not the Lambda invocation charges; those are cheap. It's the ongoing operational overhead of keeping two execution models in sync. The more you optimize the Lambda path (Webpack bundling for faster cold starts, Lambda-specific caching, memory tuning), the further it drifts from the container codebase. Every optimization that improves burst performance increases the maintenance burden.

The decision isn't "Lambda vs. containers" — it's "is the scaling speed worth the operational overhead of maintaining both?" For a use case where 10-second scaling is a hard requirement and the alternative is over-provisioning hundreds of always-on containers, the answer was yes. For a predictable sale event where you have hours of lead time? Probably not. Pattern 2 with proper service-in design would be simpler and cheaper to operate.

One mitigation that addresses multiple problems at once: keep a small percentage of traffic (say, 10%) flowing through the Lambda path at all times. This keeps environments warm, provides continuous validation that the path works, and gives early warning of cache staleness or latency drift. It also eliminates the 0 → N service-in problem entirely: you never start from zero. This is a fundamentally different answer than Pattern 2's mitigations (gradual traffic introduction, pre-warming), which try to smooth the 0 → N transition. Pattern 3's "always trickle" removes the transition altogether.

The cache layer has its own trade-off: data freshness. Caching backend responses in S3 means the burst path serves slightly stale data during peaks. Cache TTL design becomes critical: too short and you lose the backend isolation benefit; too long and users see outdated content. For read-heavy peak scenarios this is usually acceptable, but it needs to be an explicit design decision, not an afterthought.

**The lesson: for unpredictable peaks, adding a FaaS burst layer on top of a stable baseline is a viable architecture, not as a migration, but as a composition of two scaling models.** The scaling speed is real. The operational cost is also real. Whether the trade-off is worth it depends on whether your peak is the kind that gives you seconds or hours.

## Closing

Peak traffic design doesn't start from the service catalog. It starts from three questions: *What's the scaling bottleneck? Is the peak predictable? What happens when the burst environment breaks?*

The three patterns are different answers to the same questions. Pattern 1 taught me that including the data layer changes the economics. Pattern 2 taught me that "enough capacity" isn't the same as "ready to serve," and that load tests can pass while hiding the exact failure mode that production will trigger. Pattern 3 taught me that you don't have to choose between scaling models: you can compose them, if you're willing to pay the operational cost.

But the lesson I keep coming back to is from Pattern 2: the question isn't whether your system can *reach* the target load. It's *how* it gets there. The ramp-up profile, the shape of the traffic curve in the first seconds, is where the interesting failures hide. And it's the one thing most load tests don't test.

These patterns share a common thread with what I wrote about in my [previous post on Architecture Dojo 2025](https://blog.simukappu.com/4-lessons-from-dissecting-production-systems-at-scale-architecture-dojo-2025): constraints drive design, and the problem structure matters more than the service catalog. The constraint shifted from "we can't afford always-on replicas" to "we can't scale containers in 10 seconds," and each produced a fundamentally different design.

The answers change. The questions don't.

* * *

If you've hit the 0 → N problem in production, or found a way to compose scaling models that I haven't covered here, I'd like to hear about it.