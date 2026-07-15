# Building the bridges your AI needs

*How I built a custom Google Reviews tool for an AI agent, and what I learned from moving a repeated workflow into code.*

**Jonah Zander** | March 3, 2026

---

ChatGPT and Claude know a lot about the public internet. Ask either one about your own database, CRM, or Google Reviews, though, and the answer gets vague quickly.

The missing piece is access to the data.

I kept running into that gap while working with company reviews. The model could analyze the data once it had it, but getting the right reviews into the conversation took too many manual steps. I built an MCP server to handle that part.

## What is an MCP server?

MCP, the Model Context Protocol, is an open standard for giving AI clients access to custom tools. A tool might look up Google Reviews or query an internal database.

The setup is straightforward:

1. You define tools: functions with clear inputs and outputs, like "given a company URL, find all its Google Maps locations"
2. You wrap them in a small server, a lightweight web service that speaks MCP
3. A compatible client, such as Claude or Cursor, discovers the tools and calls them when needed

The client uses the tool descriptions and parameter schemas to decide when to call them.

Say a business has locations in several cities. Its Google Reviews are split across separate listings. A general web search might return five recent reviews from one location, which is not enough to compare complaints across the company.

With this server, I can ask an agent to sample reviews across the locations and summarize recurring complaints. The server finds matching places and fetches a bounded set of reviews in several sort orders. The agent receives the combined result.

## What I built

This MCP server gives an agent six tools for Google Reviews. Together they can:

- Find Google Maps listings that match a company URL
- Fetch reviews sorted by best, worst, newest, or most relevant
- Generate an overview across a configurable number of locations, with rating histograms when the data provider supplies them

A tool definition can be surprisingly short:

```python
@mcp.tool()
async def search_company_places(
    company_url: str,
    company_name: str | None = None,
) -> str:
    """Search for Google Maps / Google Business
    locations that match a company.

    Returns a formatted overview of discovered places
    including names, addresses, ratings, and review counts.
    """
```

The function is short, but the client receives more than its docstring. FastMCP generates a schema containing the parameter names, types, descriptions, and defaults. The agent uses that schema to choose a tool and fill in its arguments.

## The engineering that makes it work

*This section covers the implementation. [Skip to the takeaway](#the-takeaway) for the shorter version.*

The tool definition is small because the awkward parts live below it.

SerpAPI already ships an MCP server, so I could have stopped there. Its tools expose the individual operations: search for a place, fetch reviews, paginate, change the sort order, and repeat for another location. That works for an occasional query. For the same review workflow every time, it leaves the agent doing a lot of bookkeeping. I wanted one call that ran the sequence and returned the combined result.

I tested it against Madrona Bakery in 2026. The agent made two MCP calls: one to find the place and one to request the overview. The server made eleven SerpAPI requests. The first domain search found nothing, so it tried two more query variants, then fetched four sort orders across two pages each. The run returned eighty reviews in about twelve seconds. More importantly, the raw responses, failed search, and pagination data never entered the agent's context. Those numbers describe that test, not every request.

A skill was another option. I could have written instructions that taught the agent how to use the raw API. The agent would still execute each step, read each response back into context, and decide what to try after an empty search. A skill explains the sequence. This server executes it.

I started with SearchAPI because it was much cheaper. Then identical requests began returning different results. Sometimes a location came back with no reviews, and I could not tell whether that was true or whether the request had failed silently. It happened often enough that I stopped trusting the data. SerpAPI cost more but behaved consistently, so I switched. Both providers implement the same interface, which kept the change small.

Every provider request costs money, so the server stores results in PostgreSQL as versioned snapshots. A later request for the same company can use the cache if it already contains enough reviews. There is no automatic expiry yet. Cached reviews remain until I refresh them manually.

Fetching every review would be expensive and rarely useful. The overview defaults to three locations and twenty reviews per sort order. Separate place-level tools let the agent request a narrower sample when that is enough.

Provider requests can time out or hit rate limits. The server retries those failures with exponential backoff and jitter.

## The takeaway

Google Reviews gave me a concrete workflow to test: repeated lookups with predictable steps and paid requests along the way.

The same approach could fit other repeated lookups, such as checking an order or querying availability. The useful boundary is a task with stable steps that an agent would otherwise repeat by hand.

The architecture is small: typed tool definitions call a service, and the service talks to the data source.

The interesting part of this project was not getting a model to summarize reviews. It was deciding which steps belonged in the agent and which belonged in ordinary code. Search retries, pagination, provider quirks, and caching were easier to test once they lived in the server. The agent was left with the part it was good at: reading the result and answering the question.

The protocol specification is available at [modelcontextprotocol.io](https://modelcontextprotocol.io).
