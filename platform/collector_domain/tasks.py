from celery import shared_task
from django.db import transaction

from collector_domain.managers import AgentManager


@shared_task
def agent_status_checker():
    agents = AgentManager.get_all_agents()

    with transaction.atomic():
        for agent in agents.select_for_update():
            agent_manager = AgentManager(agent.id)
            agent_status = agent_manager.get_agent_status()

            if not agent_manager.check_agent_status() and agent_status == agent_manager.AgentStatus.ACTIVE:
                AgentManager.deactivate_agent(agent.id)
