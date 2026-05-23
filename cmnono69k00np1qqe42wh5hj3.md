---
title: "4 Lessons from Dissecting Production Systems at Scale — Architecture Dojo 2025"
seoTitle: "4 Architecture Lessons from Production Systems at Scale"
seoDescription: "Constraint-driven design, evolvability, reconciliation strategies, operational patterns. Lessons from dissecting real-world systems at AWS Summit."
datePublished: 2026-04-07T13:29:11.099Z
cuid: cmnono69k00np1qqe42wh5hj3
slug: 4-lessons-from-dissecting-production-systems-at-scale-architecture-dojo-2025
ogImage: https://cdn.hashnode.com/uploads/og-images/69d1f25c6792e486f60903fd/0036c22d-4b26-47d3-bac1-46d78a370244.jpg
tags: microservices, aws, software-architecture, cloud-computing, system-design

---

Every architecture decision is a bet. A bet that your constraints won't change, that your assumptions will hold, that the trade-off you're making today won't haunt you in two years.

Since 2022, I've been pressure-testing exactly these kinds of bets through "Architecture Dojo" at AWS Summit Japan, a session where solutions architects tackle design challenges and we debate the trade-offs on stage. I joined as a panelist and hosted the 2025 edition (2,300 registrations), where we switched to a new format: instead of the usual design challenge, we dissected two production systems on stage. One was an e-commerce modernization, the other a next-generation core banking system. Both were large-scale, mission-critical, and operating under severe constraints. ([Watch the 2025 session recording](https://youtu.be/L-NcmkkDJMI), in Japanese.)

![](https://cdn.hashnode.com/uploads/covers/69d1f25c6792e486f60903fd/9703205e-c2cb-45b6-a767-bb62a0b26565.jpg align="center")

Here are 4 lessons I keep coming back to.

> **TL;DR**
> 
> 1.  **Constraints drive design.** The most impactful design decisions come from naming what you *can't* change, not from choosing services.
>     
> 2.  **Design for evolvability.** Structure your system so you can change it, instrument it so you can see what's happening, and evolve when the data tells you to.
>     
> 3.  **Design your reconciliation.** The question isn't "how do I make this perfectly consistent?" but "what's my reconciliation strategy when it isn't?"
>     
> 4.  **Start from the problem.** Prepare in parallel, decide sequentially. Services are implementation details; the real design work is understanding the problem's constraints, actors, and failure modes.
>     

## 1\. Constraints drive design, so make them explicit

It's tempting to start a design by asking "what's the ideal architecture?" But in practice, the most impactful design decisions come from understanding what you *can't* do.

ZOZOTOWN, Japan's largest fashion e-commerce platform serving over 10 million active users with 1,600+ brands, has been running since 2004. Their inventory database sits on-premises, with multiple dependent systems (including logistics management and customer management) that rely on it, and business logic implemented in SQL Server stored procedures accumulated over nearly two decades. Migrating the entire inventory DB to the cloud was not an option. Too many dependencies, too much risk, too long a timeline. So they didn't migrate the database. They extracted *just the inventory count*, a single integer per SKU (product-color-size combination), into Amazon DynamoDB, while leaving everything else on-prem. This "logical inventory" in DynamoDB handled the high-throughput reads and writes for cart operations, while the "physical inventory" on-prem remained the source of truth for everything else.

Why just the inventory count, and not the entire inventory table? Because the inventory table contains far more than counts (pricing, sale dates, and other attributes) and is referenced and updated by multiple dependent systems and stored procedures. Before the modernization, the web server called a stored procedure in the on-premises database ([details in this AWS Database Blog post](https://aws.amazon.com/blogs/database/how-amazon-dynamodb-supported-zozotowns-shopping-cart-migration-project/)), and that stored procedure handled both inventory allocation and cart registration in a single transaction. Extracting the full table would have meant rewriting those stored procedures and their dependent systems, expanding the blast radius of the change far beyond what the team could safely deliver. By scoping the extraction to a single integer per SKU, they minimized the integration surface and kept the release timeline to roughly six months. The constraint, "we cannot move this database," is what made the design possible. Without naming it explicitly, the team might have spent months debating a full migration that would never ship.

SBI Group, one of Japan's largest financial conglomerates, faced a different kind of constraint. They were building a next-generation core banking system on AWS for regional banks across the country. This was the first in Japan to be built from scratch on the cloud rather than migrated from on-premises, targeting sub-minute RTO for AZ failures. But banking industry protocols demand fixed IP addresses and persistent sessions for connections to ATMs, branch terminals, and external networks like Zengin (Japan's interbank payment network, similar to Fedwire or CHAPS). These requirements directly conflict with the elasticity that makes cloud architectures resilient.

Their solution was a "relay center," a physical facility that sits between the cloud environment and the banking network, translating stateful, fixed-IP connections into stateless REST APIs with DNS-based resolution. The cloud side stays elastic and ephemeral; the relay center absorbs the statefulness that the banking world requires. Why a physical relay center rather than a software-level protocol translation layer like an API Gateway? Because the external systems (ATMs, branch terminals, the national banking network) require not just protocol translation but also fixed IP addresses and persistent network sessions at the transport layer. A cloud-hosted gateway would still be subject to IP changes during scaling events or AZ failovers. The relay center's physical stability is what makes it a credible endpoint for systems that were designed decades ago with the assumption that their counterpart never moves.

In both cases, the design didn't emerge from choosing services or drawing boxes. It emerged from clearly articulating what was off the table. In my experience reviewing architectures across industries, the teams that struggle most are the ones that skip this step: they jump to "what services should we use?" before answering "what can't we change?" Constraints aren't obstacles to good design — they're the inputs that make design possible.

## 2\. Design for evolvability: structure, observe, adapt

Lesson 1 showed how constraints shaped ZOZOTOWN's *what*: extracting a single integer per SKU. Now let's follow the *how*, the timeline of their modernization and the structural properties that made it possible to evolve the system in stages.

ZOZOTOWN's modernization wasn't a single big-bang migration. It was a sequence of independently shippable phases, each solving a specific problem.

Phase 1 addressed the immediate crisis: a major sale event was 7 months away, and the on-prem inventory DB couldn't handle the expected traffic spike. They introduced an async queuing system between the cart service and the inventory DB, using Amazon Kinesis Data Streams with KCL (Kinesis Client Library) workers. The queue controlled the write throughput to the database, preventing overload. This alone was enough to survive the sale.

A critical design choice in Phase 1 was using a FIFO queue to preserve cart submission order. During a flash sale, thousands of users hit "add to cart" within seconds for the same limited-stock item. FIFO ordering meant inventory was allocated on a first-come, first-served basis, a fairness guarantee that matters when you're selling limited-edition sneakers to passionate customers.

But FIFO ordering introduced a new problem: a single hot item could block the entire queue. Inventory allocation for a single SKU must be serialized to prevent overselling, so a flood of requests for one hot item backs up the FIFO queue, blocking unrelated products behind it. If 10,000 users are trying to buy the same sneaker, every other product's cart operations wait behind them. ZOZOTOWN's solution was to split the queue: a dedicated queue and worker pool for hot items, and a separate one for everything else. The clever part is how they identify hot items. A maintenance batch analyzes access logs and automatically registers products whose traffic spikes exceed a threshold. The system adapts its own queue topology based on observed traffic patterns, without manual intervention.

Phase 2, implemented later, extracted inventory counts into DynamoDB to eliminate row-level lock contention, the root cause of the performance bottleneck. What made this phased approach work wasn't just "doing less per phase." It was three structural properties that the team deliberately built into the system:

*   **Changeability**: Microservice boundaries isolated the blast radius of each change. The cart service could be modified without touching logistics or customer management.
    
*   **Observability**: Traffic instrumentation made it possible to see where pressure was building (which products were spiking, where lock contention was occurring) and feed that data back into design decisions. The hot-item detection described above is one example; the decision to move to Phase 2 was another, driven by observed lock contention patterns after Phase 1 went live.
    
*   **Timing**: Observability data informed *when* to evolve. Phase 1 was driven by a 7-month deadline. Phase 2 was driven by the fact that read-write lock contention on the inventory table, the original root cause, remained an ongoing problem even after Phase 1 tamed the throughput issue. Phase 1 controlled the *rate* of writes to the database, but it didn't eliminate the underlying contention: writes and reads still competed for the same physical resources in SQL Server, and a hot product's inventory update could block unrelated reads sharing the same data page. Eliminating that contention required moving the hot data out of the RDBMS entirely, which is what Phase 2 did.
    

Evolvability isn't just about making change easy. It's about making the *right* change at the *right* time, and that requires the ability to observe your system's behavior in production and adapt based on what you see. I've seen teams over-provision databases for anticipated peak traffic that never materializes (single-digit percent utilization for months) while funneling batch processing, analytics, and transactional writes through that same database until the aggregate load makes it the actual bottleneck. ZOZOTOWN's approach is the antidote: build the structure that lets you change, instrument so you can see what's happening, and evolve when the data tells you to.

## 3\. Decompose transactions, design your reconciliation

Phase 2 of ZOZOTOWN's modernization, extracting inventory counts into DynamoDB, created a new problem: the cart operation now spanned two different databases. Adding an item to the cart required updating the logical inventory count in DynamoDB *and* inserting a cart record in the on-prem RDBMS. These two operations couldn't share a transaction. Many teams would reach for a distributed transaction protocol such as two-phase commit, a saga orchestration framework, or similar. ZOZOTOWN chose a simpler path: let each database update independently, and reconcile. What they built shares the spirit of a saga (independent local transactions with a mechanism to detect and correct inconsistencies), but rather than adopting a generic orchestration framework, they designed a problem-specific reconciliation strategy tailored to their consistency requirements.

They built two layers of reconciliation. The first is a near-real-time sync batch that continuously propagates the on-prem physical inventory's available-for-sale count to DynamoDB, keeping the logical inventory close to the source of truth. The second is a correction batch that runs periodically, targeting only SKUs where inventory movement was detected. It recalculates the correct logical inventory from the physical inventory and the cart-reserved inventory in the on-prem RDBMS, correcting any drift caused by partial failures in the cross-database write path. A full reconciliation across all products runs once daily as a safety net. Why a periodic batch rather than real-time event-driven reconciliation? Because the reconciliation needs to cross-reference state across two databases (DynamoDB and the on-prem RDBMS), and doing that comparison on every single write would add latency and coupling to the hot path. The periodic batch keeps the reconciliation decoupled from the transaction flow while still catching inconsistencies fast enough that they rarely affect end users. The daily full sweep is a defense-in-depth measure: it catches anything the incremental batch might miss due to edge cases in change stream processing.

Eventual consistency only works if each individual operation is idempotent. When a queue worker picks up a cart operation, it might process the same message twice, for example if the worker restarts mid-processing, or if multiple KCL workers process records from the same Kinesis shard. ZOZOTOWN handles this with a state management table that tracks each transaction's lifecycle: queued → processing → completed. If a worker picks up a transaction that's already marked completed, it skips it. This is a small detail, but in a system processing millions of cart operations, it's the difference between "eventually consistent" and "silently corrupted."

The key insight is that they didn't need perfect consistency at every moment. They needed to know *where* consistency could be relaxed and *how* to detect and fix inconsistencies when they occur. The user experience remained synchronous: the customer clicks "add to cart" and gets an immediate response. Behind the scenes, the system polls for the async inventory allocation result and shows an error if it fails. The UX feels instant; the backend is eventually consistent. I've seen this pattern (synchronous UX over asynchronous backends with explicit reconciliation) come up repeatedly in the systems I work with, from payment processing to order management. The question isn't "how do I make this perfectly consistent?" but "what's my reconciliation strategy when it isn't?"

## 4\. Start from the problem, not the services

When SBI designed their regional failover for the core banking system, they didn't start with "which AWS services support cross-region failover?" They started with a question: *who decides to fail over?* This is a question about operations, not infrastructure. A regional failover for a banking system isn't just a technical switch. It affects ATM availability, branch operations, nightly batch processing, and regulatory reporting. The decision to fail over must account for the bank's business continuity posture, not just system metrics.

SBI's design reflects this. The failover workflow is automated end-to-end using AWS CodePipeline, AWS Step Functions, and AWS Lambda, but it includes three explicit human approval gates, each corresponding to a distinct level of irreversibility. Why three gates, and not two or four? Because each gate marks a step up in consequences, and each requires a separate human judgment call.

The workflow starts the moment a regional failure is detected. Critically, resource scaling in the standby region (EC2 node group expansion, Kubernetes Pod scaling, and Aurora instance provisioning) begins immediately, *in parallel with the human decision-making process*, before any approval gate is reached. While the operations team is assessing the situation (checking AWS Health Dashboard, filing support cases, coordinating with the regional bank), the disaster recovery region is already scaling up. These are safe, speculative actions: they cost money but cause no harm.

The three gates then unfold as follows:

1.  **Initiation approval**: the point where the team commits to *preparing* for a switchover. It authorizes stopping the Aurora replica in the primary region and proceeding with the cutover preparation. Costly but reversible: you can abandon the failover and restart replication.
    
2.  **Continuation approval**: the point of no return for the data layer. It triggers Aurora Global Database promotion (the `failover_global_cluster` API action) and DNS record changes (`change_resource_record_sets`), redirecting traffic to the standby region. Once the standby database is promoted to primary, you can't simply "undo" it.
    
3.  **Service release approval**: the point where user-visible traffic starts flowing. ALB rule changes (`set_rule_priorities`) release traffic to end users, and transaction blocking is lifted. This commits to user impact.
    

This structure also maps to the bank's own business continuity rhythm. Regional banks operate on a daily cycle: nightly batch processing ends at 6:00, ATM transactions begin at 7:00, core banking hours run 9:00–15:00, ATM processing closes at 21:00, and the next batch cycle starts at midnight. The decision to fail over must account for where the bank is in this cycle. A failover at 10:00 during core hours has very different implications than one at 22:00 during batch processing. System metrics alone (latency spikes, error rates, Health Dashboard alerts) can tell you *something is wrong*, but they can't tell you whether the bank should switch regions right now or wait 30 minutes for a natural business checkpoint. That's a human judgment call, and the three gates give the bank's operations team exactly three moments to make that call: "start preparing," "commit to the cutover," and "open for business."

What makes this design work is the overlap between preparation and decision-making. Because resource scaling starts immediately, without waiting for any approval, the time spent on human deliberation is not wasted. By the time the operations team reaches the initiation approval gate, the standby region is already scaled and ready. This overlap is what makes the 1-hour RTO achievable despite requiring human approval at three points. Without this parallelism, the sequential cost of "decide, then prepare, then execute" would blow past the RTO target.

This "prepare in parallel, decide sequentially" pattern is worth internalizing. It shows up beyond disaster recovery, in incident response, in deployment rollbacks, in any situation where you need human judgment but can't afford to wait idle while humans think. The key is identifying which preparation steps are safe to run speculatively (scaling up standby resources costs money but causes no harm) and which require a decision gate (promoting a database and cutting over DNS is irreversible in practice). SBI drew that line precisely: everything before the data layer cutover is speculative and parallelizable; everything after requires explicit human commitment.

This design extends to the relay center described in Section 1. An obvious question is: doesn't the relay center itself become a single point of failure? SBI addressed this by building two relay centers, one in Tokyo (primary) and one in Osaka (disaster recovery), with cross-connections to both AWS regions. The active region is identified via DNS, and traffic routing between relay centers is controlled via BGP. The failover design covers not just the AWS regions but the entire network path, including the physical relay infrastructure, handling five distinct failure scenarios from normal operation through simultaneous failure of both the primary relay center and primary region.

The service selection (CodePipeline for orchestration, Step Functions for step control, Lambda for API calls) came last. It was a consequence of the operational design, not the starting point. CodePipeline's built-in approval stages happened to map cleanly onto the three human decision points, but the three-gate structure was designed before any service was chosen.

I see this pattern across the systems I work with: the architecture is shaped by the problem structure, not by the service catalog. Services are implementation details. The real design work is understanding the problem: its constraints, its actors, its decision points, and its failure modes. When I review architectures that start from the service catalog, they tend to be over-fitted to what the services can do rather than what the problem requires, and they're harder to evolve when the problem changes.

* * *

## What's next: Architecture Dojo 2026

This year, Architecture Dojo enters the AI era. The four lessons in this post don't disappear when your system includes a probabilistic, non-deterministic component, but they take on new dimensions.

Consider constraints (Lesson 1): an LLM's output is non-deterministic by nature. You can't guarantee the same input produces the same output. That's a constraint as fundamental as ZOZOTOWN's immovable on-prem database, and it shapes every downstream design decision, from retry logic to output validation. Or consider evolvability (Lesson 2): when model capabilities change every few months and today's prompt engineering patterns become tomorrow's anti-patterns, how do you structure a system that can swap out its AI components without rewriting the business logic around them? Reconciliation (Lesson 3) gets harder too: when your model's accuracy drifts over time, what does "eventually consistent" even mean? How do you set an error budget for a component whose failure mode isn't "wrong answer" but "plausible-sounding wrong answer"? And the "prepare in parallel, decide sequentially" pattern from Lesson 4 maps directly to AI agent orchestration, where you need to manage multiple concurrent tool calls while maintaining a coherent decision chain.

We're tackling these questions at AWS Summit Japan on June 26, 2026. When LLMs hallucinate, costs explode at scale, and agents lose context mid-process, what does good architecture look like? The non-functional requirements we've always cared about (scalability, reliability, cost, security) don't go away. They get harder.

Watch the 2025 session recording (Japanese): [https://youtu.be/L-NcmkkDJMI](https://youtu.be/L-NcmkkDJMI) Past sessions: [2024](https://youtu.be/eoBlprMYx_E) | [2023](https://youtu.be/s9YqEELWutA) | [2022](https://youtu.be/C7trZIt5H3w)