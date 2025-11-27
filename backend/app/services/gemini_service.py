import google.generativeai as genai
from app.config import settings
from typing import Optional, List, Dict, Any
import base64
import logging
import re
from PIL import Image
import io

# Configure Gemini
genai.configure(api_key=settings.GOOGLE_API_KEY)


class GeminiService:
    """Service for interacting with Google Gemini AI"""
    
    def __init__(self):
        self.model = genai.GenerativeModel(settings.GEMINI_MODEL)
        self.chat_model = genai.GenerativeModel(
            settings.GEMINI_MODEL,
            generation_config={
                "temperature": 0.7,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 2048,
            }
        )
    
    async def transcribe_audio(self, audio_data: bytes) -> str:
        """Transcribe audio to text using Gemini"""
        try:
            logger = logging.getLogger(__name__)
            logger.info("Transcribing audio of size %d", len(audio_data) if audio_data else 0)
            # Gemini supports audio transcription
            response = self.model.generate_content([
                "Transcribe this audio message. The speaker is a ride-hailing or delivery driver reporting their trip details. Extract: start location, end location, earnings, expenses, and any other relevant trip information.",
                {"mime_type": "audio/wav", "data": audio_data}
            ])
            logger.info("Transcription response received. Length=%d", len(response.text) if response and response.text else 0)
            return response.text
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.exception("Audio transcription failed: %s", str(e))
            raise Exception(f"Audio transcription failed: {str(e)}")
    
    async def analyze_vehicle_images(
        self, 
        images: List[bytes],
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Analyze vehicle condition from images using Gemini Vision"""
        try:
            prompt = """You are an expert vehicle diagnostic AI. Analyze these vehicle images and provide a detailed health assessment.

Focus on:
1. Tire condition (tread depth, wear patterns, damage)
2. Engine oil level and color (if visible)
3. Brake components condition
4. Body damage (dents, scratches, rust)
5. Battery condition (if visible)
6. Any other visible issues

Provide your response in JSON format with:
{
    "overall_health": "good/fair/poor/critical",
    "severity_score": 0-100,
    "detected_issues": [
        {
            "component": "tire_front_left",
            "condition": "poor",
            "issue": "Worn tread, requires replacement",
            "severity": "high"
        }
    ],
    "tire_condition": "good/fair/poor/critical",
    "engine_oil_level": "good/low/critical",
    "brake_condition": "good/fair/poor",
    "battery_health": "good/fair/poor",
    "body_damage": "none/minor/moderate/severe",
    "immediate_action_required": true/false,
    "recommendations": [
        "Replace front left tire immediately",
        "Check engine oil level"
    ],
    "estimated_cost_range": "₹500-1000",
    "next_check_in_days": 7
}"""
            
            if context:
                prompt += f"\n\nAdditional context: {context}"
            
            # Prepare image parts
            image_parts = []
            for img_bytes in images:
                img = Image.open(io.BytesIO(img_bytes))
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Resize if too large
                max_size = 1024
                if max(img.size) > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                
                # Convert back to bytes
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG')
                img_byte_arr = img_byte_arr.getvalue()
                
                image_parts.append({
                    "mime_type": "image/jpeg",
                    "data": img_byte_arr
                })
            
            # Generate analysis
            content = [prompt] + image_parts
            response = self.model.generate_content(content)
            
            # Parse JSON response
            import json
            result = json.loads(response.text.strip().replace('```json', '').replace('```', ''))
            
            return result
        except Exception as e:
            raise Exception(f"Vehicle image analysis failed: {str(e)}")
    
    async def extract_trip_info(self, transcription: str) -> Dict[str, Any]:
        """Extract structured trip information from transcription"""
        try:
            prompt = f"""Extract trip information from this transcription: "{transcription}"

Extract and provide in JSON format:
{{
    "start_location": "location name",
    "end_location": "location name",
    "earnings": 0.0,
    "fuel_cost": 0.0,
    "toll_cost": 0.0,
    "other_expenses": 0.0,
    "platform": "uber/ola/swiggy/zomato/other",
    "trip_type": "ride_hailing/delivery/other",
    "notes": "any additional information"
}}

If any field is not mentioned, use reasonable defaults or 0.0 for numbers."""
            
            response = self.chat_model.generate_content(prompt)
            import json
            response_text = response.text.strip()
            # Try direct JSON parsing
            try:
                result = json.loads(response_text.replace('```json', '').replace('```', ''))
                # Normalize numeric fields
                for num_field in ['earnings', 'fuel_cost', 'toll_cost', 'other_expenses']:
                    if num_field in result:
                        try:
                            result[num_field] = float(result[num_field]) if result[num_field] is not None else 0.0
                        except Exception:
                            result[num_field] = 0.0
                return result
            except Exception:
                # Attempt to find a JSON block inside the text
                json_match = re.search(r"\{[\s\S]*\}", response_text)
                if json_match:
                    try:
                        result = json.loads(json_match.group(0))
                        for num_field in ['earnings', 'fuel_cost', 'toll_cost', 'other_expenses']:
                            if num_field in result:
                                try:
                                    result[num_field] = float(result[num_field]) if result[num_field] is not None else 0.0
                                except Exception:
                                    result[num_field] = 0.0
                        return result
                    except Exception:
                        pass
                # Fallback: log and return sensible default
                logger = logging.getLogger(__name__)
                logger.warning("Failed to parse JSON from Gemini extract_trip_info output: %s", response_text)
                return {
                    'start_location': None,
                    'end_location': None,
                    'earnings': 0.0,
                    'fuel_cost': 0.0,
                    'toll_cost': 0.0,
                    'other_expenses': 0.0,
                    'platform': None,
                    'trip_type': 'ride_hailing',
                    'notes': ''
                }
        except Exception as e:
            raise Exception(f"Trip info extraction failed: {str(e)}")
    
    async def analyze_earnings_pattern(
        self, 
        trip_history: List[Dict[str, Any]],
        user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze earnings patterns and provide insights"""
        try:
            prompt = f"""Analyze this driver's earnings pattern and provide actionable insights.

Trip History Summary:
{trip_history}

User Context:
{user_context}

Provide analysis in JSON format:
{{
    "total_earnings": 0.0,
    "average_earnings_per_trip": 0.0,
    "best_earning_hours": ["time slots"],
    "best_earning_zones": ["zone names"],
    "low_performance_periods": ["periods"],
    "recommendations": ["actionable recommendations"],
    "predicted_monthly_income": 0.0,
    "improvement_potential": "percentage or amount"
}}"""
            
            response = self.chat_model.generate_content(prompt)
            
            import json
            result = json.loads(response.text.strip().replace('```json', '').replace('```', ''))
            
            return result
        except Exception as e:
            raise Exception(f"Earnings pattern analysis failed: {str(e)}")
    
    async def detect_fatigue(
        self, 
        work_pattern: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Detect worker fatigue from work patterns"""
        try:
            prompt = f"""Analyze this work pattern to detect fatigue and burnout risk:

{work_pattern}

Provide analysis in JSON format:
{{
    "fatigue_level": "low/moderate/high/critical",
    "risk_score": 0-100,
    "warning_signs": ["list of detected warning signs"],
    "recommendations": ["rest recommendations"],
    "suggested_break_duration": "hours",
    "health_tips": ["tips for recovery"]
}}"""
            
            response = self.chat_model.generate_content(prompt)
            
            import json
            result = json.loads(response.text.strip().replace('```json', '').replace('```', ''))
            
            return result
        except Exception as e:
            raise Exception(f"Fatigue detection failed: {str(e)}")
    
    async def generate_financial_plan(
        self,
        user_profile: Dict[str, Any],
        goals: List[Dict[str, Any]],
        current_finances: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate personalized financial plan"""
        try:
            prompt = f"""Create a personalized financial plan for this user:

User Profile:
{user_profile}

Financial Goals:
{goals}

Current Financial Situation:
{current_finances}

Provide a comprehensive plan in JSON format:
{{
    "monthly_budget": {{
        "income": 0.0,
        "essential_expenses": 0.0,
        "savings": 0.0,
        "investments": 0.0,
        "discretionary": 0.0
    }},
    "goal_allocation": [
        {{
            "goal_name": "name",
            "monthly_amount": 0.0,
            "priority": "high/medium/low"
        }}
    ],
    "investment_recommendations": ["recommendations"],
    "action_steps": ["ordered list of steps"],
    "timeline": "estimated time to achieve goals",
    "risk_assessment": "analysis of financial risks"
}}"""
            
            response = self.chat_model.generate_content(prompt)
            
            import json
            result = json.loads(response.text.strip().replace('```json', '').replace('```', ''))
            
            return result
        except Exception as e:
            raise Exception(f"Financial plan generation failed: {str(e)}")


# Singleton instance
gemini_service = GeminiService()
