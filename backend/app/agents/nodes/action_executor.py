from typing import Dict, Any
from app.agents.state import AgentState
from app.agents.tools import DatabaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import settings
import json
from datetime import datetime


class ActionExecutor:
    """Execute user actions based on natural language input"""
    
    def __init__(self, db_tool: DatabaseTool):
        self.db_tool = db_tool
        self.llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.1
        )
    
    async def __call__(self, state: AgentState) -> AgentState:
        """Process and execute user actions"""
        
        user_query = state['query']
        user_profile = state['user_profile']
        
        # Extract action intent and parameters
        action_data = await self._extract_action_data(user_query)
        
        result = None
        action_type = action_data.get('action_type')
        
        try:
            if action_type == 'log_trip':
                result = await self._log_trip(user_profile['user_id'], action_data.get('trip_data', {}))
            
            elif action_type == 'vehicle_check':
                result = await self._create_vehicle_check(user_profile['user_id'], action_data.get('check_data', {}))
            
            elif action_type == 'create_goal':
                result = await self._create_goal(user_profile['user_id'], action_data.get('goal_data', {}))
            
            elif action_type == 'update_goal':
                result = await self._update_goal(action_data.get('goal_id'), action_data.get('amount', 0))
            
            # Generate response
            response = await self._generate_response(user_query, action_type, result, action_data)
            
            state['response'] = response
            state['recommendations'] = result.get('recommendations', []) if result else []
            state['action_items'] = result.get('action_items', []) if result else []
            
        except Exception as e:
            state['response'] = f"I encountered an error while processing your request: {str(e)}"
            state['recommendations'] = []
            state['action_items'] = []
        
        return state
    
    async def _extract_action_data(self, query: str) -> Dict[str, Any]:
        """Extract action type and parameters from natural language"""
        
        system_prompt = """You are an AI that extracts structured action data from user queries.

Identify the action type and extract relevant parameters:

Action Types:
- log_trip: User wants to log a trip (e.g., "I completed a trip from Indiranagar to Whitefield for 450 rupees")
- vehicle_check: User reports vehicle issue (e.g., "My brake is making noise", "Engine light is on")
- create_goal: User wants to set a financial goal (e.g., "I want to save 50000 for a new phone")
- update_goal: User wants to update goal progress (e.g., "I saved 5000 towards my goal")
- query: Just asking for information (no action needed)

For log_trip, extract:
- start_location: pickup location
- end_location: drop location
- earnings: fare amount
- fuel_cost: fuel expense (optional)
- toll_cost: toll expense (optional)
- distance_km: distance (optional)
- platform: app used (Uber/Ola/etc, optional)

For vehicle_check, extract:
- issue_description: what's wrong
- severity: low/medium/high

For create_goal, extract:
- goal_name: name of goal
- target_amount: target amount
- target_date: deadline (optional)

For update_goal, extract:
- goal_id: which goal (if mentioned)
- amount: amount to add

Return ONLY a valid JSON object with this structure:
{
    "action_type": "log_trip|vehicle_check|create_goal|update_goal|query",
    "trip_data": {...},
    "check_data": {...},
    "goal_data": {...},
    "goal_id": null,
    "amount": 0
}"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"User query: {query}")
        ]
        
        response = await self.llm.ainvoke(messages)
        
        try:
            # Extract JSON from response
            content = response.content.strip()
            if content.startswith('```json'):
                content = content[7:]
            if content.endswith('```'):
                content = content[:-3]
            
            return json.loads(content.strip())
        except:
            return {'action_type': 'query'}
    
    async def _log_trip(self, user_id: int, trip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Log a trip"""
        
        # Set defaults
        if 'start_time' not in trip_data:
            trip_data['start_time'] = datetime.now()
        if 'fuel_cost' not in trip_data:
            trip_data['fuel_cost'] = 0
        if 'toll_cost' not in trip_data:
            trip_data['toll_cost'] = 0
        if 'other_expenses' not in trip_data:
            trip_data['other_expenses'] = 0
        
        result = await self.db_tool.create_trip(user_id, trip_data)
        
        return {
            **result,
            'recommendations': [
                f"Trip logged successfully! Net earnings: ₹{result.get('net_earnings', 0):.2f}"
            ],
            'action_items': [
                "Your trip has been recorded in your earnings history"
            ]
        }
    
    async def _create_vehicle_check(self, user_id: int, check_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create vehicle health check"""
        
        # Determine severity
        severity_map = {'low': 3, 'medium': 5, 'high': 8}
        severity = check_data.get('severity', 'medium')
        
        check_data['check_type'] = 'ai_diagnosis'
        check_data['severity_score'] = severity_map.get(severity, 5)
        check_data['immediate_action_required'] = severity == 'high'
        
        # Generate recommendations based on issue
        issue = check_data.get('issue_description', '')
        recommendations = []
        
        if 'brake' in issue.lower():
            recommendations = [
                "Get brake pads checked immediately",
                "Don't ignore brake noises - safety first",
                "Estimated cost: ₹800-1500"
            ]
        elif 'engine' in issue.lower() or 'light' in issue.lower():
            recommendations = [
                "Get OBD scan done at nearest service center",
                "Could be minor sensor issue or major problem",
                "Don't delay - could affect fuel efficiency"
            ]
        else:
            recommendations = [
                "Schedule a vehicle inspection soon",
                "Document any unusual sounds or performance issues"
            ]
        
        check_data['recommendations'] = recommendations
        
        result = await self.db_tool.create_vehicle_check(user_id, check_data)
        
        return {
            **result,
            'action_items': [
                "Vehicle health check recorded",
                "Consider scheduling service if issues persist"
            ]
        }
    
    async def _create_goal(self, user_id: int, goal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new financial goal"""
        
        goal_data['current_amount'] = 0
        goal_data['percentage_complete'] = 0
        goal_data['status'] = 'in_progress'
        
        result = await self.db_tool.create_goal(user_id, goal_data)
        
        return {
            **result,
            'recommendations': [
                f"Goal '{result['goal_name']}' created!",
                f"Target: ₹{result['target_amount']:,.0f}",
                "Start saving regularly to reach your goal"
            ],
            'action_items': [
                "Track your progress regularly",
                "Set aside a fixed amount from each trip"
            ]
        }
    
    async def _update_goal(self, goal_id: int, amount: float) -> Dict[str, Any]:
        """Update goal progress"""
        
        result = await self.db_tool.update_goal_progress(goal_id, amount)
        
        return {
            **result,
            'recommendations': [
                f"Added ₹{amount} to '{result['goal_name']}'",
                f"Progress: {result['percentage_complete']:.1f}%",
                f"Current: ₹{result['current_amount']:,.0f}"
            ],
            'action_items': [
                "Keep saving consistently",
                f"Goal status: {result['status']}"
            ]
        }
    
    async def _generate_response(
        self,
        query: str,
        action_type: str,
        result: Dict[str, Any],
        action_data: Dict[str, Any]
    ) -> str:
        """Generate natural language response"""
        
        system_prompt = """You are Sarathi, a friendly AI companion for drivers in India.

Generate a warm, encouraging response based on the action performed.
Use Indian context, rupees, and friendly tone.
Keep it conversational and helpful."""

        context = f"""
User query: {query}
Action performed: {action_type}
Result: {json.dumps(result, default=str)}
"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=context)
        ]
        
        response = await self.llm.ainvoke(messages)
        return response.content
