from langgraph.graph import StateGraph, END
from app.agents.state import AgentState
from app.agents.nodes.user_state_evaluator import UserStateEvaluator
from app.agents.nodes.earnings_advisor import EarningsAdvisor
from app.agents.nodes.diagnostic_agent import DiagnosticAgent
from app.agents.nodes.surplus_planner import SurplusPlanner
from app.agents.nodes.investment_advisor import InvestmentAdvisor
from app.agents.nodes.action_executor import ActionExecutor
from app.agents.tools import DatabaseTool, MapsTool, FinancialTool, ChromaTool
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any
from langchain_core.messages import AIMessage


class SarathiAgent:
    """Main Sarathi Agent orchestrating all nodes"""
    
    def __init__(self, db: AsyncSession):
        # Initialize tools
        self.db_tool = DatabaseTool(db)
        self.maps_tool = MapsTool()
        self.financial_tool = FinancialTool()
        self.chroma_tool = ChromaTool()
        
        # Initialize nodes
        self.evaluator = UserStateEvaluator(self.db_tool)
        self.action_executor = ActionExecutor(self.db_tool)
        self.earnings_advisor = EarningsAdvisor(
            self.db_tool,
            self.maps_tool,
            self.chroma_tool
        )
        self.diagnostic_agent = DiagnosticAgent(self.db_tool)
        self.surplus_planner = SurplusPlanner(
            self.db_tool,
            self.financial_tool
        )
        self.investment_advisor = InvestmentAdvisor(self.financial_tool)
        
        # Build graph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the agent execution graph"""
        
        # Create graph
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("evaluate", self.evaluator)
        workflow.add_node("action_executor", self.action_executor)
        workflow.add_node("earnings_advisor", self.earnings_advisor)
        workflow.add_node("diagnostic_agent", self.diagnostic_agent)
        workflow.add_node("surplus_planner", self.surplus_planner)
        workflow.add_node("investment_advisor", self.investment_advisor)
        workflow.add_node("general_response", self._general_response)
        
        # Set entry point
        workflow.set_entry_point("evaluate")
        
        # Add conditional edges from evaluator
        workflow.add_conditional_edges(
            "evaluate",
            self._route_query,
            {
                "action_executor": "action_executor",
                "earnings_advisor": "earnings_advisor",
                "diagnostic_agent": "diagnostic_agent",
                "surplus_planner": "surplus_planner",
                "general_response": "general_response"
            }
        )
        
        # Add edges from each node to END
        workflow.add_edge("action_executor", END)
        workflow.add_edge("earnings_advisor", END)
        workflow.add_edge("diagnostic_agent", END)
        workflow.add_edge("general_response", END)
        
        # Surplus planner flows to investment advisor
        workflow.add_edge("surplus_planner", "investment_advisor")
        workflow.add_edge("investment_advisor", END)
        
        return workflow.compile()
    
    def _route_query(self, state: AgentState) -> str:
        """Route query to appropriate node based on query type"""
        return state.get('next_step', 'general_response')
    
    async def _general_response(self, state: AgentState) -> AgentState:
        """Handle general queries"""
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import SystemMessage, HumanMessage
        from app.config import settings
        
        llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.7
        )
        
        system_prompt = """You are Sarathi, an AI companion for ride-hailing and delivery drivers in India.

You help drivers with:
1. Earnings optimization - Finding high-demand zones, maximizing income
2. Vehicle health - Maintenance reminders, diagnostic advice
3. Financial planning - Savings goals, investment recommendations

Be friendly, supportive, and provide practical advice. Keep responses concise."""
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=state['query'])
        ]
        
        try:
            response = await llm.ainvoke(messages)
            content = response.content
        except Exception as e:
            print(f"LLM General Response Error: {e}")
            content = "I apologize, but I'm having trouble connecting to my AI services right now. Please try again later."
        
        state['response'] = content
        state['messages'].append(AIMessage(content=content))
        state['next_step'] = 'end'
        
        return state
    
    async def process_query(
        self,
        user_id: int,
        query: str,
        user_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process user query through the agent graph"""
        
        # Initialize state
        initial_state: AgentState = {
            'user_id': user_id,
            'user_profile': user_profile,
            'query': query,
            'query_type': '',
            'messages': [],
            'trip_data': [],
            'vehicle_data': {},
            'financial_data': {},
            'map_data': {},
            'earnings_analysis': {},
            'vehicle_analysis': {},
            'financial_analysis': {},
            'recommendations': [],
            'response': '',
            'action_items': [],
            'next_step': '',
            'requires_human_input': False
        }
        
        # Run the graph
        final_state = await self.graph.ainvoke(initial_state)
        
        # Extract relevant output
        return {
            'response': final_state['response'],
            'recommendations': final_state['recommendations'],
            'action_items': final_state['action_items'],
            'query_type': final_state['query_type'],
            'earnings_analysis': final_state.get('earnings_analysis'),
            'vehicle_analysis': final_state.get('vehicle_analysis'),
            'financial_analysis': final_state.get('financial_analysis')
        }


async def create_sarathi_agent(db: AsyncSession) -> SarathiAgent:
    """Factory function to create Sarathi agent"""
    return SarathiAgent(db)
