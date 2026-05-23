---
title: "Resilience Beyond Multi-AZ: Bulkheads and Shock Absorbers — Architecture Dojo 2024"
seoTitle: "2 Patterns for Resilience Beyond Multi-AZ"
seoDescription: "Multi-AZ is the baseline. Two production incidents and two resilience patterns: bulkheads for blast radius, shock absorbers for dependency failures."
datePublished: 2026-05-05T14:02:18.832Z
cuid: cmosp6mob00bx2flrfhnj04up
slug: resilience-beyond-multi-az-bulkheads-and-shock-absorbers-architecture-dojo-2024
ogImage: https://cdn.hashnode.com/uploads/og-images/69d1f25c6792e486f60903fd/732e60fb-f99a-4178-b156-324ff142ef48.jpg
tags: aws, software-architecture, system-design, distributed-systems, resilience

---

Some incidents look minor on paper. A small single-digit percentage of instances affected, in a single AZ. And yet the user-visible outcome is that more than half of the service's transactions stop working, and the cause isn't clear until after the problem has already resolved itself.

I've watched this shape unfold more than once over the last few years. A small blast radius at the infrastructure layer explodes into a large blast radius at the application layer, because the architecture had a quiet assumption that failed. Redundancy held exactly as designed. The failure just spread through a channel the redundancy didn't cover.

Architecture Dojo 2024 at AWS Summit Japan was built around this kind of failure. Both design challenges that year asked the same underlying question from two different angles: *once you accept that failures will happen below the region level — in a single AZ, in a dependency, in a component's gray failure — how do you stop them from taking down everything?* I was on stage as the panelist for the second challenge. ([Session recording](https://youtu.be/eoBlprMYx_E), in Japanese.)

This post isn't a replay of the session. It starts with two production incident patterns I've lived through, then turns to the two Dojo patterns that, in hindsight, organize them both. Both cases are composites, drawn from incidents of the same shape I've seen recur across different systems over the years. Where the technical specifics are useful, I've kept them concrete: particular metrics, fault injection actions, reproduction techniques. The value of this kind of post lives in those details. The composite framing is about the shape of the incident, not about scrubbing public-knowledge technical content that happens to appear in it. The views here are my own.

![](https://cdn.hashnode.com/uploads/covers/69d1f25c6792e486f60903fd/f556f3b3-7691-44db-89ca-ff63715b2a48.jpg align="center")

> **TL;DR**
> 
> 1.  **Gray failures turn "infrastructure is slightly broken" into "application is fully broken."** The mismatch between health definitions at different layers is what makes a small blast radius explode.
>     
> 2.  **Asymmetric protection is the most repeatable failure mode.** Guarding the write path while leaving the read path exposed is how a well-engineered service goes down from a dependency it thought it had handled.
>     
> 3.  **Bulkheads bound blast radius statically. Shock absorbers contain failures dynamically.** A bulkhead only works if the layers on both sides agree on when it's breached; a shock absorber only works if it covers every path that touches the dependency.
>     

With that framing, let me turn to two concrete scenarios. Both are shapes I've seen more than once, and each maps onto one of the two Dojo patterns I'll return to later.

## Case 1: A partial failure that became a region-wide outage

### The scene

An infrastructure-level event took out a small single-digit percentage of compute instances in one AZ of a large-scale distributed system in production. Well-designed redundancy should have absorbed this almost immediately: a few affected instances, automatic failover to healthy capacity, recovery measured in seconds. That's not what happened. The application-side impact was severe for tens of minutes. More than half of the user-facing transactions failed. Operators couldn't identify what was blocking the application from behind the infrastructure event; by the time the root cause was narrowed down, the infrastructure had already recovered.

That asymmetry, where a single-digit percentage of affected infrastructure translated into a majority-transaction outage, and where the root cause stayed hidden until the event had already resolved, gave me a lot to think about afterward. A small blast radius at one layer shouldn't propagate into a large blast radius at another.

### The failure, layer by layer

The application depended on a stateful middleware layer — think of a message broker, or any similar component that sits between services and can hold up upstream work when it stalls. The middleware ran on its own compute with its own attached block storage.

Here's what broke, layer by layer:

*   **The compute layer of the middleware stayed up.** Its processes responded. Its health checks passed. From anything probing at the surface, it looked fine.
    
*   **The block storage backing a subset of the middleware's nodes became unresponsive.** Not offline. Reads and writes arrived at the volume and then didn't complete in any reasonable time. The I/O was accepted and then hung.
    
*   **The middleware's own failover didn't trigger.** Its failure detection was tuned for node loss, not for "this node is alive but its storage is pathologically slow." The metrics that would have caught it weren't wired into the decision to fail over.
    
*   **The application had no downstream visibility into the stalled middleware.** Whatever retry and timeout behavior the client was configured for, it couldn't cleanly distinguish "the middleware is slow" from "the middleware is up but failing silently." The longer it hung, the more upstream work backed up behind it.
    

None of these is a bug in isolation. Compute-layer health checks are how most things work. Failover logic tuned for node loss is industry standard. Client-side retry and timeout policies, however configured, can only work with the signals they receive. The layers weren't negligent. They just had no way, in combination, to recognize in real time that this specific shape of storage failure was happening. The machinery for detecting and reacting to failures existed everywhere, and none of it was calibrated for a storage device that was simultaneously attached, responsive to control-plane queries, and unable to complete I/O on the data plane.

### The response, in two threads

The response split in two. The application-side work was to put a buffer between the request path and the middleware so that a stalled middleware couldn't hold up user-visible transactions; I'll come back to this when I turn to the Dojo patterns. The system already had a reconciliation mechanism for the data the middleware was carrying, so recovering state after a failed asynchronous publish was a matter of letting that existing mechanism do its job, not building something new. Where the interesting engineering lived was on the infrastructure side: detecting and reproducing the specific failure mode.

Going back through the telemetry from the incident window, only the queue-length metrics on the block storage volumes (`VolumeQueueLength` and related) indicated anything abnormal. The metrics one would instinctively reach for first, such as stalled I/O checks and idle time, showed nothing out of the ordinary. The device wasn't idle; it was accepting work. It wasn't flagged as stalled by the platform; it was receiving requests. It just wasn't finishing them in any meaningful time. Queue depth was the only place where "requests going in, responses not coming out" was visible.

Adding that metric to the baseline alerting set was the easy half. The harder half was showing that a new alert actually fires when it matters, which meant reproducing the failure in staging. The obvious tool was AWS Fault Injection Service (FIS), and specifically `aws:ebs:pause-volume-io`. But that action pauses I/O entirely, sending requests into a void, which doesn't reproduce the queue-length anomaly a team in this situation would need to exercise. The production failure was "almost no I/O, with requests still being accepted," not "no I/O at all."

What works, after some trial and error, is using Linux cgroup v2's `io.max` controller to impose an extremely low IOPS ceiling on the block device (on the order of a handful of read/write IOPS per second). The device keeps responding and keeps accepting requests; they just drain extremely slowly, which is exactly how queues back up in the real failure. Running this in staging moved the queue-length metric, didn't trigger the middleware's own failover, and reproduced the upstream symptoms with enough fidelity to be useful. From that point on, every further change to monitoring or client behavior could be verified against a concrete failure, not an educated guess.

### The honest lesson

It would be easy to read this as a story about a middleware layer that wasn't doing its job. I don't think that's fair, and I don't think it's useful. No dependency layer is fully resistant to gray failures. Not the middleware I've been describing, and, if we're honest, not the managed cloud services underneath it either. Managed services are dramatically better at detection and recovery than most self-managed alternatives, which is a real difference worth naming. It still doesn't eliminate gray failures entirely. The state space of a large distributed system is effectively infinite, and every layer, managed or not, will eventually find a partial failure mode whose detection wasn't designed for.

That reframes the question. The resilience problem doesn't stop at whether your dependency is well-designed. It extends into what your application does when a well-designed dependency still has a failure mode neither of you can detect. That's a question the application architecture has to answer on its own, because the dependency's vendor isn't going to answer it for you. Even if the layer below is doing excellent work on its own terms, you're still the only one who can place a buffer between their layer and yours.

In the incident I described, that answer came down to three things that actually worked:

*   **Decouple the synchronous path from the dependency.** Moving the publish off the request-handling thread meant a stalled dependency couldn't stall a user-facing transaction. This is the single highest-leverage change you can make when a dependency's gray failure has taken you down.
    
*   **Add dependencies across independent failure domains.** For the read side, a secondary path that doesn't share the same underlying infrastructure (a different region, a cache backed by different storage, a fallback to degraded but working behavior) turns a single failure into a manageable degradation. This is the harder one to invest in because it costs real money and engineering time, and the benefit only appears during incidents.
    
*   **Keep the chaos catalog current.** The specific failure mode I described wasn't in any fault injection toolkit available off the shelf. Without a purpose-built reproduction, any fix is a guess. The catalog isn't something you finish; it's something you keep updating as you meet new failure shapes in production.
    

Every one of these is a version of the same design move: placing shock absorbers between the application and the thing that might fail in a way you can't see coming. That's what Architecture Dojo 2024's second challenge was asking, and I'll come back to it when I turn to the Dojo patterns below.

## Case 2: The read path had none of the protections the write path did

Case 2 is, in a sense, the mirror image of Case 1. The first was about a dependency whose failure mode none of the layers could detect. The second is about a dependency whose failure mode was understood perfectly well on one side of the application, and completely unprotected on the other.

### The setup

A high-traffic web application depended on an external lookup service used by many of its requests. The architecture had been through several design reviews. The write path to that external service was carefully protected: a circuit breaker wrapped the call, writes went through an asynchronous queue, retries had exponential backoff. If you asked the team "what happens when this dependency fails?", they'd walk you through the write path and show you every defense in depth.

The read path was synchronous. In-process. Pulling from a shared thread pool sized for normal conditions. With no timeout on the outbound HTTP call.

This wasn't an oversight from forgetfulness. The read path looked simple and the write path looked critical. Reads were small, fast, and went to a service the team had been using for years. The perceived risk was low enough that the circuit breaker and timeout never made it to the top of the backlog. The write path, on the other hand, was the one that could miss an event or corrupt state, and it got all the design attention.

### How it cascaded

The external service started responding slowly. Not down, just slow. Reads that normally completed in milliseconds began taking seconds, then tens of seconds. This was a gradual degradation, not a step change. For the first few minutes, the latency increase was almost invisible in the aggregate metrics because only a subset of requests was affected.

Then the queue started to build.

Threads that had been picking up read requests from the shared pool began lingering on in-process socket waits. Because there was no client-side timeout, each waiting thread stayed in the pool, holding its slot. The next read came in, took a thread, and joined the wait. Then the next. And the next. The thread pool was sized for normal conditions, and normal conditions assumed reads completed in milliseconds. Under degraded conditions, threads that would normally have been released within a frame were holding for tens of seconds.

The web server's upstream process pool was exhausted shortly after. New requests, including requests that had nothing to do with the affected dependency, couldn't get a worker. The service went dark from the user's perspective, not because the dependency was unreachable, but because the process pool was full of threads waiting on sockets that were never going to complete in time.

### The small fix, exposing a big assumption

The fix, once the team traced it, was a small, localized client-side change: an HTTP client timeout on the read, and a circuit breaker wrapping the call. It shipped as soon as the root cause was confirmed.

The write path never broke. The write path worked exactly as designed throughout the incident. The write path's circuit breaker opened, its backoff retries kicked in, its async queue absorbed the pressure. All the investment in protecting the write path paid off, exactly as intended.

But it didn't matter. The read path was the failure mode that took the service down, and the read path had none of those protections.

This is the failure mode I want to name explicitly: **asymmetric protection**. The write path was protected, thoroughly. The problem was that critical and critical-path aren't the same thing. Every path that touches a flaky dependency is a critical path for that dependency's failure modes, regardless of whether the business considers that path critical.

### The less obvious lesson

The obvious lesson is "protect all paths." The less obvious lesson is how protection decisions get made, and why they skew asymmetric.

When a team designs a shock absorber around a dependency, they're usually reacting to a specific worry. Writes feel critical because writes have clear failure semantics: a write either succeeded or it didn't, and the business consequences of a lost write are usually easy to articulate. Reads feel more forgiving because a failed read can be retried, or cached, or degraded gracefully at the UI layer. The protection decisions follow the shape of the worry, not the shape of the dependency.

That's the cognitive bias. A flaky dependency doesn't care which of its paths you considered critical when you designed the protections. It fails on whichever path happens to be exposed. If you've carefully guarded the write path and left the read path naked, the dependency will find the read path, because that's the one that's still sharing resources with the rest of your service under degraded conditions.

The generalization I've taken from this: **resilience mechanisms have to cover every path that touches the dependency, not just the path you designed around**. If one direction is asynchronous and protected and the other is synchronous and unprotected, the two paths still share the same dependency, and the unprotected one will fail first. Architecture Dojo 2024's second challenge offers a systematic answer to this asymmetry, which is where I turn next.

## Two ways to control the impact of failure

With both incidents on the table, I want to go back to Architecture Dojo 2024. The session's framing is one clear way to organize what to do about failures of these shapes.

### Two axes of impact control

The session's host, Eiichiro Uchiumi, made an observation at the end of Architecture Dojo 2024 that I've been repeating ever since: the basic approach to resilience in the cloud is to control the *impact* of failures, not their *causes*. The state space of a cloud-based system is effectively infinite, so eliminating failure modes is not a game you can win. Bounding what each failure does, though, is a game you can win, and you have two fundamentally different tools for playing it.

| Aspect | Bulkheads (static) | Shock absorbers (dynamic) |
| --- | --- | --- |
| Purpose | Limit the scope of failure | Absorb failures as they propagate |
| Decided at | Design time | Runtime |
| Typical examples | AZ independence, functional isolation, cell-based architecture | Rate limiting, circuit breakers, queues, caches |
| What breaks them | Shared resources you forgot about | Paths you forgot to protect |

Bulkheads are structural. The term comes from shipbuilding: the internal walls that divide a ship's hull into watertight compartments, so a breach in one doesn't flood the whole vessel.

Shock absorbers are behavioral. The term is less established in software, borrowed here from the car suspension that damps road impact before it reaches the passenger. It's a useful framing because it groups primitives that aren't usually grouped together: rate limiting, circuit breakers, retries, queues, caches, asynchronous processing all share the same job of damping a dependency's misbehavior before it reaches the caller.

Architecture Dojo 2024's two challenges were, in effect, one problem per axis. Challenge 1 asked for a bulkhead strategy against gray failures inside a single AZ. Challenge 2 asked for a shock absorber strategy against an unreliable third-party dependency. Case 1 is a problem a bulkhead strategy would have contained; Case 2 is a problem a shock absorber strategy would have contained.

### Challenge 1: The bulkhead response to gray failure

Challenge 1's scenario was a credit card company running a payment application on AWS with the expected mission-critical baseline: Route 53, ALB across three AZs, EKS, Aurora with a Global Database replica. The question was specifically about gray failures inside one AZ, the same shape of failure as Case 1.

The response that the session ultimately built on was presented by my colleague Shunsuke Mabuchi, and centered on **AZ independence (AZI)**: the idea that each AZ should behave as an isolated silo with zero cross-AZ dependencies on the data path. AWS documents the pattern extensively in the [Advanced Multi-AZ Resilience Patterns whitepaper](https://docs.aws.amazon.com/whitepapers/latest/advanced-multi-az-resilience-patterns/advanced-multi-az-resilience-patterns.html). The design's core moves, in four pieces:

*   **Disable cross-zone load balancing.** By default, ALB spreads traffic from every AZ to every backend. Turning this off means traffic entering the AZ-2 ALB stays in AZ-2.
    
*   **Partition everything along AZ lines.** Separate Kubernetes namespaces, ConfigMaps, and Fargate profiles per AZ. Per-AZ Aurora custom endpoints for reads, so an AZ-2 pod talks to an AZ-2 reader. Writes still cross AZ boundaries because Aurora has one writer, but every other call stays local.
    
*   **Deep health checks on the write path.** For the one path you can't make AZ-local, make the health check exercise the actual dependency. Not "is the front end responding," but "can the back end reach the Aurora writer within a sane latency envelope." If the write path is degraded, the ALB drains that AZ from its target group.
    
*   **Composite alarm plus zonal shift.** A composite CloudWatch alarm distinguishes "AZ-1 is sick" from "the region is sick" from "the writer is sick" using per-AZ metrics combined with NOT conditions for the other cases. When the alarm fires, a Route 53 ARC zonal shift moves traffic out of AZ-1 for a bounded window, giving operators time to investigate.
    

Each of these has a cost. Disabling cross-zone load balancing tightens capacity planning: each AZ now needs headroom for its own traffic plus the scenario where another AZ is drained. In a 3-AZ configuration, surviving the loss of one AZ means each AZ has to carry 50% of the normal-state traffic during failover, so you're provisioning roughly 1.5x the pre-AZI capacity across the fleet. Per-AZ database endpoints need extra replicas to keep load balanced when the writer and reader are colocated. Deep health checks raise the risk of false positives that drain a healthy AZ. You're paying with capacity and complexity to buy isolation.

The underlying mindset is what I keep coming back to: **every cross-AZ link is a potential failure propagation path, so you name them explicitly, and for each one you either eliminate it or accept it with eyes open**. Apply that lens to Case 1: the middleware nodes with failing storage were clustered in one AZ, and the cross-AZ link from the application to that middleware was the actual propagation path. Its health definition didn't match the application's. The middleware side saw "responsive compute"; the application side saw "stalled requests." The implicit AZ boundary never triggered. Under AZI, the bulkhead would have absorbed it: unaffected AZs would have kept serving insulated from the failing middleware, and a composite alarm could have drained the affected AZ within minutes. The bulkhead wasn't absent in a physical sense. It was absent in a *semantic* sense, and that's the failure mode AZI is built to close.

### Challenge 2: The shock absorber response to unreliable dependencies

Challenge 2 was the one I was on stage for. The setup was an e-commerce application on AWS (CloudFront, S3, ALB, ECS, DynamoDB with DAX) that depended on a third-party service for one specific feature. The third party was unreliable in the worst way: not down, just sometimes slow, sometimes returning errors, getting worse under load. Replacing it wasn't an option.

When your dependency can't be fixed and can't be removed, the only lever you have is how your system behaves when the dependency misbehaves. That's what shock absorbers are for, and that's the shape of the problem Case 2 describes.

Before the design, it helps to name what a buffer between an application and a flaky dependency is actually for. There are two distinct jobs:

*   **Reduce load on the dependency when it's struggling.** More requests make the situation worse. Primitives for this job: rate limiting, circuit breakers, caches.
    
*   **Contain the blast radius of the dependency's failures.** Don't let its failure take down the caller. Primitives for this job: backoff retries, circuit breakers, asynchronous processing.
    

Circuit breakers show up in both columns because they do both at once: when open, the caller fails fast (containment) and the dependency gets a break from incoming requests (load reduction). Everything else specializes.

### The design: a proxy service with four access modes

I proposed wrapping the third-party dependency in a proxy service. The application talks to the proxy instead of the third party directly, and the proxy encapsulates the resilience logic. Application code never calls the third party, never handles retries, never implements circuit breakers inline. It calls the proxy, and the proxy decides what to do.

Inside, the proxy exposes four access modes that the application chooses per request:

1.  **Synchronous write.** Go to the dependency now, retry on transient failure, fail fast once the circuit breaker opens. Latency is bounded; errors bubble up.
    
2.  **Asynchronous write.** Enqueue the request, return a request ID immediately, process in the background, let the caller poll for the result. The caller never waits on the dependency.
    
3.  **Direct read.** Go to the dependency for fresh data, populate the cache on the way back. Same latency profile as a synchronous write, with the side effect of warming the cache.
    
4.  **Cached read.** Serve from the cache. On hit, return immediately. On miss, return an error; the caller can fall back to a direct read if it wants fresh data badly enough.
    

![](https://cdn.hashnode.com/uploads/covers/69d1f25c6792e486f60903fd/32ee1e37-edab-45b4-bc30-73d7cf631b91.png align="center")

There are a few design choices I want to explain, because they're what held up to the session's discussion rather than collapsing into the obvious "put a retry loop around the call" design.

**The application picks the mode per request, not the proxy.** The proxy doesn't know the business context. It doesn't know whether a given call is on the checkout critical path (where failing fast matters) or a background enrichment (where retrying later is fine) or a product recommendation (where stale is better than missing). The application knows. The proxy gives it the vocabulary to say so.

**Four modes because sync-vs-async and write-vs-read are two different axes.** This is the part that Case 2 informs most directly. If you'd asked me to design this proxy without having lived through the read-path incident, I might have built three modes (sync, async, cached) and treated the read path as a simpler case of the write path. The incident taught me that the read path is its own thing, with its own failure modes, its own latency budget, and its own questions about staleness versus errors. A cached read that returns an error on miss is a different behavioral contract from a direct read that might fail after retrying. Making them separate modes lets the application express which contract it wants.

**The async mode uses polling rather than callbacks.** When the consumer has finished processing a request in the background, the application finds out by polling for the state by request ID, not by the proxy calling back into the application. The main reason is practical: polling minimizes the changes the application team has to make to adopt the pattern. They only need to learn the proxy's request/response contract. They don't have to expose a new callback endpoint or handle inbound calls from the proxy. For a team incrementally retrofitting resilience onto an existing service, that's often the difference between "we can ship this next sprint" and "this requires an application-wide refactor."

There's a second reason that matters more the longer you operate the pattern. Polling pushes the consistency model into a shape the application already understands. The caller reads the current state of its own request by ID, which is an idempotent operation, and can reconcile its view of the world against the proxy's authoritative state at its own cadence. That's the same "design your reconciliation" move I wrote about in the [Architecture Dojo 2025 post](https://blog.simukappu.com/4-lessons-from-dissecting-production-systems-at-scale-architecture-dojo-2025): rather than engineering exactly-once semantics into the callback path, accept that the two sides can drift briefly and give the caller a clean way to resync.

The four modes share a single core engine. The rate limiter and circuit breaker used by synchronous write are the same ones used by the async consumer and by direct read on a cache miss. The proxy is one buffer with four entry points, not four separate systems. The serverless composition is clean: API Gateway at the front for entry-level rate limiting, Step Functions Express Workflows for the sync retry loop and circuit state machine, SQS for the async queue, Lambda for the consumer, and DynamoDB for circuit state, request state, and cache.

### How each mode behaves when the dependency fails

The table is the reason the four-mode design is worth having. Each mode converts a dependency failure into a different kind of problem that the caller can reason about:

| Failure mode | Synchronous write | Asynchronous write | Direct read | Cached read |
| --- | --- | --- | --- | --- |
| Transient degradation (slow, elevated errors) | Retries may succeed; latency increases; circuit may or may not open | Returns 200 to caller immediately; background retry usually succeeds | Retries may succeed; latency increases; circuit may or may not open | Hit: serves from cache. Miss: error |
| Persistent failure (dependency fully down) | Circuit opens; fails fast with 5xx | Returns 200 immediately. Background processing either gives up after retries and surfaces an error on poll, or keeps waiting for recovery (configurable) | Circuit opens; fails fast with 5xx | Hit: serves from cache. Miss: error |

The asynchronous write turns dependency availability into a latency problem rather than an error problem on the caller's side. The caller's write succeeds; the actual call to the third party happens later, under controlled conditions. That's usually what the business actually wants: the order was placed, the notification will go out when it can.

The cached read turns dependency availability into a freshness problem. You trade "the data might be slightly stale" for "the feature stays up even when the dependency is down." For reference data, catalog information, or anything where yesterday's value is good enough during an incident, this is the right trade. For data where staleness is dangerous, it isn't.

### When the proxy itself fails

The session's host raised this question during the Q&A: your proxy is now on the critical path of every dependency call. You've traded a direct coupling to a flaky third party for an indirect coupling to a buffer that you now have to operate. What happens if the proxy itself has a problem? I had two answers, and they address different slices of the problem.

**The first answer is to make the proxy cheaply relocatable.** The serverless implementation is stateless at the compute layer (Lambda, API Gateway, Step Functions) with state delegated to managed services (DynamoDB, SQS). Because everything is pay-as-you-go, a standby copy in another region costs almost nothing when idle: no warm capacity, no steady-state bill, just the state backend sitting quietly. If the primary region's proxy is impaired, the application switches its endpoint to the secondary, and the standby absorbs traffic at AWS's multi-region ceiling of availability. The host's counterpoint was fair: multi-region handles infrastructure-level failures of the proxy, but a logic bug in the proxy code, or a misconfiguration in one of its AWS services, will replicate to every region you deploy to.

**The second answer is to remove the proxy as an independent failure domain.** Instead of running the proxy as a separate service, integrate its logic directly into the application, either as an in-process library or, if you want looser coupling, as a sidecar alongside each application instance. Either way, the proxy shares the application's lifecycle: if the application is up, the proxy is up; if the proxy is down, the affected application instance is down with it. There's no separate "proxy outage" to worry about. The tradeoff is giving up per-request elasticity and coupling deployment cycles; shared state like circuit breaker state still needs to live outside the process.

Serverless multi-region and embedded deployment target different failure modes, so neither fully replaces the other. Which one fits depends on what kind of proxy failure you're most worried about.

## Closing

Architecture Dojo 2024 ended with three sentences from Uchiumi-san that I'll paraphrase here, because they compress the whole session into one handhold. Multi-AZ is the baseline; plenty of customers go further and run multi-region. But distributing infrastructure across locations, by itself, doesn't eliminate the failures that application architecture is uniquely positioned to absorb. Controlling the *impact* of failures — not their causes — is what application architecture is for.

Incidents of the shape I described in Case 1 tend to happen to teams that have been working on resilience improvements for years. The improvements are understood. The patterns in this post aren't new to them. What's often missing is follow-through against a backlog that keeps losing priority to cost optimization and feature velocity, until an incident arrives that shifts the priorities by itself. Architecture decisions are also decisions about what an organization is willing to invest in before it has to.

The session closed with a metaphor Uchiumi-san used that still works for me. Think of the counters in a bank or a government office. Different counters for different services. All the counters could technically handle any service; combining them would be more efficient in terms of staff utilization. Why don't they? Because separating counters keeps a customer with urgent business from being blocked behind less urgent ones. That's a bulkhead. And within each counter, you might take a ticket or book a time slot — that's a shock absorber, smoothing the arrival pattern so the counter doesn't get overwhelmed. The physical world has been refining these patterns for a long time. Sometimes the best way to see your own architecture is to look at the one you walk through every day. Since that session, every architecture review I walk into now has me asking two questions earlier than I used to: where are the counters, and what's between them?

If you're carrying the scars of a gray failure that should have stayed in one AZ, or a dependency outage that took down more than it should have, I'd genuinely like to hear about it. The patterns that end up in posts like this one come from those incidents. They don't come from Dojo sessions alone.

Previous posts in this series:

*   [4 Lessons from Dissecting Production Systems at Scale — Architecture Dojo 2025](https://blog.simukappu.com/4-lessons-from-dissecting-production-systems-at-scale-architecture-dojo-2025)
    

Past Architecture Dojo sessions (Japanese): [2025](https://youtu.be/L-NcmkkDJMI) | [2024](https://youtu.be/eoBlprMYx_E) | [2023](https://youtu.be/s9YqEELWutA) | [2022](https://youtu.be/C7trZIt5H3w)