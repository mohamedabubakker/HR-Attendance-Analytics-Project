SELECT TOP 5 * FROM hr_daily_fact
SELECT TOP 5 * FROM hr_employee_dim

--1: Total Attendance Summary (per employee)
SELECT 
    e.employee_id,
    e.emp_name,
    COUNT(f.date) AS days_present,
    SUM(CASE WHEN f.true_absent = 1 THEN 1 ELSE 0 END) AS days_absent,
    SUM(f.overtime_hours) AS total_overtime
FROM hr_daily_fact f
JOIN hr_employee_dim e ON f.employee_id = e.employee_id
GROUP BY e.employee_id, e.emp_name
ORDER BY e.employee_id

--2: Department-wise Overtime Report
SELECT 
    e.department_name,
    SUM(f.overtime_hours) AS total_overtime,
    AVG(f.overtime_hours) AS avg_overtime
FROM hr_daily_fact f
JOIN hr_employee_dim e ON f.employee_id = e.employee_id
GROUP BY e.department_name
ORDER BY total_overtime DESC

--3: Identify Employees With Frequent Absence
SELECT 
    e.employee_id,
    e.emp_name,
    COUNT(*) AS absent_days
FROM hr_daily_fact f
JOIN hr_employee_dim e 
      ON e.employee_id = f.employee_id
WHERE f.true_absent = 1
GROUP BY e.employee_id, e.emp_name
ORDER BY absent_days DESC

--4: Shift-wise Productivity
SELECT 
    f.shift_id,
    AVG(f.worked_hours) AS avg_hours,
    AVG(f.overtime_hours) AS avg_overtime
FROM hr_daily_fact f
GROUP BY f.shift_id

--5: Full Employee Attendance Snapshot
SELECT 
    e.employee_id,
    e.emp_name,
    e.department_name,
    f.date,
    f.worked_hours,
    f.overtime_hours,
    f.true_absent
FROM hr_employee_dim e
JOIN hr_daily_fact f
    ON e.employee_id = f.employee_id
ORDER BY e.employee_id,f.absent_flag

