import pandas as pd

att = pd.read_csv("attendance_logs.csv", parse_dates=["timestamp"])
employees = pd.read_csv("employees.csv")
print("Employees columns before split:", employees.columns)

# if the single column name is not 'raw', replace it below
employees_split = employees.iloc[:, 0].str.split(',', expand=True)
employees_split.columns = [
    'employee_id', 'emp_name', 'hire_date', 'termination_date',
    'department_id', 'job_role', 'payroll_grade', 'shift_id'
]
employees = employees_split
print("Employees columns after split:", employees.columns)

# ---- SHIFTS: split single column ----
shifts = pd.read_csv("shifts.csv")
print("Shifts columns before split:", shifts.columns)

shifts_split = shifts.iloc[:, 0].str.split(',', expand=True)
shifts_split.columns = [
    'shift_id', 'shift_name', 'start_time', 'end_time', 'standard_hours_per_day'
]
shifts = shifts_split
print("Shifts columns after split:", shifts.columns)

leaves = pd.read_csv(
    "leave_records.csv",
    parse_dates=["leave_start_date", "leave_end_date"]
)

departments = pd.read_csv("departments.csv")
payroll = pd.read_csv("payroll.csv")

print("All files loaded successfully!")

att = pd.read_csv("attendance_logs.csv")

# 1) AFTER LOADING FILES
att = pd.read_csv("attendance_logs.csv")
att['timestamp'] = pd.to_datetime(att['timestamp'], errors='coerce')

print("Employees columns:", employees.columns)
print("Shifts columns:", shifts.columns)

# -----------------------------
# 2) CLEAN ATTENDANCE LOGS
# -----------------------------
print("1. Cleaning attendance logs...")
att['event_type'] = att['event_type'].str.upper().str.strip()
att['date'] = att['timestamp'].dt.date

# first IN per employee/day
ins = (
    att[att['event_type'] == 'IN']
    .sort_values(['employee_id', 'timestamp'])
    .groupby(['employee_id', 'date'])
    .first()
    .reset_index()
)

# last OUT per employee/day
outs = (
    att[att['event_type'] == 'OUT']
    .sort_values(['employee_id', 'timestamp'])
    .groupby(['employee_id', 'date'])
    .last()
    .reset_index()
)

# >>> HERE WE CREATE daily (MUST BE BEFORE ANY MERGE USING daily) <<<
daily = pd.merge(
    ins[['employee_id', 'date', 'timestamp']].rename(columns={'timestamp': 'in_ts'}),
    outs[['employee_id', 'date', 'timestamp']].rename(columns={'timestamp': 'out_ts'}),
    on=['employee_id', 'date'],
    how='outer'
)

# -----------------------------

# 3) WORKED HOURS & SHIFT MERGE
print("2. Adding shift & worked hours...")

daily['worked_hours'] = (daily['out_ts'] - daily['in_ts']).dt.total_seconds() / 3600

# use the columns exactly as they are in employees.csv
daily = daily.merge(
    employees[['employee_id', 'shift_id']],
    on='employee_id',
    how='left'
)

daily = daily.merge(
    shifts[['shift_id', 'standard_hours_per_day']],
    on='shift_id',
    how='left'
)

# handle all possible column names safely
if 'standard_hours_per_day_x' in daily.columns:
    base_col = 'standard_hours_per_day_x'
elif 'standard_hours_per_day_y' in daily.columns:
    base_col = 'standard_hours_per_day_y'
else:
    base_col = 'standard_hours_per_day'

daily['standard_hours_per_day'] = pd.to_numeric(daily[base_col], errors='coerce')

daily['overtime_hours'] = (daily['worked_hours'] - daily['standard_hours_per_day']).clip(lower=0)
daily['absent_flag'] = daily['worked_hours'].isna()


# 3. PROCESS LEAVES
print("3. Processing approved leaves...")
approved_leaves = leaves[leaves['approved_flag'].str.upper() == 'Y'].copy()
leaves_expanded = []

for _, row in approved_leaves.iterrows():
    for date in pd.date_range(row['leave_start_date'], row['leave_end_date']):
        leaves_expanded.append({
            'employee_id': row['employee_id'],
            'date': date.date(),
            'leave_type': row['leave_type']
        })

leaves_df = pd.DataFrame(leaves_expanded)
daily = daily.merge(leaves_df, on=['employee_id', 'date'], how='left')
daily['is_paid_leave'] = daily['leave_type'].notna()
daily['true_absent'] = daily['absent_flag'] & (~daily['is_paid_leave'])

# 4. FINAL COLUMN ORDER
column_order = [
    'employee_id', 'date', 'in_ts', 'out_ts', 'worked_hours',
    'shift_id', 'standard_hours_per_day', 'overtime_hours',
    'absent_flag', 'leave_type', 'is_paid_leave', 'true_absent'
]
daily = daily[column_order]

# -----------------------------
# 5. SAVE HR DAILY FACT TABLE
# -----------------------------
daily.to_csv('hr_daily_fact.csv', index=False)
print(f"✅ SAVED: hr_daily_fact.csv ({len(daily)} rows)")

# -----------------------------
# 6. CREATE EMPLOYEE DIMENSION (robust)
# -----------------------------
print("Employees columns:", employees.columns)
print("Departments columns before fix:", departments.columns)

# If departments doesn't have 'department_id', try to recover/split it
if 'department_id' not in departments.columns:
    # Case A: departments was read as a single column containing comma-separated values
    if departments.shape[1] == 1:
        col0 = departments.columns[0]
        sample_cell = departments.iloc[0, 0] if len(departments) > 0 else ""
        # If the header string itself contains commas, or rows contain commas -> split
        if (',' in col0) or (',' in str(sample_cell)):
            # split every row on comma
            departments = departments.iloc[:, 0].str.split(',', expand=True)
            # if original header was actually "department_id,department_name,manager_id" then use it
            if ',' in col0:
                new_cols = [c.strip() for c in col0.split(',')]
            else:
                # fallback default names (adjust if your file has different columns)
                new_cols = ['department_id', 'department_name', 'manager_id'][:departments.shape[1]]
            departments.columns = new_cols
            # If the header ended up duplicated as first row, drop that row
            if len(departments) > 0 and list(departments.iloc[0].astype(str).str.strip()) == new_cols:
                departments = departments.iloc[1:].reset_index(drop=True)
        else:
            # fallback: split rows anyway and assign default names
            departments = departments.iloc[:, 0].str.split(',', expand=True)
            departments.columns = ['department_id', 'department_name', 'manager_id'][:departments.shape[1]]
    else:
        # Case B: file had a proper multi-column read but different header name; try to find a likely column
        # Look for any column that contains 'dept' or 'department'
        possible = [c for c in departments.columns if 'dept' in c.lower() or 'department' in c.lower()]
        if possible:
            # rename the first matching one to 'department_id'
            departments.rename(columns={possible[0]: 'department_id'}, inplace=True)

print("Departments columns after fix:", departments.columns)
print("Departments sample rows:\n", departments.head())

# Now ensure both keys exist before conversion
if 'department_id' not in departments.columns:
    raise KeyError("Could not find 'department_id' in departments after attempted fixes. "
                   "Please inspect departments.csv manually or paste the first few lines here.")

# Normalize types and strip whitespace
employees['department_id'] = employees['department_id'].astype(str).str.strip()
departments['department_id'] = departments['department_id'].astype(str).str.strip()

# Finally merge
employee_dim = employees.merge(departments, on='department_id', how='left')
employee_dim.to_csv('hr_employee_dim.csv', index=False)
print(f"✅ SAVED: hr_employee_dim.csv ({len(employee_dim)} rows)")
