from src.app.workflow.deep_agent import create_deep_agent


def create_workflow():
    agent = create_deep_agent(
        tools=[],
        system_prompt="You are a helpful AI assistant.",
    )
    return agent
