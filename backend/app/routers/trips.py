from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from datetime import datetime, timedelta
from app.database import get_db
from app.models.user import User
from app.models.trip import Trip
from app.auth import get_current_active_user
from app.schemas.trip import (
    TripCreate, TripResponse, TripUpdate, TripVoiceCreate,
    TripStats, ZoneRecommendation
)
from app.services import gemini_service, google_maps_service, whatsapp_service
import logging
import aiofiles
import os
from app.config import settings

router = APIRouter(prefix="/trips", tags=["Trips"])


@router.post("", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
async def create_trip(
    trip_data: TripCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new trip"""
    
    # Geocode if coordinates not provided
    if not trip_data.start_lat or not trip_data.start_lng:
        coords = google_maps_service.geocode_address(trip_data.start_location)
        if coords:
            trip_data.start_lat, trip_data.start_lng = coords
    
    if not trip_data.end_lat or not trip_data.end_lng:
        coords = google_maps_service.geocode_address(trip_data.end_location)
        if coords:
            trip_data.end_lat, trip_data.end_lng = coords
    
    # Calculate distance if not provided
    if not trip_data.distance_km and trip_data.start_lat and trip_data.end_lat:
        distance_info = google_maps_service.calculate_distance(
            (trip_data.start_lat, trip_data.start_lng),
            (trip_data.end_lat, trip_data.end_lng)
        )
        if distance_info:
            trip_data.distance_km = distance_info['distance_km']
    
    # Calculate duration
    duration_minutes = None
    if trip_data.end_time:
        duration_minutes = (trip_data.end_time - trip_data.start_time).total_seconds() / 60
    
    # Calculate net earnings
    total_expenses = trip_data.fuel_cost + trip_data.toll_cost + trip_data.other_expenses
    net_earnings = trip_data.earnings - total_expenses
    
    # Create trip
    new_trip = Trip(
        user_id=current_user.id,
        **trip_data.model_dump(),
        duration_minutes=duration_minutes,
        net_earnings=net_earnings
    )
    
    db.add(new_trip)
    await db.commit()
    await db.refresh(new_trip)
    
    return new_trip


@router.post("/voice", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
async def create_trip_from_voice(
    audio_file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create trip from voice message (WhatsApp integration)"""
    
    # Save audio file
    upload_dir = settings.UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
    
    # Use content type to infer extension
    mime = getattr(audio_file, 'content_type', None) or 'audio/wav'
    ext = 'wav'
    if 'm4a' in mime:
        ext = 'm4a'
    elif 'wav' in mime:
        ext = 'wav'
    elif 'mpeg' in mime or 'mp3' in mime:
        ext = 'mp3'

    file_path = os.path.join(upload_dir, f"voice_{current_user.id}_{datetime.now().timestamp()}.{ext}")
    
    async with aiofiles.open(file_path, 'wb') as f:
        content = await audio_file.read()
        await f.write(content)
    
    # Transcribe audio
    try:
        logger = logging.getLogger(__name__)
        logger.info("Received voice file: %s size=%d bytes", file_path, len(content) if content else 0)

        transcription = await gemini_service.transcribe_audio(content)
        logger.info("Transcription length=%d: %s", len(transcription) if transcription else 0, (transcription[:200] + '...' if transcription and len(transcription) > 200 else transcription))
        if not transcription or not transcription.strip():
            logger.warning("Transcription empty for file: %s", file_path)
            # Bad request if transcription is empty
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Audio transcription resulted in empty text. Please try again with clearer audio"
            )
        
        # Extract trip information
        trip_info = await gemini_service.extract_trip_info(transcription)
        logger.info("Extracted trip_info: %s", str(trip_info))
        if not trip_info or not isinstance(trip_info, dict):
            logger.warning("Trip extraction returned unexpected result: %s", str(trip_info))
            # Bad request - extraction invalid
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to extract trip info from transcription"
            )
        
        # Create trip
        trip_data = TripCreate(
            start_location=trip_info.get('start_location', 'Unknown'),
            end_location=trip_info.get('end_location', 'Unknown'),
            start_time=datetime.now() - timedelta(hours=1),
            earnings=trip_info.get('earnings', 0),
            fuel_cost=trip_info.get('fuel_cost', 0),
            toll_cost=trip_info.get('toll_cost', 0),
            other_expenses=trip_info.get('other_expenses', 0),
            platform=trip_info.get('platform'),
            trip_type=trip_info.get('trip_type', 'ride_hailing')
        )
        
        # Geocode locations
        start_coords = google_maps_service.geocode_address(trip_data.start_location)
        end_coords = google_maps_service.geocode_address(trip_data.end_location)
        
        if start_coords:
            trip_data.start_lat, trip_data.start_lng = start_coords
        if end_coords:
            trip_data.end_lat, trip_data.end_lng = end_coords
        
        # Calculate distance
        if start_coords and end_coords:
            distance_info = google_maps_service.calculate_distance(start_coords, end_coords)
            if distance_info:
                trip_data.distance_km = distance_info['distance_km']
        
        net_earnings = trip_data.earnings - (trip_data.fuel_cost + trip_data.toll_cost + trip_data.other_expenses)
        
        new_trip = Trip(
            user_id=current_user.id,
            **trip_data.model_dump(),
            voice_message_url=file_path,
            transcription=transcription,
            net_earnings=net_earnings,
            end_time=datetime.now()
        )
        
        db.add(new_trip)
        await db.commit()
        await db.refresh(new_trip)
        
        return new_trip
        
    except Exception as e:
        # If it's an HTTPException, re-raise to be returned as is
        from fastapi import HTTPException as FastAPIHTTPException
        if isinstance(e, FastAPIHTTPException):
            raise
        # Log full exception and stack trace
        logger = logging.getLogger(__name__)
        logger.exception("Voice processing failed for file %s: %s", file_path, str(e))

        # Attempt to cleanup the uploaded file if present
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info("Removed temporary file: %s", file_path)
        except Exception:
            logger.exception("Failed to remove temporary file: %s", file_path)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Voice processing failed: {str(e)}"
        )


@router.get("", response_model=List[TripResponse])
async def get_trips(
    skip: int = 0,
    limit: int = 50,
    days: Optional[int] = 30,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's trips"""
    
    query = select(Trip).filter(Trip.user_id == current_user.id)
    
    if days:
        start_date = datetime.now() - timedelta(days=days)
        query = query.filter(Trip.created_at >= start_date)
    
    query = query.order_by(Trip.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    trips = result.scalars().all()
    
    return trips


@router.get("/stats", response_model=TripStats)
async def get_trip_stats(
    days: int = 30,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get trip statistics"""
    
    start_date = datetime.now() - timedelta(days=days)
    
    result = await db.execute(
        select(
            func.count(Trip.id).label('total_trips'),
            func.sum(Trip.earnings).label('total_earnings'),
            func.sum(Trip.fuel_cost + Trip.toll_cost + Trip.other_expenses).label('total_expenses'),
            func.avg(Trip.earnings).label('avg_earnings'),
            func.count(Trip.id).filter(Trip.is_high_value_zone == True).label('high_value_trips')
        )
        .filter(Trip.user_id == current_user.id)
        .filter(Trip.created_at >= start_date)
    )
    
    stats = result.first()
    
    # Get best performing zone
    zone_result = await db.execute(
        select(Trip.end_location, func.avg(Trip.earnings).label('avg_earnings'))
        .filter(Trip.user_id == current_user.id)
        .filter(Trip.created_at >= start_date)
        .group_by(Trip.end_location)
        .order_by(func.avg(Trip.earnings).desc())
        .limit(1)
    )
    best_zone = zone_result.first()
    
    return {
        'total_trips': stats.total_trips or 0,
        'total_earnings': float(stats.total_earnings or 0),
        'total_expenses': float(stats.total_expenses or 0),
        'net_earnings': float(stats.total_earnings or 0) - float(stats.total_expenses or 0),
        'average_trip_earnings': float(stats.avg_earnings or 0),
        'high_value_trips': stats.high_value_trips or 0,
        'best_zone': best_zone[0] if best_zone else None,
        'best_time_slot': None  # Can be calculated with more analysis
    }


@router.get("/recommendations/zones", response_model=List[ZoneRecommendation])
async def get_zone_recommendations(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get high-demand zone recommendations"""
    
    # Get user's last trip location or use city center
    result = await db.execute(
        select(Trip)
        .filter(Trip.user_id == current_user.id)
        .order_by(Trip.created_at.desc())
        .limit(1)
    )
    last_trip = result.scalar_one_or_none()
    
    if last_trip and last_trip.end_lat and last_trip.end_lng:
        current_location = (last_trip.end_lat, last_trip.end_lng)
    else:
        # Default location based on city
        current_location = (12.9716, 77.5946)  # Bangalore
    
    # Get current time
    current_hour = datetime.now().hour
    if 5 <= current_hour < 12:
        time_of_day = "morning"
    elif 12 <= current_hour < 17:
        time_of_day = "afternoon"
    elif 17 <= current_hour < 22:
        time_of_day = "evening"
    else:
        time_of_day = "night"
    
    # Get zone recommendations
    zones = google_maps_service.suggest_high_demand_zones(
        current_location,
        current_user.city or "Bangalore",
        time_of_day
    )
    
    # Convert to response format
    recommendations = []
    for zone in zones:
        recommendations.append(ZoneRecommendation(
            zone_name=zone['zone_name'],
            latitude=zone['latitude'],
            longitude=zone['longitude'],
            expected_earnings=150.0,  # Base estimate
            confidence_score=min(zone.get('rating', 3) * 20, 100),
            reason=f"High demand area for {time_of_day}",
            best_time=time_of_day
        ))
    
    return recommendations


@router.get("/{trip_id}", response_model=TripResponse)
async def get_trip(
    trip_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific trip"""
    
    result = await db.execute(
        select(Trip).filter(Trip.id == trip_id, Trip.user_id == current_user.id)
    )
    trip = result.scalar_one_or_none()
    
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )
    
    return trip


@router.patch("/{trip_id}", response_model=TripResponse)
async def update_trip(
    trip_id: int,
    trip_update: TripUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update trip"""
    
    result = await db.execute(
        select(Trip).filter(Trip.id == trip_id, Trip.user_id == current_user.id)
    )
    trip = result.scalar_one_or_none()
    
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )
    
    update_data = trip_update.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(trip, field, value)
    
    # Recalculate net earnings if expenses updated
    if any(field in update_data for field in ['earnings', 'fuel_cost', 'toll_cost', 'other_expenses']):
        trip.net_earnings = trip.earnings - (trip.fuel_cost + trip.toll_cost + trip.other_expenses)
    
    # Recalculate duration if end_time updated
    if 'end_time' in update_data and trip.end_time:
        trip.duration_minutes = (trip.end_time - trip.start_time).total_seconds() / 60
    
    await db.commit()
    await db.refresh(trip)
    
    return trip


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(
    trip_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete trip"""
    
    result = await db.execute(
        select(Trip).filter(Trip.id == trip_id, Trip.user_id == current_user.id)
    )
    trip = result.scalar_one_or_none()
    
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )
    
    await db.delete(trip)
    await db.commit()
    
    return None
