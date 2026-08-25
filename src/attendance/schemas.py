from datetime import date

from pydantic import BaseModel


class AnnualLeave(BaseModel):
    joining_date: date
    new_fiscal_year_start_date: date | None = None

class EmployeeFiscalYear(BaseModel):
    employee: object
    fiscal_year_start_date: date
    fiscal_year_end_date: date