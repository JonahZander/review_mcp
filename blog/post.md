# Building the bridges your AI needs

*How I built a custom AI tool for Google Reviews, and why purpose-built tools beat generic ones for predictable workflows.*

**Jonah Zander** | March 3, 2026

---

You probably already use ChatGPT or Claude. Maybe daily. But you've noticed the gap: you ask about something specific to your own systems (a database, a CRM, what your customers are saying on Google) and the AI gives you a polished answer about nothing in particular.

That's not an intelligence problem. It's an access problem.

AI models today are like a brilliant new hire on their first day. They want to help, but they don't have the login to your systems. They can't pull your data or check what your customers are saying on Google. They're locked out of the world they need to work in.

So I built a bridge.

## What is an MCP server?

MCP, the Model Context Protocol, is an open standard that lets AI models use custom tools. Think of it like giving your AI assistant a set of specialized apps on its phone. One app looks up Google Reviews. Another queries your database. A third pulls data from your CRM.

Here's how it works:

1. You define tools: functions with clear inputs and outputs, like "given a company URL, find all its Google Maps locations"
2. You wrap them in a small server, a lightweight web service that speaks MCP
3. Any compatible AI client (Claude, Cursor, or your own application) discovers the tools and calls them as needed

The AI decides *when* to use a tool based on the conversation. You give it capabilities, and it applies them when they're relevant.

Say you run a business with locations in several cities. Keeping a pulse on customer sentiment is a headache. Google Reviews are scattered across dozens of listings. Most AI models, when asked "what are the reviews like for our locations?", will pull up maybe five recent ones from a single listing and call it a day. That's not useful when you're trying to spot patterns across ten or twenty sites.

With the right tool, you can ask your AI to "pull the reviews across all our locations and summarize the biggest complaints customers are having," and it actually can. It calls the search tool to find every location, fetches reviews sorted by rating, and gives you a useful summary instead of five reviews from one place.

## What I built

This project is an MCP server for Google Reviews. It lets AI agents look up and analyze reviews for any business. It can:

- Find all Google Maps listings for a company given its URL
- Fetch reviews sorted by best, worst, newest, or most relevant
- Generate an overview across all locations, with rating histograms when the data provider supplies them

A tool definition can be surprisingly short:

```python
@mcp.tool()
async def search_company_places(
    company_url: str,
    company_name: str | None = None,
) -> str:
    """Search for all Google Maps / Google Business
    locations associated with a company.

    Returns a formatted overview of discovered places
    including names, addresses, ratings, and review counts.
    """
```

This is one of the simpler tool definitions, but there's a lot packed into it. The AI doesn't just see the docstring. It receives the full schema: parameter names, types, descriptions, defaults. It uses all of that to decide which tool to call and how to fill in the arguments. You write a function with good annotations, and the AI figures out when and how to use it.

The function definition is the easy part.

## The engineering that makes it work

*This section gets into the implementation details. If you're more interested in the big picture, feel free to skip ahead to [the takeaway](#the-takeaway).*

Behind that clean function signature, there's a lot of messy work. And some scars.

**SerpAPI already ships an MCP server. This one still exists for a reason.** An agent could use the generic SerpAPI tools and do the whole job itself: call "search place," call "get reviews" for the best ratings, again for the worst, again for the newest, stitch the three lists together, repeat for every location. It works. But every one of those steps is another agent turn, another round of reasoning about what to call next, more tokens spent on the agent's own output, and another billed API call. When the workflow is predictable enough that you can write it down as a sentence ("the 20 best, 20 worst, and 20 newest reviews for every location of this company"), the agent shouldn't have to rediscover it from scratch every time. A single purpose-built tool that runs the whole sequence in one call, caches the results to the database as a side effect, and hands back a clean summary collapses dozens of agent turns into one. That is most of the reason this server exists.

**Two tool calls, eleven API calls.** I tested this against Madrona Bakery. The agent made two MCP calls: one to find the place, one for the overview. Inside the server that fanned out to eleven SerpAPI requests: the first domain search returned no match, so the server tried three query variants until one stuck, then pulled four different sort orders (best, worst, newest, most relevant) across two pages each. Eighty reviews, twelve seconds of wall clock, two turns from the agent's side. With a generic MCP the agent would have had to run all eleven of those steps itself: eleven turns, eleven rounds of reasoning about which call comes next, every intermediate response re-read into the context before the next decision. Just as important: none of those eleven raw API responses ever touched the agent's context window. The retries, the query fallbacks, the pagination noise, all of it stayed inside the server. The agent's context stays clean and open for what it's actually for: the conversation and the analysis.

**A skill is different from a tool.** The usual alternative to writing a server is to write a skill: a doc that teaches the agent how to use the raw API. That works. But the agent still executes every step. It still pays the turn cost, still burns tokens re-reading its own output between calls, still has to decide what to do when a search returns empty. A skill improves the agent's instructions. A tool removes the steps from the agent entirely. For any workflow you'll run more than a handful of times, removing the steps wins.

**The vendor I wanted to use didn't work.** When I started building this, I went with SearchAPI because it was significantly cheaper. That lasted until I noticed the same request would return different results on every call. I'd query reviews for a location, get nothing back, and have no way to know if the place genuinely had no reviews or if the API just failed silently. This happened often enough that I couldn't trust the data. So I switched to SerpAPI, which costs more but returns consistent results. The code is built so that if SearchAPI improves (or a cheaper alternative shows up), swapping back is a config change, not a rewrite.

**You don't want to pay for the same data twice.** Every API call costs money. If someone asks about the same company tomorrow, the server shouldn't have to hit the API again. So results are cached in PostgreSQL. Each batch of fetched data gets stored as a versioned snapshot. Same question twice, one API bill. (There's no automatic expiry yet — cached data is reused until it's refreshed manually, which is a fine tradeoff for reviews that change slowly.)

**Most of the time you don't need every review.** Each page of reviews from the API is a separate billable request, and a busy location might have hundreds of reviews. A subset of the best, worst, and newest usually tells you what you need to know. So there are two tools: one that gives a quick overview with a sensible default, and one that gives the AI full control over exactly how many reviews to fetch. The AI picks the right one depending on what you're asking for.

**APIs go down.** External services fail and hit rate limits. The system retries automatically with increasing wait times, so a temporary outage becomes a brief delay rather than a broken response.

## The takeaway

Google Reviews is just one example. The pattern works anywhere a human currently looks something up in a system.

Look at the most repetitive "lookup" tasks you or your team do. Order status. Availability checks. Review sentiment. Whatever it is, if a person is copying data from one system to answer a question in another, that's a candidate for an MCP tool.

Each of these follows the same architecture: define the tool, connect it to the data source, wrap it in an MCP server, let the AI call it when relevant.

Right now, the hard part isn't the AI itself. It's connecting it to the messy, fragmented systems where actual work happens. You don't need to rebuild your tech stack. One server with one or two tools is enough to prove the value. Build clean interfaces, cache results, abstract your vendors. The work compounds.

The Model Context Protocol is open and growing. You can explore the specification at [modelcontextprotocol.io](https://modelcontextprotocol.io).

I built this one because the generic MCP tools pushed too much of the workflow onto the agent. If you're working through the same problem in your own stack, I'd be glad to talk it through. The code is right here in this repo.
