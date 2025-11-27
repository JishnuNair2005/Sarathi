# Sarathi AI Agent - Natural Language Interface

The Sarathi AI agent now handles ALL operations through simple chat messages. Users don't need to navigate different routes - just chat naturally!

## Trip Logging

Instead of using `/trips` endpoint, users can simply chat:

**Examples:**
- "I just completed a trip from Indiranagar to Whitefield for 450 rupees"
- "Log my trip: picked up from MG Road, dropped at Koramangala, earned 320"
- "Completed delivery from Jayanagar to HSR, got 250 rupees, spent 40 on fuel"

**What happens:**
- AI extracts: pickup, dropoff, earnings, fuel cost
- Geocodes locations automatically
- Calculates distance and net earnings
- Stores trip in database
- Returns friendly confirmation

## Vehicle Health

Instead of `/vehicles/health-check`, users can chat:

**Examples:**
- "My brake is making a squeaking noise"
- "Engine light came on this morning"
- "Tire pressure seems low"
- "Check my vehicle health"

**What happens:**
- AI analyzes the issue
- Determines severity (low/medium/high)
- Generates specific recommendations
- Stores health check in database
- Provides cost estimates

## Financial Goals

Instead of `/goals` endpoint, users can chat:

**Examples:**
- "I want to save 50000 rupees for a new phone"
- "Set a goal to buy a bike for 80000"
- "I saved 5000 today towards my phone goal"
- "Update my savings goal with 2000"

**What happens:**
- AI creates/updates goal
- Tracks progress automatically
- Provides motivational feedback
- Suggests savings strategies

## Earnings Analysis

Users can ask questions:

**Examples:**
- "Where should I drive to earn more?"
- "What are the best zones right now?"
- "How much did I earn this week?"
- "Show me my trip statistics"

**What happens:**
- AI analyzes trip history
- Suggests high-demand zones
- Provides earnings insights
- Recommends optimal routes

## General Questions

The AI handles everything conversationally:

**Examples:**
- "Hello Sarathi, how are you?"
- "What's the weather like for driving?"
- "Should I work today or rest?"
- "Help me plan my day"

## Technical Implementation

All requests go through a single endpoint:

```
POST /agent/chat
{
    "query": "I completed a trip from Airport to Indiranagar for 650 rupees"
}
```

**Backend Flow:**
1. **UserStateEvaluator** - Classifies query type (action/earnings/vehicle/financial/general)
2. **ActionExecutor** - Handles action queries (creates trip/vehicle check/goal)
3. **Specialized Advisors** - Handle analysis queries (earnings/vehicle/financial)
4. **General Response** - Handles casual conversation

**Frontend:**
- Single chat interface
- No forms needed
- Voice input supported
- Natural conversation flow

## Benefits

✅ **Simplicity** - One chat interface for everything
✅ **Natural** - Talk like you're texting a friend
✅ **Voice-friendly** - Perfect for WhatsApp integration
✅ **Multilingual ready** - Works in Hindi, English, etc.
✅ **Context-aware** - Remembers user preferences
✅ **Smart extraction** - Pulls data from natural language
✅ **Automatic geocoding** - Converts locations to coordinates
✅ **Intelligent routing** - Sends to right handler automatically

## Example Conversation

```
User: "Hi Sarathi!"
AI: "Namaste! How can I help you today?"

User: "I just finished a trip from Whitefield to Electronic City, made 580 rupees"
AI: "Great job! I've logged your trip:
     • Route: Whitefield → Electronic City
     • Distance: ~18.5 km
     • Earnings: ₹580
     • Net earnings: ₹580 (no expenses recorded)
     
     Your trip has been added to your earnings history!"

User: "My brake is making noise"
AI: "I've recorded a vehicle health check for your brake issue. This requires immediate attention!
     
     Recommendations:
     • Get brake pads checked immediately
     • Don't ignore brake noises - safety first
     • Estimated cost: ₹800-1500
     
     Would you like me to find nearby service centers?"

User: "I want to save 30000 for Diwali"
AI: "Excellent! I've created a savings goal for you:
     • Goal: Diwali savings
     • Target: ₹30,000
     • Current: ₹0
     • Progress: 0%
     
     Based on your average earnings, I recommend saving ₹300-400 daily to reach your goal comfortably!"
```

## Migration from Old Routes

Old way:
```javascript
// Multiple API calls
await api.post('/trips', tripData);
await api.post('/vehicles/health-check', vehicleData);
await api.post('/goals', goalData);
```

New way:
```javascript
// Single chat interface
await api.post('/agent/chat', {
    query: "Completed trip from MG Road to Koramangala for 350"
});
```

The AI handles everything automatically! 🚀
