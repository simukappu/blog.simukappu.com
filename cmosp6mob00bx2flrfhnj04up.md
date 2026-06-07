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

Architecture Dojo 2024 at AWS Summit Japan was built around this kind of failure. Both design challenges that year asked the same question from two angles: once you accept that failures will happen below the region level, in a single AZ, in a dependency, in a component's gray failure, how do you stop them from taking down everything? I was on stage as the panelist for the second challenge. ([Session recording](https://youtu.be/eoBlprMYx_E), in Japanese.)

This post isn't a replay of the session. It starts with two production incidents I've lived through, then turns to the two Dojo patterns that organize them. Both cases are composites of incidents of the same shape I've seen recur across different systems; where the technical specifics are useful I've kept them concrete, because the value lives in those details. The views here are my own.

![](https://cdn.hashnode.com/uploads/covers/69d1f25c6792e486f60903fd/f556f3b3-7691-44db-89ca-ff63715b2a48.jpg align="center")

> **TL;DR**
> 
> 1.  **Gray failures turn "infrastructure is slightly broken" into "application is fully broken."** The mismatch between health definitions at different layers is what makes a small blast radius explode.
>     
> 2.  **Asymmetric protection is the most repeatable failure mode.** Guarding the write path while leaving the read path exposed is how a well-engineered service goes down from a dependency it thought it had handled.
>     
> 3.  **Bulkheads bound blast radius statically. Shock absorbers contain failures dynamically.** A bulkhead only works if the layers on both sides agree on when it's breached; a shock absorber only works if it covers every path that touches the dependency.
>     

## Case 1: A partial failure that became a region-wide outage

An infrastructure-level event took out a small single-digit percentage of compute instances in one AZ of a large-scale distributed system in production. Well-designed redundancy should have absorbed it in seconds. Instead the application-side impact was severe for tens of minutes, more than half of user-facing transactions failed, and operators couldn't pin down what was blocking the application until the infrastructure had already recovered. A single-digit percentage of affected infrastructure had become a majority-transaction outage. A small blast radius at one layer shouldn't propagate into a large one at another.

The application depended on a stateful middleware layer (think of a message broker, or anything that sits between services and can hold up upstream work when it stalls), running on its own compute with its own attached block storage. Here is what broke, layer by layer:

*   **The middleware's compute stayed up.** Its processes responded, its health checks passed. From the surface it looked fine.
    
*   **The block storage on a subset of its nodes became unresponsive.** Not offline: reads and writes arrived at the volume and then hung, accepted but never completing in any reasonable time.
    
*   **The middleware's own failover didn't trigger.** Its failure detection was tuned for node loss, not for "this node is alive but its storage is pathologically slow."
    
*   **The application had no visibility into the stall.** Its retry and timeout behavior couldn't distinguish "the middleware is slow" from "the middleware is up but failing silently," so the longer it hung, the more upstream work backed up behind it.
    

None of these is a bug in isolation. Compute-layer health checks, failover tuned for node loss, client-side timeouts: each is standard practice, and none was calibrated for a storage device that was simultaneously attached, responsive to control-plane queries, and unable to complete I/O on the data plane. The machinery for reacting to failures existed everywhere; none of it was wired to recognize this shape in real time.

The response split in two. On the application side, the fix was to put a buffer between the request path and the middleware so a stall couldn't hold up user-visible transactions (more on that with the Dojo patterns); an existing reconciliation mechanism already recovered state after a failed asynchronous publish, so nothing new was needed there. The interesting engineering was on the infrastructure side: detecting and reproducing the failure. Going back through the telemetry, only the queue-length metrics on the block storage volumes (`VolumeQueueLength` and related) showed anything abnormal. The metrics you'd reach for first, stalled-I/O checks and idle time, showed nothing: the device wasn't idle and wasn't flagged as stalled, it just wasn't finishing work. Queue depth was the only place "requests going in, responses not coming out" was visible.

Adding that metric to the alerting set was the easy half. The harder half was proving the alert fires when it matters, which meant reproducing the failure in staging. The obvious tool, AWS Fault Injection Service (FIS) with `aws:ebs:pause-volume-io`, pauses I/O entirely and sends requests into a void, which doesn't reproduce the queue-length anomaly: the production failure was "almost no I/O, with requests still accepted," not "no I/O at all." What works, after some trial and error, is Linux cgroup v2's `io.max` controller imposing an extremely low IOPS ceiling on the device, on the order of a handful of read/write IOPS per second. It keeps responding and accepting requests that then drain extremely slowly, exactly how queues back up in the real failure. In staging it moved the queue-length metric, didn't trip the middleware's failover, and reproduced the upstream symptoms with enough fidelity that every later change could be verified against a concrete failure rather than a guess.

It would be easy to read this as a story about a middleware layer that wasn't doing its job. That's neither fair nor useful. No dependency layer is fully resistant to gray failures, not this middleware and, honestly, not the managed cloud services underneath it either. Managed services are far better at detection and recovery than most self-managed alternatives, but they don't eliminate gray failures: the state space of a large distributed system is effectively infinite, and every layer eventually meets a partial failure mode its detection wasn't designed for. So the resilience problem doesn't stop at whether your dependency is well-designed. It extends to what your application does when a well-designed dependency fails in a way neither of you can detect, because the vendor isn't going to answer that for you. You're the only one who can place a buffer between their layer and yours. In this incident, three things actually worked:

*   **Decouple the synchronous path from the dependency.** Moving the publish off the request-handling thread meant a stalled dependency couldn't stall a user-facing transaction. This is the single highest-leverage change when a gray failure has taken you down.
    
*   **Add dependencies across independent failure domains.** A secondary read path that doesn't share the same infrastructure (a different region, a cache on different storage, a degraded-but-working fallback) turns a single failure into a manageable degradation. This one is hard to justify because it costs real money and the benefit only shows up during incidents.
    
*   **Keep the chaos catalog current.** This failure mode wasn't in any off-the-shelf fault-injection toolkit, and without a purpose-built reproduction any fix is a guess. The catalog is never finished; you keep adding to it as you meet new shapes in production.
    

Each is a version of the same move: placing shock absorbers between the application and the thing that might fail in a way you can't see coming. That's what the Dojo's second challenge was asking.

## Case 2: The read path had none of the protections the write path did

Case 2 is the mirror image. Case 1 was a dependency whose failure mode no layer detected in real time; this is a dependency whose failure mode was understood perfectly on one side of the application and left completely unprotected on the other.

A high-traffic web application depended on an external lookup service used by many of its requests. The architecture had been through several design reviews, and the write path was carefully protected: a circuit breaker around the call, an asynchronous queue, exponential backoff on retries. Ask the team "what happens when this dependency fails?" and they'd walk you through the write path's defense in depth. The read path was synchronous, in-process, pulling from a shared thread pool sized for normal conditions, with no timeout on the outbound HTTP call. This wasn't forgetfulness. Reads looked simple and went to a service the team had used for years; the perceived risk never made the circuit breaker and timeout worth prioritizing, while the write path, the one that could miss an event or corrupt state, got all the design attention.

Then the external service started responding slowly. Not down, just slow, reads creeping from milliseconds to seconds to tens of seconds. For the first few minutes the latency was almost invisible in aggregate metrics because only a subset of requests was affected. Then the queue started to build. Each read thread, with no client-side timeout, lingered on its socket wait and held its slot in the pool. The next read took a thread and joined the wait. Then the next, and the next. The pool was sized for reads that complete in milliseconds; under degradation, threads that should have released within a frame were holding for tens of seconds. The web server's upstream process pool was exhausted soon after, and new requests, including ones with nothing to do with the affected dependency, couldn't get a worker. The service went dark while the dependency was still reachable; the process pool was full of threads waiting on sockets that would never complete in time.

The fix, once traced, was small and local: an HTTP client timeout on the read and a circuit breaker around the call. The write path never broke; it worked exactly as designed throughout, its circuit breaker opening, its backoff retries firing, its queue absorbing the pressure. All that investment paid off, and it didn't matter, because the read path took the service down and the read path had none of those protections.

This is the failure mode worth naming: **asymmetric protection**. Every path that touches a flaky dependency is a critical path for that dependency's failure modes, whatever the business considers critical. The way protection decisions get made skews asymmetric for a reason. Writes feel critical because they have clear failure semantics, a write either succeeded or it didn't, and the cost of a lost write is easy to articulate; reads feel forgiving because a failed read can be retried, cached, or degraded at the UI. So protection follows the shape of the team's worry rather than the shape of the dependency, and a flaky dependency ignores that bias: it fails on whichever path is exposed, and the unprotected read path is the one still sharing resources with the rest of your service under load. The generalization I've kept: **resilience mechanisms have to cover every path that touches the dependency, not just the one you designed around.** The Dojo's second challenge offers a systematic answer to exactly this asymmetry.

## Two ways to control the impact of failure

With both incidents on the table, the Dojo's framing is one clean way to organize what to do about them. The session's host, Eiichiro Uchiumi, made an observation I've repeated ever since: in the cloud you control the *impact* of failures, not their *causes*. Since you can't eliminate every failure mode, bounding what each one does is the game worth playing, and you have two fundamentally different tools for it.

| Aspect | Bulkheads (static) | Shock absorbers (dynamic) |
| --- | --- | --- |
| Purpose | Limit the scope of failure | Absorb failures as they propagate |
| Decided at | Design time | Runtime |
| Typical examples | AZ independence, functional isolation, cell-based architecture | Rate limiting, circuit breakers, queues, caches |
| What breaks them | Shared resources you forgot about | Paths you forgot to protect |

Bulkheads are structural, from shipbuilding: the internal walls that divide a hull into watertight compartments so a breach in one doesn't flood the vessel. Shock absorbers are behavioral, borrowed from the car suspension that damps road impact before it reaches the passenger; the framing is useful because it groups primitives that aren't usually grouped together, rate limiting, circuit breakers, retries, queues, caches, and asynchronous processing all sharing the job of damping a dependency's misbehavior before it reaches the caller. The 2024 challenges were one problem per axis: Challenge 1 a bulkhead strategy against gray failures inside one AZ, Challenge 2 a shock absorber strategy against an unreliable dependency. Case 1 is what a bulkhead would have contained; Case 2 is what a shock absorber would have contained.

### Challenge 1: The bulkhead response to gray failure

Challenge 1 was a credit card company's payment application on AWS with the expected mission-critical baseline (Route 53, ALB across three AZs, EKS, Aurora with a Global Database replica), asking specifically about gray failures inside one AZ, the same shape as Case 1. The answer the session built on, presented by my colleague Shunsuke Mabuchi, centered on **AZ independence (AZI)**: each AZ behaves as an isolated silo with zero cross-AZ dependencies on the data path. The [Advanced Multi-AZ Resilience Patterns whitepaper](https://docs.aws.amazon.com/whitepapers/latest/advanced-multi-az-resilience-patterns/advanced-multi-az-resilience-patterns.html) documents the moves (disable cross-zone load balancing, per-AZ Aurora read endpoints, composite alarms driving a Route 53 ARC zonal shift); the one that matters most for Case 1 is the deep health check that exercises the actual write-path dependency rather than a surface ping. It isn't free, a 3-AZ fleet provisions roughly 1.5x its baseline so each AZ can absorb a drained peer's share, and over-eager checks can drain a healthy AZ, but you buy isolation with it.

The mindset is what carries over: **every cross-AZ link is a potential failure propagation path, so you name each one and either eliminate it or accept it with eyes open.** Apply that to Case 1. The middleware nodes with failing storage sat in one AZ, and the cross-AZ link from the application to that middleware was the propagation path; its health definition didn't match the application's. The middleware saw "responsive compute," the application saw "stalled requests," and the implicit AZ boundary never triggered. Under AZI the bulkhead would have absorbed it: unaffected AZs keep serving, and a composite alarm drains the sick one within minutes. The bulkhead was present physically but absent *semantically*, and that's the failure mode AZI closes.

### Challenge 2: The shock absorber response to unreliable dependencies

Challenge 2 was the one I was on stage for: an e-commerce application (CloudFront, S3, ALB, ECS, DynamoDB with DAX) depending on a third-party service that was unreliable in the worst way, not down, just sometimes slow, sometimes erroring, worse under load, and not replaceable. When a dependency can't be fixed or removed, your only lever is how your system behaves when it misbehaves.

A buffer around a flaky dependency does two jobs: reduce load on it when it's struggling (rate limiting, circuit breakers, caches) and contain the blast radius of its failures (backoff retries, circuit breakers, asynchronous processing). Circuit breakers do both, failing fast while giving the dependency a break; everything else specializes. I proposed wrapping the dependency in a proxy service that owns this logic, so application code never handles retries or circuit breakers inline: it calls the proxy, and the proxy decides what to do. The proxy exposes four access modes the application picks per request:

1.  **Synchronous write.** Call now, retry on transient failure, fail fast once the circuit opens. Bounded latency, errors bubble up.
    
2.  **Asynchronous write.** Enqueue, return a request ID immediately, process in the background, let the caller poll. The caller never waits on the dependency.
    
3.  **Direct read.** Fetch fresh data and populate the cache on the way back.
    
4.  **Cached read.** Serve from cache on hit; on miss, return an error and let the caller fall back to a direct read if it wants fresh data badly enough.
    

![](https://cdn.hashnode.com/uploads/covers/69d1f25c6792e486f60903fd/32ee1e37-edab-45b4-bc30-73d7cf631b91.png align="center")

Two design choices held up under the session's discussion. First, **the application picks the mode, not the proxy**, because only the application knows whether a call is on the checkout critical path (fail fast), a background enrichment (retry later is fine), or a recommendation (stale beats missing); the proxy just gives it the vocabulary to say so. Second, **four modes because sync-vs-async and write-vs-read are two different axes**, the part Case 2 taught me directly: without the read-path incident I might have built three modes and treated reads as simpler writes, but a cached read that errors on miss is a different contract from a direct read that might fail after retrying, and the application should be able to say which it wants. The async mode polls rather than calls back, which both minimizes what an adopting team has to change and keeps reconciliation in a shape the application already understands, reading its own request state by ID, the same "design your reconciliation" move from the [Architecture Dojo 2025 post](https://blog.simukappu.com/4-lessons-from-dissecting-production-systems-at-scale-architecture-dojo-2025). Under the hood the four modes share one engine: API Gateway for entry-level rate limiting, Step Functions Express Workflows for the sync retry loop and circuit state machine, SQS for the async queue, Lambda for the consumer, DynamoDB for circuit state, request state, and cache.

The point of the four modes is that each converts a dependency failure into a different problem the caller can reason about:

| Failure mode | Synchronous write | Asynchronous write | Direct read | Cached read |
| --- | --- | --- | --- | --- |
| Transient degradation (slow, elevated errors) | Retries may succeed; latency increases; circuit may or may not open | Returns 200 to caller immediately; background retry usually succeeds | Retries may succeed; latency increases; circuit may or may not open | Hit: serves from cache. Miss: error |
| Persistent failure (dependency fully down) | Circuit opens; fails fast with 5xx | Returns 200 immediately. Background processing either gives up after retries and surfaces an error on poll, or keeps waiting for recovery (configurable) | Circuit opens; fails fast with 5xx | Hit: serves from cache. Miss: error |

The asynchronous write turns availability into a latency problem rather than a caller-side error (the order is placed, the notification goes out when it can); the cached read turns it into a freshness problem, trading possibly-stale data for a feature that stays up, which is right for reference or catalog data and wrong where staleness is dangerous.

The session's host raised the obvious objection: the proxy is now on the critical path of every dependency call, so what happens when it fails? Two answers, for different slices. Make it cheaply relocatable: the serverless implementation is stateless at the compute layer, so there's nothing to hand over at failover, an idle standby in another region costs almost nothing, and the application can switch to it, though as the host noted, a logic bug or misconfiguration replicates to every region. Or remove it as an independent failure domain, embedding its logic as a library or sidecar so it shares the application's lifecycle and there's no separate "proxy outage," at the cost of per-request elasticity and coupled deployments. The two target different failure modes, so neither fully replaces the other.

## Closing

Architecture Dojo 2024 ended on a line from Uchiumi-san I keep returning to: distributing infrastructure across locations, by itself, doesn't eliminate the failures that application architecture is uniquely positioned to absorb. Controlling the *impact* of failures, not their causes, is what application architecture is for.

Incidents of Case 1's shape tend to hit teams that have worked on resilience for years. The patterns aren't new to them; what's missing is follow-through against a backlog that keeps losing priority to cost optimization and feature velocity, until an incident reorders the priorities by itself. Architecture decisions are also decisions about what an organization is willing to invest in before it has to.

The session closed on a metaphor that still works for me. Think of the counters in a bank or a government office, separated by service. Combining them would use staff more efficiently, but separation keeps a customer with urgent business from being stuck behind less urgent ones, that's a bulkhead; and within each counter, taking a ticket or booking a time slot smooths the arrival pattern so the counter doesn't get overwhelmed, that's a shock absorber. The physical world has been refining these patterns for a long time, and sometimes the best way to see your own architecture is to look at the one you walk through every day. Since that session, every architecture review has me asking two questions earlier than I used to: where are the counters, and what's between them?

If you're carrying the scars of a gray failure that should have stayed in one AZ, or a dependency outage that took down more than it should have, I'd genuinely like to hear about it. The patterns that end up in posts like this one come from those incidents. They don't come from Dojo sessions alone.

Watch the 2024 session recording (Japanese): [https://youtu.be/eoBlprMYx\_E](https://youtu.be/eoBlprMYx_E)  
Past sessions: [2025](https://youtu.be/L-NcmkkDJMI) | [2023](https://youtu.be/s9YqEELWutA) | [2022](https://youtu.be/C7trZIt5H3w)