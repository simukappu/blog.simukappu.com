---
title: "Sent, Accepted, Reached: Automating a Home Theater That Is Also My Office"
seoTitle: "3 Home Theater Automation Lessons: Sent, Accepted, Reached"
seoDescription: "Alexa said the theater was shutting down. The projector stayed on. Sent, accepted, reached: three facts my home automation had to log apart."
datePublished: 2026-10-30T09:42:51.117Z
cuid: cmvusal8p000102p1ht3j9zfq
slug: sent-accepted-reached-automating-a-home-theater-that-is-also-my-office
ogImage: https://cdn.hashnode.com/uploads/og-images/69d1f25c6792e486f60903fd/52a715b4-134d-4b0a-a38a-71c63e6a52d4.png
tags: iot, system-architecture, system-design, distributed-systems, observability

---

One day I asked Alexa to shut down the theater. Alexa answered, "Shutting down the theater," and the routine ran all the way to the end. The projector stayed on.

The room is my home theater with 7.1.4 speakers and a 100-inch screen, and it's also my office. I watch Blu-rays from my collection, recorded dramas and sports games, and whatever Apple TV and Fire TV Stick stream. I sometimes listen to music as well. A theater should start the moment you want it and shut down the moment you're done. Yes, like on-demand cloud computing.

When an automated system says it's done, the only thing done may be sending the command. Sending a command, the device accepting it, and the device reaching the requested state are three separate facts. The automation in this room treated them as one. It's the same problem as telling a request's acknowledgment (ack) apart from its completion between services.

I chose a small subject on purpose. No customers, no on-call rotation, one operator. In exchange, I can follow every step from a voice request to the moment a device actually gets there, and what I found generalizes more than you'd expect. Blame it on the architect in me. If you're curious, AV geek or not, come along.

> **TL;DR**
>
> 1. **Computers and AV gear share the screens and keep their own paths.** Three worlds share one room: TCP/IP, video over HDMI and coax, and infrared and radio remotes. The wiring in the walls should last as long as the house, while the sequence code went through four versions in half a day. A Mac mini at the TCP/IP center ties it all together.
> 2. **AI builds the state checks fast, and they still misread real devices.** An AI coding agent found an undocumented recorder's power toggle by proposing an HTTP proxy on the Mac mini, and all I did was point the iPhone at it. The arrival checks the same agent wrote then misread the state twice on their first run against real devices.
> 3. **Record acceptance and arrival as separate facts.** The old stop routine read nothing back and shut the room down in 2 of the last 10 runs. The new sequence logs each step as reached or only accepted, and went 10 for 10. The shutter's gateway says `COMPLETED` after the same 31 seconds every time, though the shutter stops in about 16, so a "completed" can fool you more easily than a plain "accepted."

## Computers and AV gear share the screens and keep their own paths

I'll come back to the projector that stayed on. First, let me tell you about the room. I wanted desk time and watching-and-listening time in the same place. So into a room of about 13 square meters, I packed those 7.1.4 speakers, the motorized screen (KIKUCHI SCREEN SES-100HDCW/W) and the desk I work at. It's a greedy little room.

As for what plays here, the Blu-ray shelf probably holds more than 300 films. I haven't counted them exactly, which is a little embarrassing for someone whose theater logs every step it takes. I'm a big fan of Christopher Nolan, so every one of his films is in there. *Tenet* I've seen at least twice, in a cinema and in this room, which seems to be the minimum for that film. I own nearly all of Studio Ghibli too, though lately it's my kids watching *My Neighbor Totoro*, and I'm the neighbor in the next seat. When I show the room off, I crank up a racing film for the sound: *Ford v Ferrari*, *F1*, or the podrace in *Star Wars: Episode I*. In baseball, I root for the Dodgers, where Japanese players shine, but what I really love is a team without deep pockets that builds a winner, like this year's Brewers, in 2026.

Three worlds share the room. In the TCP/IP world, the LAN reaches recorders in other rooms, and the WAN reaches the Alexa and SwitchBot clouds and the streaming behind Apple TV and Fire TV Stick. In the world of video signals, coax brings broadcasts in and HDMI carries picture and sound. In the world of remotes, infrared (IR) and radio run devices on the simple faith that a pressed button is a delivered button. Each world has its own language and its own manners about answering back.

In the video world, the displays are shared and the paths are separate. The Apple Mac mini drives a 32-inch and a 27-inch monitor directly. The AV receiver (Denon AVC-X6700H) reaches the same monitors and the projector (Sony VPL-XW5000) over its own path. An HDMI line from the Mac mini into the receiver puts the Mac on the 100-inch screen too. The monitors do double duty, as work screens and as AV outputs.

![](https://cdn.hashnode.com/uploads/covers/69d1f25c6792e486f60903fd/0dd68d6c-afe9-4afe-8fb6-0dff6a40a53f.png align="center")

Different worlds also have different lifespans, like the layers of a building that change at different speeds (the shearing layers Stewart Brand popularized in *How Buildings Learn*). The longest-lived layer, the LAN and coax in the walls, will with luck last as long as the house. Devices get replaced every few years. The shortest-lived is my sequence, which went through four versions in less than half a day on real devices. Because the layers meet at generic ports like LAN and HDMI, I can rewrite a fast layer without dragging the slow ones along.

Control, which runs across the TCP/IP world and the world of remotes, has the worst manners. The projector speaks ADCP (a protocol for operating and querying it over the LAN) over TCP, the AV receiver speaks HTTP and telnet, and the recorder (Sony BDZ-FBW2100) has a LAN port too. The screen understands only IR, relayed from the cloud by a SwitchBot hub. The shutter's one-way radio remote tells nobody how things went, and neither does the Somfy gateway (Connexoon) that now relays LAN instructions to it.

Physics applies to control too, as architecture constraints that can't be moved. IR is one-way and needs a line of sight, and the SwitchBot hub on the rear shelf struggles to reach the projector and the recorder on the same shelf. The projector's spot is fixed by the throw distance for a 100-inch picture. So the projector and the recorder moved to the LAN, and only the screen at the front, which gets IR fine, stayed on it. I always want the shutter closed when I watch, so it joined the sequence later through the gateway. The lighting I want depends on what I watch and who I watch with, so I still dim the lights by hand. Putting everything on one mechanism would make a prettier diagram, but where the effort buys no real improvement, I left things manual. Not automating something is a perfectly respectable design decision.

With all that in place, I designed the control around TCP/IP. On the Mac mini, Homebridge (relay software that connects home devices to Alexa and Apple's Home app) runs one small plugin per device to absorb its quirks, plus the start and stop sequences. Alexa and the iPhone just press Theater start or Theater stop. Adapters absorb the protocol differences and one place orchestrates the components, the shape we know from cloud design. The computer on the desk moonlights as the theater's conductor.

![](https://cdn.hashnode.com/uploads/covers/69d1f25c6792e486f60903fd/d8a4d02d-f5e1-455a-b2b0-91a288f41ff9.png align="center")

I set the trade-off between dependency and replaceability place by place. Matter (a smart home standard) and HomeKit let Alexa and the iPhone press the same buttons. The conductor, though, has no understudy. If the Mac mini stops, all that's left is each device's own remote or app. Remotes come in the box, so this isn't anything to brag about, but a fallback deserves a plan. Let's say they're a second path I kept on purpose.

So that's my room today. I've been sounding rather pleased with myself, but it didn't start out this way. I rebuilt the control around TCP/IP only after the day I opened with, and until then the routines had never once checked what happened after an instruction.

## AI builds the state checks fast, and they still misread real devices

To check state, you first have to learn each device's language. The projector and the receiver come with public documentation. The recorder doesn't. Now what?

The projector went on the LAN first. I ran one more LAN cable to the switch, alongside the recorder's. Asked over ADCP for its power state, it answers `standby`, `startup`, `on` or `cooling`, and a single power-off takes it all the way down to standby. That was also goodbye to the IR double press, which the next chapter explains.

The recorder was the tough one, with a LAN port for control and no documentation for it. An AI coding agent proposed running an HTTP proxy on the Mac mini to record what the manufacturer's official app sends, and all I did was set the proxy on the iPhone's Wi-Fi.

It turned out the app sends the same power key for on and off, a toggle. For a person looking at the screen, that's correct, because they see the state and decide whether to press. The only one in trouble is my automation, which can't see the screen. So the sequence reads the state, sends the toggle once, and reads the state back. Wake-on-LAN, which the sequence sends first when the recorder is in standby, wakes only its network side. It talks in its sleep.

With all five languages in hand, here's what the sequence can see of the three facts, device by device.

| Device | How far a command is known to get | Returns acceptance? | Can arrival be read? |
| --- | --- | --- | --- |
| Projector | The device, over the LAN | Yes (a response line) | Yes |
| AV receiver | The device, over the LAN | No. Always the same empty response | Yes, but the value can be stale |
| Recorder | The device, over the LAN | No | Yes. Silent in standby |
| Screen | The SwitchBot cloud. Whether IR left the hub is unknown | Yes, from the cloud only | No. IR has no way back |
| Shutter | The Somfy gateway | Yes, from the gateway (execution started) | No. The radio is one-way |

For a device that returns no acceptance, "success" right after sending means nothing. Whether a step worked is decided only by reading its arrival back.

The same agent implemented most of the work, and I made the occasional call on the design and the approach. Every test against the fake devices (mocks) the agent built passed. Mock devices are always agreeable.

The first time I ran the start sequence on the real devices, two of its five steps were logged as failed, yet both devices had arrived. The projector had finished starting, and the receiver had switched to Blu-ray. Both bugs were in the arrival check the agent wrote. One state query timed out during the projector's startup, and the code took that single timeout as "did not arrive," though a query can be repeated without changing anything. The receiver's HTTP status page kept showing the old input for more than three minutes, while telnet (port 23) already said Blu-ray. Why HTTP lagged, I still don't know. Something like a cache, perhaps, the kind of thing real-world systems do too.

The fix keeps reading through failed reads until a deadline and never resends a command, not even an input change that would be safe to repeat. A resend acts on a read, and the reads had just been wrong twice. For the recorder's toggle, a resend on a wrong read would switch it right back off. The sequence now reads the receiver's state on port 23 and falls back to HTTP only when port 23 doesn't answer (many Denon receivers take only one telnet client at a time). An HTTP value that matches the target gets confirmed on port 23 before it's believed. That last step matters. Both misjudgments called a success a failure and cost only a false alarm. The other direction, which hasn't happened yet, is the dangerous one. If a stale value happens to match the target, the sequence proudly concludes the device is already there, sends nothing, and records a success. So the check is most suspicious exactly when the value matches.

Looking back, the agent that proposed how to learn the recorder's language also misjudged arrival twice. I'm not sure whether to praise it or scold it, so both go on the record. What the undocumented device said became clear quickly. Whether the code listening to each device was right stayed unknown until it ran on real devices. The scale is nothing alike, but I think the same pair comes along when you modernize an undocumented system with AI.

Code written with AI got one more kind of check, human review. My change to expose the projector over Matter first lived in a fork only I could fix. The plugin's author reviewed it, asked for two fixes, and released it as v1.1.0 ([PR #2](https://github.com/keremerkan/homebridge-sony-adcp/pull/2)). One fewer part only I can fix, and that genuinely makes me happy. However fast AI makes development, I hope this OSS culture stays, and keeping it alive is a job for us humans.

## Record acceptance and arrival as separate facts

Back to the routine before the fix. An Alexa routine called a SwitchBot scene (a saved bundle of operations), and the scene sent IR from the hub to the screen, the projector, the recorder and the receiver. IR goes out and never reports back. In network terms, it was fire-and-forget UDP with a prayer attached.

The shutter was even more physical. A SwitchBot Bot (a small gadget that presses a button) sat on the Somfy remote, a robot finger hired for a human finger's job. Its battery died at some point, and it quit without notice. I can't tell you when. The projector's shutdown had another wrinkle. One press of its power button brings up a confirmation and a second turns it off, but only if the first arrived. Otherwise the second becomes a new first, and only the projector knows which happened.

Laid out in order, there are four facts the old routine couldn't see. Here, sent splits in two, because a cloud scene sat in the middle.

| Fact | Visible to the old routine? | What a miss looks like |
| --- | --- | --- |
| The scene started | No | Nothing happens, or it runs minutes late |
| IR or radio was sent | No | You can't tell, even from inside the room |
| The device accepted it | No | The first press never arrives, so the second means something else |
| The device reached the requested state | Only to someone in the room | The routine finishes, and the projector stays on |

Before the fix, I counted the old stop routine. In the last 10 runs, the room actually shut down twice. That's batting .200. One run is one shutdown request by voice, and a success means the projector reached standby without my touching anything. Most failures were the scene starting late or not starting at all. It used to be better than this, but I have no numbers from back then. Nothing read any state, so the decline left no record.

Why it got worse isn't pinned down. My own read is that the cause is compound. IR has always struggled to reach the devices on the rear shelf. The scenes run on a cloud service I use for free, with no SLA on how fast a command reaches the hub. Expecting one would be unreasonable, and building as if there were one was my mistake as the designer. And nobody watches whether IR was actually emitted, so there's no telling afterward where things fell through.

The new sequence records each step as one of five results: arrival confirmed (`reached`), already in that state (`already`), acceptance only (`accepted`), not sent because a precondition wasn't met (`skipped`), and `failed`. The screen is on IR, so it comes out `accepted` every time. That's what an honest log says.

The shutter, added later, is also `accepted` every time, for a different reason. The Somfy gateway reports `IN_PROGRESS` about a second after the command, then `COMPLETED`. In all six runs I measured, opening or closing, `COMPLETED` came 30.7 to 30.9 seconds after the command, while by my stopwatch the shutter stops after 15.5 to 16 seconds. The radio is one-way, so the gateway can't know where the shutter is. This house's gateway was watching the clock, not the shutter, which is about all you can do when you report on something you can't see. The catch is that a `COMPLETED` is easier to mistake for arrival than a plain acceptance. So the sequence records `accepted` at `IN_PROGRESS` and doesn't wait. Even with a `COMPLETED` in hand, the honest log still says `accepted`.

After the fix, counted the same way over the last 10 runs, the room shut down 10 times out of 10. Quite a career turnaround for a .200 hitter. The screen can be confirmed only up to acceptance, but apart from the 7.1.4 speakers, it's the loudest thing in the room, so I don't even need to look. My ears confirm its arrival. That's human in the loop in the most literal sense. Someday I'd like to swap that human for the desk camera's microphone.

Even so, the Alexa and iPhone buttons can say only that the sequence was accepted, and physics is why. The projector takes 20.5 to 22.1 seconds to start and 15.7 to 16.1 to cool down, so the sequence takes 22 to 23 seconds to start and 17 to 20 to stop. The Matter on/off that Alexa talks to is a single boolean, with no room for "starting" or "cooling." You can't fit 20 seconds of physics into one bit. So the buttons answer on acceptance, and Alexa's "OK" means "the Mac mini has the job," not "the theater has shut down." In HTTP terms, Alexa's "OK" is a 202 Accepted, not a 200 OK. Only the room and the Mac mini's records know whether the devices arrived.

One change helps people in the room see acceptance. The first stop sequence moved the screen last, after the projector's 16-second cooldown, so the screen looked slow, though its command was accepted in 216 ms. The slow part was the order I'd chosen. Now the screen moves first both ways, the most visible sign that the sequence was accepted.

## Closing

Here's what to take home and do. For each step of your automation, write down which of sent, accepted or reached you actually observe. Then tell users which of the three your "success" means, in those words. And for every "completed" you show, know whether it was observed or assumed. In my room, the Alexa and iPhone buttons can only say accepted, so arrival lives in the Mac mini's records. My seconds won't predict yours, but this way of counting travels.

All of this looks a lot like the [four lessons I took from Architecture Dojo 2025](https://blog.simukappu.com/4-lessons-from-dissecting-production-systems-at-scale-architecture-dojo-2025), especially the one about deciding how to reconcile declared and actual state when they drift. I came home, and the same lessons were waiting for me. Sigh. In the theater, I'd rather forget about architecture and just watch a movie...

Anyway, life is unpredictable, and that's a big part of the fun, but we built this house to last. It's certified under Japan's long-life quality housing program, and I had LAN and coax run to every room. That wiring, the longest-lived layer, is as it was. The sequence, the shortest-lived one, was rewritten many times in a few days. Because the slow layer stayed put, the fast one could change freely. What changed is that the sequence now reads its own results.

I'm grateful to the author of the projector plugin for reviewing my proposal and merging it. The plugin that drives IR through SwitchBot is published as [homebridge-switchbot-ir-matter](https://github.com/simukappu/homebridge-switchbot-ir-matter), and the plugin that runs the whole theater's sequences is [homebridge-theater-sequence](https://github.com/simukappu/homebridge-theater-sequence).

If you've read this far, this post is at least `accepted`. Happy watching, and happy architecting!