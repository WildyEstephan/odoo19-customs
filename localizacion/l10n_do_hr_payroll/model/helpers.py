
from odoo import api
import datetime


@api.model
def get_years():
    """
    Generate a list of years from to actual
    """
    years_list = []
    year_start = datetime.date(2016, 1, 1)
    actual_year = datetime.date.today()
    for i in range(actual_year.year - year_start.year + 1):
        year_id = year_label = str(year_start.year + i)
        years_list.append((year_id, year_label))
    years_list.reverse()
    return years_list
