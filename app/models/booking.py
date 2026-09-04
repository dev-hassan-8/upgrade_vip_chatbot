from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EnquiryType(str, Enum):
    NONE = "none"
    AIRPORT_VIP = "airport_vip"
    AIRPORT_TRANSFER = "airport_transfer"


class EnquiryStatus(str, Enum):
    COLLECTING = "collecting"
    COMPLETE = "complete"


class AirportVipEnquiry(BaseModel):
    airport: str | None = None
    service_date: str | None = None
    service_time: str | None = None
    flight_number: str | None = None
    passenger_count: int | None = None
    luggage_details: str | None = None
    passenger_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    special_requirements: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class AirportTransferEnquiry(BaseModel):
    airport: str | None = None
    pickup_location: str | None = None
    dropoff_location: str | None = None
    service_date: str | None = None
    service_time: str | None = None
    flight_number: str | None = None
    passenger_count: int | None = None
    luggage_details: str | None = None
    passenger_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class EnquiryState(BaseModel):
    enquiry_type: EnquiryType = EnquiryType.NONE
    status: EnquiryStatus = EnquiryStatus.COLLECTING
    airport_vip: AirportVipEnquiry = Field(default_factory=AirportVipEnquiry)
    airport_transfer: AirportTransferEnquiry = Field(
        default_factory=AirportTransferEnquiry
    )
