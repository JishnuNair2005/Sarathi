from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from app.models.trip import Trip
from app.models.vehicle import Vehicle, VehicleHealthCheck
from app.models.goal import Goal
from app.models.investment import Investment
from app.models.alert import Alert


class DatabaseTool:
    """Tool for querying database"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_trip_history(
        self,
        user_id: int,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get trip history for user"""
        start_date = datetime.now() - timedelta(days=days)
        
        result = await self.db.execute(
            select(Trip)
            .filter(Trip.user_id == user_id)
            .filter(Trip.created_at >= start_date)
            .order_by(Trip.created_at.desc())
        )
        
        trips = result.scalars().all()
        
        return [
            {
                'id': trip.id,
                'start_location': trip.start_location,
                'end_location': trip.end_location,
                'earnings': trip.earnings,
                'net_earnings': trip.net_earnings,
                'distance_km': trip.distance_km,
                'duration_minutes': trip.duration_minutes,
                'created_at': trip.created_at.isoformat(),
                'is_high_value_zone': trip.is_high_value_zone,
                'zone_rating': trip.zone_rating
            }
            for trip in trips
        ]
    
    async def get_trip_stats(
        self,
        user_id: int,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get aggregated trip statistics"""
        start_date = datetime.now() - timedelta(days=days)
        
        result = await self.db.execute(
            select(
                func.count(Trip.id).label('total_trips'),
                func.sum(Trip.earnings).label('total_earnings'),
                func.sum(Trip.fuel_cost + Trip.toll_cost + Trip.other_expenses).label('total_expenses'),
                func.avg(Trip.earnings).label('avg_earnings')
            )
            .filter(Trip.user_id == user_id)
            .filter(Trip.created_at >= start_date)
        )
        
        stats = result.first()
        
        return {
            'total_trips': stats.total_trips or 0,
            'total_earnings': float(stats.total_earnings or 0),
            'total_expenses': float(stats.total_expenses or 0),
            'avg_earnings': float(stats.avg_earnings or 0),
            'net_earnings': float(stats.total_earnings or 0) - float(stats.total_expenses or 0)
        }
    
    async def get_vehicle_info(self, user_id: int) -> Dict[str, Any]:
        """Get vehicle information"""
        result = await self.db.execute(
            select(Vehicle)
            .filter(Vehicle.user_id == user_id)
            .filter(Vehicle.is_active == True)
        )
        
        vehicle = result.scalar_one_or_none()
        
        if not vehicle:
            return {}
        
        return {
            'id': vehicle.id,
            'vehicle_number': vehicle.vehicle_number,
            'vehicle_type': vehicle.vehicle_type,
            'make': vehicle.make,
            'model': vehicle.model,
            'current_odometer_km': vehicle.current_odometer_km,
            'insurance_expiry': vehicle.insurance_expiry.isoformat() if vehicle.insurance_expiry else None,
            'last_service_date': vehicle.last_service_date.isoformat() if vehicle.last_service_date else None,
            'next_service_due_km': vehicle.next_service_due_km
        }
    
    async def get_latest_vehicle_check(self, user_id: int) -> Dict[str, Any]:
        """Get latest vehicle health check"""
        result = await self.db.execute(
            select(VehicleHealthCheck)
            .join(Vehicle)
            .filter(Vehicle.user_id == user_id)
            .order_by(VehicleHealthCheck.created_at.desc())
            .limit(1)
        )
        
        check = result.scalar_one_or_none()
        
        if not check:
            return {}
        
        return {
            'id': check.id,
            'check_type': check.check_type,
            'severity_score': check.severity_score,
            'tire_condition': check.tire_condition,
            'engine_oil_level': check.engine_oil_level,
            'brake_condition': check.brake_condition,
            'immediate_action_required': check.immediate_action_required,
            'recommendations': check.recommendations,
            'created_at': check.created_at.isoformat()
        }
    
    async def get_goals(self, user_id: int) -> List[Dict[str, Any]]:
        """Get user goals"""
        result = await self.db.execute(
            select(Goal)
            .filter(Goal.user_id == user_id)
            .filter(Goal.status.in_(['in_progress', 'completed']))
        )
        
        goals = result.scalars().all()
        
        return [
            {
                'id': goal.id,
                'goal_name': goal.goal_name,
                'target_amount': goal.target_amount,
                'current_amount': goal.current_amount,
                'completion_percentage': goal.percentage_complete,
                'target_date': goal.target_date.isoformat() if goal.target_date else None,
                'status': goal.status
            }
            for goal in goals
        ]
    
    async def get_investments(self, user_id: int) -> List[Dict[str, Any]]:
        """Get user investments"""
        result = await self.db.execute(
            select(Investment)
            .filter(Investment.user_id == user_id)
            .filter(Investment.status == 'active')
        )
        
        investments = result.scalars().all()
        
        return [
            {
                'id': inv.id,
                'investment_name': inv.investment_name,
                'investment_type': inv.investment_type,
                'current_value': inv.current_value,
                'invested_amount': inv.invested_amount,
                'returns_percentage': inv.returns_percentage,
                'risk_level': inv.risk_level
            }
            for inv in investments
        ]
    
    async def get_active_alerts(self, user_id: int) -> List[Dict[str, Any]]:
        """Get active alerts"""
        result = await self.db.execute(
            select(Alert)
            .filter(Alert.user_id == user_id)
            .filter(Alert.status == 'active')
            .order_by(Alert.created_at.desc())
            .limit(10)
        )
        
        alerts = result.scalars().all()
        
        return [
            {
                'id': alert.id,
                'alert_type': alert.alert_type,
                'title': alert.title,
                'message': alert.message,
                'priority': alert.priority,
                'created_at': alert.created_at.isoformat()
            }
            for alert in alerts
        ]
    
    async def create_trip(
        self,
        user_id: int,
        trip_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new trip"""
        from app.services import google_maps_service
        
        # Geocode if coordinates not provided
        if 'start_location' in trip_data and ('start_lat' not in trip_data or not trip_data.get('start_lat')):
            coords = google_maps_service.geocode_address(trip_data['start_location'])
            if coords:
                trip_data['start_lat'], trip_data['start_lng'] = coords
        
        if 'end_location' in trip_data and ('end_lat' not in trip_data or not trip_data.get('end_lat')):
            coords = google_maps_service.geocode_address(trip_data['end_location'])
            if coords:
                trip_data['end_lat'], trip_data['end_lng'] = coords
        
        # Calculate distance if not provided
        if 'distance_km' not in trip_data or not trip_data.get('distance_km'):
            if trip_data.get('start_lat') and trip_data.get('end_lat'):
                distance_info = google_maps_service.calculate_distance(
                    (trip_data['start_lat'], trip_data['start_lng']),
                    (trip_data['end_lat'], trip_data['end_lng'])
                )
                if distance_info:
                    trip_data['distance_km'] = distance_info['distance_km']
        
        # Calculate duration and net earnings
        duration_minutes = None
        if trip_data.get('end_time') and trip_data.get('start_time'):
            duration_minutes = (trip_data['end_time'] - trip_data['start_time']).total_seconds() / 60
        
        total_expenses = (
            trip_data.get('fuel_cost', 0) + 
            trip_data.get('toll_cost', 0) + 
            trip_data.get('other_expenses', 0)
        )
        net_earnings = trip_data.get('earnings', 0) - total_expenses
        
        # Create trip
        new_trip = Trip(
            user_id=user_id,
            duration_minutes=duration_minutes,
            net_earnings=net_earnings,
            **trip_data
        )
        
        self.db.add(new_trip)
        await self.db.commit()
        await self.db.refresh(new_trip)
        
        return {
            'id': new_trip.id,
            'start_location': new_trip.start_location,
            'end_location': new_trip.end_location,
            'earnings': new_trip.earnings,
            'net_earnings': new_trip.net_earnings,
            'distance_km': new_trip.distance_km,
            'created_at': new_trip.created_at.isoformat()
        }
    
    async def create_vehicle_check(
        self,
        user_id: int,
        check_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a vehicle health check"""
        # Get user's vehicle
        result = await self.db.execute(
            select(Vehicle)
            .filter(Vehicle.user_id == user_id)
            .filter(Vehicle.is_active == True)
        )
        vehicle = result.scalar_one_or_none()
        
        if not vehicle:
            raise ValueError("No active vehicle found for user")
        
        # Create health check
        new_check = VehicleHealthCheck(
            vehicle_id=vehicle.id,
            **check_data
        )
        
        self.db.add(new_check)
        await self.db.commit()
        await self.db.refresh(new_check)
        
        return {
            'id': new_check.id,
            'severity_score': new_check.severity_score,
            'recommendations': new_check.recommendations,
            'immediate_action_required': new_check.immediate_action_required,
            'created_at': new_check.created_at.isoformat()
        }
    
    async def create_goal(
        self,
        user_id: int,
        goal_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new goal"""
        new_goal = Goal(
            user_id=user_id,
            **goal_data
        )
        
        self.db.add(new_goal)
        await self.db.commit()
        await self.db.refresh(new_goal)
        
        return {
            'id': new_goal.id,
            'goal_name': new_goal.goal_name,
            'target_amount': new_goal.target_amount,
            'current_amount': new_goal.current_amount,
            'status': new_goal.status
        }
    
    async def update_goal_progress(
        self,
        goal_id: int,
        amount: float
    ) -> Dict[str, Any]:
        """Update goal progress"""
        result = await self.db.execute(
            select(Goal).filter(Goal.id == goal_id)
        )
        goal = result.scalar_one_or_none()
        
        if not goal:
            raise ValueError("Goal not found")
        
        goal.current_amount += amount
        goal.percentage_complete = (goal.current_amount / goal.target_amount) * 100
        
        if goal.percentage_complete >= 100:
            goal.status = 'completed'
        
        await self.db.commit()
        await self.db.refresh(goal)
        
        return {
            'id': goal.id,
            'goal_name': goal.goal_name,
            'current_amount': goal.current_amount,
            'percentage_complete': goal.percentage_complete,
            'status': goal.status
        }
