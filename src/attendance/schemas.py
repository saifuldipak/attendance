from pydantic import BaseModel
from datetime import date
from typing import Optional

class AnnualLeave(BaseModel):
    joining_date: date
    new_fiscal_year_start_date: Optional[date] = None