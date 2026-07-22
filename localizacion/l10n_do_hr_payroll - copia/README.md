Odoo - HR Payroll
=================
#ToDo
- **HR Contract and Salary Rule**
   -  Add Type Of Incomes with name TINGRESO, will be a selections, after hr.contract.type_id:
      DONE
        
   - Add "Payroll Key" related one2many payrollkeys after hr.contract.TINGRESO: 
      DONE

   - Add a Page on the NoteBook after Salary Information, name **Frequency** this will add a new discount or new gross to an employee by an amount or by dues, it will search on so the contract can have many2many contrac_news_ids 
        - Salary Rule: On Salary Rule will should add this:
           - is_news an bool.
           - If is_news is True appear should appear a selection:
            - Type of News Should Be A Model:
                - value = IN, string = Gross
                - value = SA, string = Leave
                - value = VC, string = Vacations
                - value = LM, string = Maternity License
                - value = LV, string = Voluntary License
                - value = LD, string = Disability License 
                - value = AD, Employee Update Data.
        - This will have the following field
            - is_active.bool
            - Description.char
            - Selection Salary Rules IDS, just with is_news = true.
            - amount.float
            - is_dues, once this is true it will show:
                - dues.integer 
                "This mean the amount will add to the salary selected the time on every payslips"
                - dues_remaining.integer. 
                "This reaming subtracting the dues, so if Amount set to 4, this mean the amount will add to the salary selected, so in the next payslips will remean"         
            - is_subsidy is this true will show:
               - subsidy_amount
               -  subsidy_account_id one2many to account_account.
               
             Can't have a dues and subside on the same times.
    - Add On Contract Detail after schedule_pay.
        - schedule_withholding selection with:
          DONE
        - withholding_partner.bool is true:
            - Show a withholding_partner_id one2many contacts
        - remuneracion.float. will show on withholding_partner is true.

- **Salary Rule**
           