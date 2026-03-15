My current agentic workflow is about 5x faster, better quality, I understand the system better, and I’m having fun again.
My previous workflows have left me exhausted, overwhelmed, and feeling out of touch with the systems I was building. They also degraded quality too much.
This is way better.
I’m not ready to describe in detail. It’s still evolving a bit. But I’ll give you a high level here.
I call this the Night Shift workflow.

The key components of Night Shift:

My time and energy and “human token usage” (reading and writing text) are highly constrained and expensive resources
Agents and agent tokens are cheap and plentiful and practically unconstrained
I want to remain in control, with the minimum (but no less than the minimum) of my own effort and time
I do not like babysitting agents


I do not want to read agent plans.
I do not want to sit and prompt and reprompt agents.
I want them to get better over time.
I want to focus on one thing at a time.
I want to be in control.
I don’t want to feel anxious when an agent is sitting idle waiting for me.

So, I decided that I will take the day shift, and AI agents will take the night shift.
I will prepare everything for them as much as I can during the day shift.
Then, during the night, they will work autonomously while I am resting, and be done by the next morning.

During the day shift, it’s my time. The agents are sitting idle. I am not babysitting them.
I interface with humans, gathering requirements, thinking through the system architecture, and writing up a specification document with as much detail as I can write.
I spend a lot of time on this. I snooze AI autocomplete. I do as much work myself as I think necessary to spec out the work for the agent tonight. The system design and possible problems and solutions get embedded in my brain.
Specs describe the feature, all the edge cases to cover, everything I can think of. They’re well organized — not for the agent, but for ME. To organize my own thinking.
I do not run the agent to implement yet.
When i finish and have more time, i take another feature. I write out the spec. I take my time. I work at a sustainable pace.
I take breaks. Everything is sitting idle and silent.

I do use AI during the day shift, but it’s in short narrow “Ask” mode, where I simply ask it to find information for me. It’s a helper bringing info to my desk. It had better be concise. I am not here to read pages of generated text. Give me the sharpest most concise answer. Let me do the design.

Finally, it’s time to wrap up for the day. If I’m not done with a spec, that’s okay. Leave it for tomorrow.
All the completed spec docs live in a folder, ./Specs. If they are named draft-*, the agent will ignore them.
I load up Claude Code, Cursor, or Codex — whichever I’ve decided will work that evening.

I tell it to load @AGENT_LOOP.md. This is a markdown file that explains the process of how to work at night. More on this later.
Critically, @AGENTS.md is a small (~150 line) “router”, which tells the agent where to find documentation. This includes workflow docs, skill docs (I don’t use skills directly, these are equivalent though), and system documentation (describing different parts of the system).
I kick it off, and I close my computer for the evening. I’m done. The Night Shift is on it.

While I’m away, the agent does the following:

Prep: Cleans the working tree by analyzing any uncommitted work and doing the right thing with it (stash or commit). Also runs the entire current test suite and fixes any failures it encounters.
Picks a task from bugs first, or if bugs are complete, a feature that I’ve completed a spec for
Loads up the spec, and then analyzes it
Loads relevant docs, then looks at relevant code
Develops a testing plan (absolutely critical)
Writes extensive tests for this, then runs them, expecting failures
Develops an extensive plan of its own (I NEVER read this, I do not care)
Runs sub-agents as critical reviewers (review agents) based on 6 personas I’ve detailed in REVIEW_PERSONAS.md: Designer, Architect, Domain Expert, Code Expert, Performance Expert, Human Advocate. Each of these “owns” a portion of the docs, and reviews against their own documentation, including suggesting where their own docs need to be adapted.
Adapts plan based on review agent reviews, and loops to 7 until green light from all review agents
Implements the plan, including documentation adjustments (docs live in the same code base under Docs)
Runs type checking, linting, compiler, other static analysis tools such as bundle size reporter, as many things as possible, and of course the relevant tests themselves, and verifies that it works, iterating as it goes
Run the entire test suite to protect against regressions, fix any new issues
Runs the review agents again on the implementation diff, and loops back to step 10 until getting a green light from all review agents.
Add any encountered unrelated TODOs for human review that they’ve noticed along the way to the TODO doc
Wrap-up: write a CHANGELOG entry, commit with a detailed commit message meant for human context when reviewing the code. (More on commits later)
Loop back to the beginning (step 1), and select the next task or spec.
When completely done, write up a report for human review. Extremely concise. Details live in commit messages.
The Night Shift is done. It goes silent and waits for me to wake up.


When I come in for the day shift, the first thing I do is review the changelog and look at the agent recap.
Then I go commit by commit. I review each one, looking at the commit message and implementation diff. I examine the tests it wrote and the code itself, the docs changes.

I keep all commits in the same branch. I want them to stack on each other (a good use for stacked PRs, btw). Improvements should be used for each subsequent commit. Fewer conflicts, better results, less duplicative work.

If I need to correct something very quickly (low effort) I do it using an interactive agent session or just do it by hand. But before I do, i ALWAYS analyze and correct the docs, workflow, validations/testing.

If your agent misbehaves and writes the wrong code, don’t tell it to fix the code. And don’t fix it yourself.
Use that valuable context to figure out WHY it did the wrong thing. Tell it the issue, have it analyze its own context, and have it tell you what docs or skills or workflow is wrong, and what improvements would make it make the right decision next time.
Then have it fix those issues. Be very diligent that it gets it right. Be prepared to hand tune this, because you can amortize the improvement over the rest of your project.
Only after that, have it fix the original issue.
More about that step here: https://t.co/ch8v9oRvxj

I also test manually. I check almost every change manually, and thoroughly.
It’s not just that I want to catch bugs. I obviously do. But just as importantly, I want to catch gaps in my docs, skills, specs, validations/tests, my own understanding of the system. And fix them!

Then I get back to the first part of this. I gather requirements, write specs, do architecture, and think a lot.
The Night Shift needs my best work. So I do my best work without context shifting and babysitting agents.

That’s my Night Shift agentic workflow.
An important characteristic of this is that I am NOT there to babysit it.
I can’t paper over docs or workflow imperfections by steering it by hand. I must improve every day, so the next morning isn’t spent cleaning up a mess. Constant improvement via a feedback loop is the key.
I started using this workflow about a month ago, and it has gotten better and better every day. Every time I come in to look at the code, the results are better than before.
I’m spending far less time babysitting, much more time thinking about the problems I need to solve, and my productivity soars.
Very little context shifting, more peaceful and relaxed workflow, and when the agent runs that night, it runs unimpeded by me.

Some other notes:

automated testing is incredibly important. This WILL NOT WORK if you don’t have a super robust end-to-end testing harness in place and excellent docs so the agents can create their own tests.
spec writing is hard at first and gets easier. Don’t give up because it’s hard. Your brain will get better and better at it.
specs don’t have to solve everything for the agent. The more that you push into docs instead, and have a good agent router to hint to the agent to load those docs, the smaller your specs can be.
be as strict as possible with your type checking and linting system. I used to be anti strictness, but that was when I was a wetware dev. For agents, I want the most strictness possible.


You should be willing to burn all the tokens trying to make sure everything is as perfect as the agent can make it before a human ever has to review anything.
A human should not be having to catch basic obvious issues. If so, your automated validations suck and you need to fix them. This includes having robust agent review steps.
My time and energy are precious. I will not accept anything less than the agent’s best.
/fin

PS. One experiment I ran was to have Codex watch what Claude was doing and write feedback into a file. Claude knew it was doing this, would tail the file, and pull in the feedback for consideration. It actually worked pretty well and I may do this more often in the future.
Prompt:
"I have another agent doing the AGENT_LOOP.md right now, working through TODOS.md. What I'd like you to do is do your own loop as an expert reviewer.

Sleep for 5 minutes at a time.
Then, wake up look at the current git log to see if any new commits have landed
Systematically review them against the corresponding TODOS.md entry.
Provide your feedback about each commit in a file named TODOS_CODEX_REVIEW.md located in the same folder as TODOS.md.
I will tell the other agent to take a look at your notes for it in that folder, and it will then incorporate your feedback in a separate, second loop.
If you do not find any new commits (even if there are working tree changes), please don't do anything and just sleep again.
You'll know you should be done when all the current TODOs are marked complete or moved into the "NEEDS INPUT FROM USER" section. In that case, you can stop.
If you do not see any changes within 30 minutes, go ahead and stop, as the other agent may have quit prematurely."
