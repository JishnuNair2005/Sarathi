from typing import Dict, Any
from app.agents.state import AgentState
from app.agents.tools import DatabaseTool, MapsTool, FinancialTool, ChromaTool
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from app.config import settings


class UserStateEvaluator:
    """Node that evaluates user state and determines query type"""
    
    def __init__(self, db_tool: DatabaseTool):
        self.db_tool = db_tool
        self.llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.3
        )
    
    async def __call__(self, state: AgentState) -> AgentState:
        """Evaluate user state and categorize query"""
        
        # Gather user context
        trip_stats = await self.db_tool.get_trip_stats(state['user_id'], days=7)
        vehicle_info = await self.db_tool.get_vehicle_info(state['user_id'])
        goals = await self.db_tool.get_goals(state['user_id'])
        alerts = await self.db_tool.get_active_alerts(state['user_id'])
        
        # Update state with context
        state['trip_data'] = [trip_stats]
        state['vehicle_data'] = vehicle_info
        state['financial_data'] = {'goals': goals}
        
        # Classify query type using LLM
        classification_prompt = f"""Classify this user query into one of these categories:
- action: User wants to perform an action (log trip, report vehicle issue, create goal, etc.)
  Examples: "I completed a trip", "My brake is making noise", "I want to save for a bike"
- earnings: Questions about income, trips, high-value zones
- vehicle: Questions about vehicle health, maintenance
- financial: Questions about savings, investments, goals
- general: General questions or greetings

User query: {state['query']}

Respond with just the category name."""
        
        messages = [
            SystemMessage(content="You are a query classifier for a driver assistance app."),
            HumanMessage(content=classification_prompt)
        ]
        
        try:
            response = await self.llm.ainvoke(messages)
            query_type = response.content.strip().lower()
        except Exception as e:
            print(f"LLM Classification Error: {e}")
            # Fallback to general if LLM fails
            query_type = 'general'
        
        if query_type not in ['action', 'earnings', 'vehicle', 'financial', 'general']:
            query_type = 'general'
        
        state['query_type'] = query_type
        state['messages'].append(HumanMessage(content=state['query']))
        
        # Determine next step
        if query_type == 'action':
            state['next_step'] = 'action_executor'
        elif query_type == 'earnings':
            state['next_step'] = 'earnings_advisor'
        elif query_type == 'vehicle':
            state['next_step'] = 'diagnostic_agent'
        elif query_type == 'financial':
            state['next_step'] = 'surplus_planner'
        else:
            state['next_step'] = 'general_response'
        
        return state
