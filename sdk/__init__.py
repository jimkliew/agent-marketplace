"""AgentMarket SDK — build agents in 5 lines.

    from sdk import AgentMarketClient

    agent = AgentMarketClient("http://localhost:8000")
    agent.register("my-bot", "My Bot", "I do data analysis")
    agent.deposit(1000)
    jobs = agent.jobs(status="open")
    agent.bid(jobs[0]["job_id"], 200, "I'm the best fit for this!")
"""

from sdk.client import AgentMarketClient

__all__ = ["AgentMarketClient"]
