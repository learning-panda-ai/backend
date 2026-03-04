import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class UploadedFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    s3_url: str
    content_type: str
    board: str
    standard: str
    subject: str
    state: str
    ingest_status: str
    celery_task_id: str | None = None
    uploaded_at: datetime
    ingested_at: datetime | None = None


class State(str, Enum):
    # States
    ANDHRA_PRADESH = "Andhra Pradesh"
    ARUNACHAL_PRADESH = "Arunachal Pradesh"
    ASSAM = "Assam"
    BIHAR = "Bihar"
    CHHATTISGARH = "Chhattisgarh"
    GOA = "Goa"
    GUJARAT = "Gujarat"
    HARYANA = "Haryana"
    HIMACHAL_PRADESH = "Himachal Pradesh"
    JHARKHAND = "Jharkhand"
    KARNATAKA = "Karnataka"
    KERALA = "Kerala"
    MADHYA_PRADESH = "Madhya Pradesh"
    MAHARASHTRA = "Maharashtra"
    MANIPUR = "Manipur"
    MEGHALAYA = "Meghalaya"
    MIZORAM = "Mizoram"
    NAGALAND = "Nagaland"
    ODISHA = "Odisha"
    PUNJAB = "Punjab"
    RAJASTHAN = "Rajasthan"
    SIKKIM = "Sikkim"
    TAMIL_NADU = "Tamil Nadu"
    TELANGANA = "Telangana"
    TRIPURA = "Tripura"
    UTTAR_PRADESH = "Uttar Pradesh"
    UTTARAKHAND = "Uttarakhand"
    WEST_BENGAL = "West Bengal"
    # Union Territories
    DELHI = "Delhi"
    JAMMU_AND_KASHMIR = "Jammu & Kashmir"
    LADAKH = "Ladakh"
    CHANDIGARH = "Chandigarh"
    PUDUCHERRY = "Puducherry"
    ANDAMAN_AND_NICOBAR = "Andaman & Nicobar Islands"
    DADRA_AND_NAGAR_HAVELI = "Dadra & Nagar Haveli"
    LAKSHADWEEP = "Lakshadweep"


class Board(str, Enum):
    CBSE = "CBSE"
    ICSE = "ICSE"
    IGCSE = "IGCSE"
    IB = "IB"
    STATE_BOARD = "State Board"


class Standard(str, Enum):
    CLASS_1 = "Class 1"
    CLASS_2 = "Class 2"
    CLASS_3 = "Class 3"
    CLASS_4 = "Class 4"
    CLASS_5 = "Class 5"
    CLASS_6 = "Class 6"
    CLASS_7 = "Class 7"
    CLASS_8 = "Class 8"
    CLASS_9 = "Class 9"
    CLASS_10 = "Class 10"
    CLASS_11 = "Class 11"
    CLASS_12 = "Class 12"


class Subject(str, Enum):
    MATHEMATICS = "Mathematics"
    SCIENCE = "Science"
    PHYSICS = "Physics"
    CHEMISTRY = "Chemistry"
    BIOLOGY = "Biology"
    ENGLISH = "English"
    HINDI = "Hindi"
    HISTORY = "History"
    GEOGRAPHY = "Geography"
    COMPUTER_SCIENCE = "Computer Science"
    ECONOMICS = "Economics"
    ACCOUNTANCY = "Accountancy"
    BUSINESS_STUDIES = "Business Studies"
    POLITICAL_SCIENCE = "Political Science"
    SOCIOLOGY = "Sociology"
    PSYCHOLOGY = "Psychology"
