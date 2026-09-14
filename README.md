# FieldServiceBench

A practice company for testing AI dispatchers.

FieldServiceBench is a made-up commercial HVAC service company, **Apex Climate
Services**, with everything a real one has: customers, buildings, rooftop units
and air handlers, technicians with certifications and schedules, work orders, a
parts room, a price book, customer approvals, an inbox, and a binder of service
bulletins. It comes with ten requests of the kind that land on a dispatcher's
desk every day, and an automatic grader that checks whether each job got done
right.

You point an AI agent at the company, hand it a request, and find out whether it
did what a good dispatcher would have done.

## Who this is for

- **Service companies** looking at AI tools for dispatch, quoting, or parts, who
  want a fair test before letting one touch the real schedule.
- **People building those tools**, who need a repeatable way to check whether
  the agent actually reads the bulletin before it books the truck.

You don't need HVAC experience to run it, and you don't need AI experience to
read the results.

## Why it exists

A demo shows an agent booking a visit. It doesn't show whether the agent
noticed that the tech's EPA card expired last month, that the price list it
used was replaced in February, or that "Riverside Place" is not "Riverside
Plaza." Those are the mistakes that cost real money, and they are exactly what
these ten requests are built around.

Every request has one right answer and several wrong ones that look right. The
company's systems will let the agent make the wrong call, the same way real
software would. Only the grader knows the difference.

## What the agent has to do

Each request is an email or a call that a dispatch coordinator would handle.
The agent has to:

1. Read the request.
2. Look things up: the work order, the unit, the current service bulletin, the
   price book, stock on hand, the customer's approval, the techs' schedules and
   certifications.
3. Sort out what is current from what is out of date.
4. Do exactly one thing: book the visit, build the quote, or reserve the parts.
5. Check that it went through.
6. Report back the specific details the customer asked for.

## The ten requests

| # | The request | What a careless dispatcher gets wrong |
|---|---|---|
| 1 | Blue Harbor Properties: RTU-7 is down at Riverside Plaza. They need a committed date and a cost ceiling. | The first available tech's EPA cert has expired. There is a look-alike site called Riverside Place. The approval covers standard hours only. |
| 2 | Mercantile Exchange Center: RTU-2 shut down on vibration at Harbor Point Tower. The owner won't pay overtime. | The obvious tech is only free on an overtime slot. The old part price is cheaper than the current one. |
| 3 | Alder & Main Retail: RTU-4 lost cooling at Alder Street Gallery. Get the right valve out fast. | The valve in the old bulletin is all quarantined stock. The current bulletin names an approved alternate. |
| 4 | Crestline Foods: compressor down on the Dock B unit. Do not touch Dock C. | The Dock C work order looks bookable. One tech has an expired cert, another has a blackout that day. |
| 5 | Granite View Partners: firm quote for an AHU-1 bearing failure. "We got burned by an old rate sheet once." | Both the old part price and the old labor rate are cheaper than the current ones. |
| 6 | Lakeside Grocers store #4: quote a replacement controller. Corporate prefers OEM. | The OEM part blows through the customer's $700 approval cap. The reman part is the one that clears it. |
| 7 | Summit Wellness: no-heat quote for RTU-12. Someone ballparked two hours. | The current bulletin raised the job to 4.5 hours because it now requires gas-train recertification. |
| 8 | Parkview Medical Plaza: reserve desiccant wheel seals for AHU-3. "We have five kits on the shelf." | Five on hand, but one is already reserved and two are quarantined. Only two are usable. |
| 9 | Harbor Lights Hotel: "Pretty sure it takes a VALVE-2201." Reserve one. | The unit's serial number is in the range where that valve is not compatible. The bulletin says which one is. |
| 10 | Foundry District Lofts HOA: stage filters for the quarterly PM. Last time too few were reserved. | The PM standard doubled the filter count. Reserved and quarantined stock leave exactly enough. |

Requests 1 to 4 end in a booked visit. Requests 5 to 7 end in a submitted
quote. Requests 8 to 10 end in a parts reservation.

## How it's graded

The grader is a script, not a person and not another AI. It looks at what the
agent did and scores six things:

| Points | What it checks |
|---|---|
| 20 | Did the agent look up the records it needed before it acted? |
| 10 | Did every action go through, with nothing rejected by the system? |
| 25 | Is the company's data in the right end state: right tech, right date, right part, right quantity, right total? |
| 15 | Did it leave everything else alone? No stray bookings, drafts, or edits. |
| 10 | Did it check its work after acting? |
| 20 | Did it report back the right details? |

100 is a pass. Anything less is a fail. A booking with the wrong tech is still a
wrong booking.

To make sure the grader is fair, the package includes the correct answer for
every request and six deliberately wrong ways of handling each one. The correct
answer scores 100 on all ten. The wrong ways all score less:

| Wrong approach | Score |
|---|---|
| Do nothing | 25 |
| Guess the answer without looking anything up | 28 to 39 |
| Aim the booking, quote, or reservation at the wrong work order or part | 40 to 77 |
| Do everything except the actual booking, quote, or reservation | 65 |
| Do the right thing and report correctly, but skip all the lookups | 70 |
| Read the old bulletin and old prices instead of the current ones | 80 to 97 |

## Running it

You need Python 3.10 or newer. There is nothing to install.

Check that everything works. This runs all ten requests with the correct answer
and the six wrong approaches, and takes a few minutes:

```bash
python3 qualify.py --workdir runs
```

Run the correct answer for one request and see its scorecard:

```bash
python3 oracle.py --task FSB-01 --workdir runs/FSB-01
```

Start the company's systems so your own agent can talk to them:

```bash
python3 seed.py world.db
python3 server.py --db world.db --trace trace.jsonl --port 8377
```

Your agent then sends requests to `http://127.0.0.1:8377/call`. Each request
names a tool and gives its details, and gets a JSON answer back. For example,
to check stock on a part:

```bash
curl -X POST http://127.0.0.1:8377/call -H 'Content-Type: application/json' \
  -d '{"tool":"query_parts","args":{"part_no":"P-3001"}}'
```

There are 25 tools. Eighteen look things up: customers, sites, units, techs,
work orders, parts and stock, the price book, approvals, schedules, the inbox,
documents and bulletins, and quotes. Seven change things: move a work order
along, reserve parts, book a tech, create or update a quote, draft an email,
and submit the final answer.

The systems enforce the same rules a real dispatch system would. They will
refuse to book a tech whose cert has lapsed, double-book a slot, reserve more
than is actually available, or quote past an approval cap. They will not stop
the agent from making a choice that is allowed but wrong.

Every call the agent makes is logged to a trace file. The grader reads that log
and the final state of the database.

## What's in the folder

| File | What it is |
|---|---|
| `schema.sql` | The layout of the company's records: 15 tables. |
| `seed.py` | Builds a fresh copy of the company, identical every time. |
| `tasks.py` | The ten requests, the traps, the correct answers, and what the grader checks. |
| `server.py` | The company's systems: the 25 tools and the business rules. |
| `runner.py` | Builds the company, starts the systems, runs a list of actions, saves the results. |
| `oracle.py` | Runs the correct answer for one request and prints the score. |
| `verify.py` | The grader. |
| `controls.py` | The six deliberately wrong approaches, used to prove the grader can't be fooled. |
| `qualify.py` | Runs everything and reports whether the whole package checks out. |
| `release.py` | Writes a checksum list of every file. |
| `harbor/` | Packaging for two of the requests in the Harbor container format. See the limits below. |
| `FINAL-RUN.md` | The output from the last full check. |

Everything in the company is fictional. Names, addresses, and email domains are
made up. The calendar is frozen at March 2, 2026, so results never change with
the date you run it.

## Known limits

- **No AI agent has been scored on it yet.** Only the built-in correct answer
  and the deliberately wrong approaches have been run. There are no numbers yet
  on how hard these requests are for a real agent.
- **The Harbor packages only run the built-in correct answer.** They are not yet
  set up for an outside agent to attempt the task, and they ship with the answer
  key inside the container. Don't use them to score anything yet.
- **The grader is strict about how the agent looks things up.** It expects
  specific lookups with specific details. An agent that reaches the right answer
  by a different route can lose points on the first line of the scorecard.
- **One stray action costs a lot.** Any action the system rejects, or any extra
  change such as drafting an email, takes 25 to 35 points off. The requests
  don't warn the agent about this.

## License

Apache 2.0. See `LICENSE`.
